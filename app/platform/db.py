"""Tiny portable data layer over DB-API: SQLite (default, zero setup) or PostgreSQL (docker compose).

SQL is written once with `?` placeholders and ISO-8601 text timestamps, which both engines
support; the PostgreSQL adapter only rewrites placeholders and the primary-key type.
No ORM on purpose: it keeps the dependency surface small and every query visible.
"""
from __future__ import annotations

import json
import logging
import queue
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from .. import config

log = logging.getLogger("autograder.db")
POOL_SIZE = 10

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id {pk},
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        entry_no TEXT,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student',
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY,
        user_id {fk} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS assignments (
        id {pk},
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        track TEXT NOT NULL DEFAULT 'fullstack',
        weights TEXT NOT NULL,
        rubric_notes TEXT NOT NULL DEFAULT '',
        due_at TEXT,
        created_by {fk} REFERENCES users(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS submissions (
        id {pk},
        user_id {fk} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        assignment_id {fk} REFERENCES assignments(id) ON DELETE CASCADE,
        job_id TEXT NOT NULL,
        repo_url TEXT NOT NULL,
        ref TEXT,
        status TEXT NOT NULL,
        final_score {real},
        grade TEXT,
        dims TEXT,
        details TEXT,
        total_ms INTEGER,
        cache_hit INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        instance TEXT,
        created_at TEXT NOT NULL,
        finished_at TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS ix_submissions_user ON submissions(user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_submissions_job ON submissions(job_id)",
    "CREATE INDEX IF NOT EXISTS ix_submissions_assignment ON submissions(assignment_id)",
    "CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id)",
    """CREATE TABLE IF NOT EXISTS lab_progress (
        user_id {fk} NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        lab TEXT NOT NULL,
        task TEXT NOT NULL,
        completed_at TEXT NOT NULL,
        PRIMARY KEY (user_id, lab, task)
    )""",
    # Replica heartbeats: lets any replica fail submissions left behind by a replica that died
    # (container IDs change on every recreate, so "my own hostname" is not enough).
    """CREATE TABLE IF NOT EXISTS instances (
        id TEXT PRIMARY KEY,
        started_at TEXT NOT NULL,
        last_seen TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS ix_submissions_status ON submissions(status, instance)",
    """CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso_in(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds")


def iso_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="seconds")


def to_utc_iso(value: str) -> str:
    """Parse an ISO-8601 timestamp (naive = UTC) and normalise it to UTC, so text comparison is chronological."""
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except ValueError:
        return default


class Tx:
    """One transaction on one connection; helpers return plain dicts."""

    def __init__(self, conn: Any, kind: str) -> None:
        self.conn, self.kind = conn, kind

    def _sql(self, sql: str) -> str:
        # psycopg uses %s placeholders and treats a bare % as one, so escape literals first.
        return sql.replace("%", "%%").replace("?", "%s") if self.kind == "postgres" else sql

    def all(self, sql: str, params: tuple | list = ()) -> list[dict]:
        cur = self.conn.execute(self._sql(sql), tuple(params))
        return [dict(r) for r in cur.fetchall()]

    def one(self, sql: str, params: tuple | list = ()) -> dict | None:
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: tuple | list = ()) -> Any:
        row = self.one(sql, params)
        return next(iter(row.values())) if row else None

    def run(self, sql: str, params: tuple | list = ()) -> int:
        """Execute a write; returns the affected row count."""
        return self.conn.execute(self._sql(sql), tuple(params)).rowcount

    def insert(self, sql: str, params: tuple | list = ()) -> int:
        """INSERT ... RETURNING id (supported by SQLite >= 3.35 and PostgreSQL)."""
        row = self.conn.execute(self._sql(sql + " RETURNING id"), tuple(params)).fetchone()
        return int(row["id"] if isinstance(row, dict) else row[0])


class Database:
    """Thread-safe connection provider. Each helper call is its own short transaction."""

    def __init__(self, url: str) -> None:
        self.url = url
        if url.startswith("sqlite:///"):
            self.kind = "sqlite"
            self._path = url[len("sqlite:///"):]
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        elif url.startswith(("postgresql://", "postgres://")):
            self.kind = "postgres"
            self._pool: queue.LifoQueue = queue.LifoQueue(maxsize=POOL_SIZE)
            # Caps *concurrent* connections per replica (idle ones are capped by the queue), so
            # N replicas x POOL_SIZE stays below PostgreSQL's max_connections (default 100).
            self._slots = threading.BoundedSemaphore(POOL_SIZE)
        else:
            raise ValueError("AUTOGRADER_DATABASE_URL must start with sqlite:/// or postgresql://")

    @property
    def engine_name(self) -> str:
        return "PostgreSQL" if self.kind == "postgres" else f"SQLite {sqlite3.sqlite_version}"

    def _new_conn(self):
        if self.kind == "sqlite":
            conn = sqlite3.connect(self._path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        import psycopg  # imported lazily: only needed in PostgreSQL mode
        from psycopg.rows import dict_row

        return psycopg.connect(self.url, row_factory=dict_row, connect_timeout=10)

    @contextmanager
    def tx(self) -> Iterator[Tx]:
        """Borrow a connection, commit on success, roll back on error."""
        if self.kind == "sqlite":
            conn = self._new_conn()
            try:
                yield Tx(conn, self.kind)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()
            return
        if not self._slots.acquire(timeout=15):
            raise RuntimeError("database connection pool exhausted")
        try:
            conn = self._borrow()
        except BaseException:
            self._slots.release()
            raise
        healthy = True
        try:
            yield Tx(conn, self.kind)
            conn.commit()
        except BaseException:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001 - broken connection: dropped below
                healthy = False
            raise
        finally:
            try:
                if healthy and not conn.closed:
                    try:
                        self._pool.put_nowait((conn, time.monotonic()))
                    except queue.Full:
                        conn.close()
                else:
                    conn.close()
            finally:
                self._slots.release()

    def _borrow(self):
        """Reuse an idle connection; connections idle for a while are pinged first, so a DB restart
        costs one reconnect instead of one failed request per pooled connection."""
        while True:
            try:
                conn, idle_since = self._pool.get_nowait()
            except queue.Empty:
                return self._new_conn()
            if conn.closed:
                continue
            if time.monotonic() - idle_since < 10:
                return conn
            try:
                conn.execute("SELECT 1")
                conn.rollback()
                return conn
            except Exception:  # noqa: BLE001 - stale connection (server restarted): discard and retry
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    # ---- single-statement helpers ---------------------------------------------------
    def all(self, sql: str, params: tuple | list = ()) -> list[dict]:
        with self.tx() as t:
            return t.all(sql, params)

    def one(self, sql: str, params: tuple | list = ()) -> dict | None:
        with self.tx() as t:
            return t.one(sql, params)

    def scalar(self, sql: str, params: tuple | list = ()) -> Any:
        with self.tx() as t:
            return t.scalar(sql, params)

    def run(self, sql: str, params: tuple | list = ()) -> int:
        with self.tx() as t:
            return t.run(sql, params)

    def insert(self, sql: str, params: tuple | list = ()) -> int:
        with self.tx() as t:
            return t.insert(sql, params)

    def ping_ms(self) -> float:
        t0 = time.perf_counter()
        self.scalar("SELECT 1 AS ok")
        return round((time.perf_counter() - t0) * 1000, 2)

    # ---- schema --------------------------------------------------------------------
    def init_schema(self, seed: Callable[[Tx], None] | None = None) -> None:
        """Create tables (idempotent) and optionally seed, all in one serialised transaction."""
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if self.kind == "sqlite" else "BIGSERIAL PRIMARY KEY"
        fk = "INTEGER" if self.kind == "sqlite" else "BIGINT"  # must match the referenced BIGSERIAL
        real = "REAL" if self.kind == "sqlite" else "DOUBLE PRECISION"  # Postgres REAL is 4-byte: 63.4 -> 63.4000015
        if self.kind == "sqlite":
            conn = self._new_conn()
            try:
                conn.execute("PRAGMA journal_mode = WAL")  # readers never block the writer
            finally:
                conn.close()
        with self.tx() as t:
            if self.kind == "postgres":
                # Replicas start together: serialise DDL + seeding with a transaction-scoped advisory lock.
                t.run("SELECT pg_advisory_xact_lock(4242001)")
            for stmt in SCHEMA:
                t.run(stmt.format(pk=pk, fk=fk, real=real))
            if seed:
                seed(t)


_db: Database | None = None
_db_lock = threading.Lock()


def get_db() -> Database:
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = Database(config.DATABASE_URL)
    return _db
