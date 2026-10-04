"""Hands-on labs: frontend, databases, load balancing, networking and containers, in one place.

Some tasks are *server-verified* (the SQL and Dockerfile labs check the student's answer here),
others are *client-verified* (observations made in the browser, e.g. measuring RTT).
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import sqlite3
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import config
from ..sandbox.dockerfile_lint import lint as lint_dockerfile, parse as parse_dockerfile
from .db import get_db, now_iso
from .security import optional_user, require_user

router = APIRouter()
STARTED_AT = time.time()
_request_no = 0
_counter_lock = threading.Lock()

TASK_XP = 20

LABS: dict[str, dict] = {
    "frontend": {
        "title": "Frontend: HTML, CSS & JS", "track": "frontend", "icon": "FE",
        "summary": "Write HTML/CSS/JS in the browser, see it live in a sandboxed preview and pass DOM checks.",
        "tasks": {
            "heading": ("Add an <h1> that contains the word Hello", "client"),
            "counter": ("Button #inc increments the number shown in #count", "client"),
            "flex": ("Lay out .row with CSS flexbox (display: flex)", "client"),
            "a11y": ("Every <img> has alt text and every <input> has a <label>", "client"),
        },
    },
    "database": {
        "title": "Databases: SQL & indexes", "track": "database", "icon": "DB",
        "summary": "Query a real relational schema (students, courses, enrollments) and read query plans.",
        "tasks": {
            "select": ("Filter and sort: CSE students in year 3, by name", "server"),
            "join": ("Join three tables: who is enrolled in CSL100?", "server"),
            "aggregate": ("GROUP BY: number of students per branch", "server"),
            "index": ("Make EXPLAIN QUERY PLAN use an index", "server"),
        },
    },
    "loadbalancer": {
        "title": "Load balancers", "track": "networking", "icon": "LB",
        "summary": "Fire requests through Nginx at several API replicas and compare round-robin, least-connections and sticky hashing.",
        "tasks": {
            "burst": ("Send a burst of 30+ requests and read the distribution", "client"),
            "replicas": ("Observe responses from 2+ different replicas", "client"),
            "sticky": ("Compare round-robin with sticky (hash) routing", "client"),
        },
    },
    "network": {
        "title": "Networks & HTTP", "track": "networking", "icon": "NET",
        "summary": "Measure round-trip time and jitter, inspect proxy headers and read Server-Timing from the backend.",
        "tasks": {
            "rtt": ("Measure RTT (min / avg / p95 / jitter) over 20 requests", "client"),
            "headers": ("Find your request's path through the reverse proxy", "client"),
            "timing": ("Break a request down into DNS / TCP / TTFB / server time", "client"),
        },
    },
    "docker": {
        "title": "Containers: Dockerfiles", "track": "devops", "icon": "CTR",
        "summary": "Fix a real-world Dockerfile with the same 20+ rule linter AutoGrader uses to grade your projects.",
        "tasks": {
            "clean": ("No critical, high or medium lint findings", "server"),
            "multistage": ("Use a multi-stage build (builder + runtime)", "server"),
            "hardened": ("Run as a non-root USER with a HEALTHCHECK", "server"),
        },
    },
}


def lab_catalog() -> list[dict]:
    return [{"id": lid, "title": l["title"], "track": l["track"], "icon": l["icon"], "summary": l["summary"],
             "tasks": [{"id": tid, "title": t[0], "verify": t[1], "xp": TASK_XP if t[1] == "server" else 0}
                       for tid, t in l["tasks"].items()]}
            for lid, l in LABS.items()]


# Only answers the server checked itself earn XP (leaderboard integrity); browser-checked tasks
# still count as lab progress, since anyone can POST those with curl.
SERVER_TASKS = {(lid, tid) for lid, l in LABS.items() for tid, t in l["tasks"].items() if t[1] == "server"}


def verified_tasks(progress: dict[str, list[str]]) -> int:
    return sum(1 for lab, tasks in progress.items() for t in tasks if (lab, t) in SERVER_TASKS)


def total_tasks() -> int:
    return sum(len(l["tasks"]) for l in LABS.values())


def user_progress(user_id: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in get_db().all("SELECT lab, task FROM lab_progress WHERE user_id = ?", (user_id,)):
        out.setdefault(r["lab"], []).append(r["task"])
    return out


def mark_done(user_id: int, lab: str, task: str) -> bool:
    """Record completion; returns True if it is new."""
    if lab not in LABS or task not in LABS[lab]["tasks"]:
        return False
    n = get_db().run("INSERT INTO lab_progress (user_id, lab, task, completed_at) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT (user_id, lab, task) DO NOTHING", (user_id, lab, task, now_iso()))
    return n > 0


@router.get("/api/labs")
def list_labs(user: dict | None = Depends(optional_user)):
    progress = user_progress(user["id"]) if user else {}
    return {"labs": lab_catalog(), "progress": progress, "total_tasks": total_tasks(),
            "completed": sum(len(v) for v in progress.values()), "xp_per_task": TASK_XP}


class ProgressIn(BaseModel):
    lab: str = Field(max_length=40)
    task: str = Field(max_length=40)


@router.post("/api/labs/progress")
def complete_client_task(body: ProgressIn, user: dict = Depends(require_user)):
    lab = LABS.get(body.lab)
    if not lab or body.task not in lab["tasks"]:
        raise HTTPException(status_code=404, detail="unknown lab task")
    if lab["tasks"][body.task][1] != "client":
        raise HTTPException(status_code=403, detail="this task is verified by the server; submit your answer instead")
    return {"new": mark_done(user["id"], body.lab, body.task), "lab": body.lab, "task": body.task}


# ---------------------------------------------------------------------------- load balancer + network
def _next_request_no() -> int:
    global _request_no
    with _counter_lock:
        _request_no += 1
        return _request_no


@router.get("/api/lab/whoami")
@router.get("/lb/{algo}/whoami")
async def whoami(request: Request, algo: str = "direct", delay_ms: int = 0):
    """Identifies the replica that served the request. `delay_ms` simulates a slow backend (least-conn demo)."""
    if algo not in ("direct", "rr", "least", "hash"):
        raise HTTPException(status_code=404, detail="unknown algorithm")
    delay = max(0, min(delay_ms, 2000))
    if delay:
        await asyncio.sleep(delay / 1000)
    return {
        "instance": config.INSTANCE_ID, "pid": os.getpid(), "request_no": _next_request_no(),
        "uptime_s": round(time.time() - STARTED_AT, 1),
        "lb_algorithm": request.headers.get("x-lb-algorithm") or ("none (direct to API)" if algo == "direct" else algo),
        "behind_proxy": "x-forwarded-for" in request.headers, "delay_ms": delay,
    }


_HIDDEN_HEADERS = {"cookie", "authorization", "proxy-authorization", "x-api-key"}


@router.get("/api/lab/network")
def network_info(request: Request, response: Response):
    t0 = time.perf_counter()
    db = get_db()
    db_ms = db.ping_ms()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HIDDEN_HEADERS}
    xff = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    hops = [{"name": "Your browser", "detail": xff[0] if xff else (request.client.host if request.client else "?")}]
    if xff:
        hops.append({"name": "Nginx load balancer", "detail": f"reverse proxy, forwarded for {', '.join(xff)}"})
    hops.append({"name": f"API replica {config.INSTANCE_ID}", "detail": f"FastAPI / uvicorn, pid {os.getpid()}"})
    hops.append({"name": db.engine_name, "detail": f"SELECT 1 in {db_ms} ms"})
    app_ms = round((time.perf_counter() - t0) * 1000, 2)
    response.headers["Server-Timing"] = f'db;dur={db_ms};desc="database ping", app;dur={app_ms};desc="handler"'
    return {
        "client_ip": request.client.host if request.client else None, "x_forwarded_for": xff,
        "scheme": request.headers.get("x-forwarded-proto", request.url.scheme),
        "http_version": request.scope.get("http_version"), "host": request.headers.get("host"),
        "instance": config.INSTANCE_ID, "db_engine": db.engine_name, "db_ping_ms": db_ms, "app_ms": app_ms,
        "headers": headers, "hops": hops,
    }


# ---------------------------------------------------------------------------- SQL lab
_FIRST = ["Aarav", "Diya", "Kabir", "Ananya", "Rohan", "Isha", "Arjun", "Meera", "Vivaan", "Sara", "Aditya", "Kavya",
          "Ishaan", "Riya", "Reyansh", "Tara", "Krish", "Nisha", "Dev", "Pooja", "Yash", "Anika", "Rahul", "Sneha"]
_LAST = ["Sharma", "Verma", "Gupta", "Iyer", "Reddy", "Nair", "Khan", "Das", "Mehta", "Singh", "Patel", "Bose",
         "Joshi", "Kulkarni", "Chopra", "Menon"]
_COURSES = [("CSL100", "Introduction to Computer Science", 4), ("COL106", "Data Structures and Algorithms", 5),
            ("COL216", "Computer Architecture", 4), ("COL331", "Operating Systems", 5), ("COL334", "Computer Networks", 4),
            ("COL351", "Analysis and Design of Algorithms", 4), ("COL362", "Database Management Systems", 4),
            ("COL380", "Parallel and Distributed Programming", 3), ("ELL201", "Digital Electronics", 4),
            ("MTL106", "Probability and Stochastic Processes", 4)]
_BRANCHES = ["CSE", "EE", "ME", "CE", "MnC"]

SAMPLE_SCHEMA = """CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT NOT NULL, branch TEXT NOT NULL, year INTEGER NOT NULL);
CREATE TABLE courses (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, title TEXT NOT NULL, credits INTEGER NOT NULL);
CREATE TABLE enrollments (student_id INTEGER NOT NULL REFERENCES students(id), course_id INTEGER NOT NULL REFERENCES courses(id),
                          semester TEXT NOT NULL, grade_points INTEGER, PRIMARY KEY (course_id, student_id));"""

SQL_TASKS = {
    "select": ("SELECT name, year FROM students WHERE branch = 'CSE' AND year = 3 ORDER BY name", True),
    "join": ("SELECT s.name FROM students s JOIN enrollments e ON e.student_id = s.id "
             "JOIN courses c ON c.id = e.course_id WHERE c.code = 'CSL100' ORDER BY s.name", True),
    "aggregate": ("SELECT branch, COUNT(*) AS n FROM students GROUP BY branch", False),
}

_template: bytes | None = None
_template_lock = threading.Lock()
_sql_slots = threading.BoundedSemaphore(2)  # at most two lab queries execute at once per replica

_OK_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
_BLOCKED_FUNCS = {"randomblob", "zeroblob", "printf", "format", "load_extension", "readfile", "writefile"}


def _build_template() -> bytes:
    rng = random.Random(100)  # deterministic dataset: everyone sees the same rows
    con = sqlite3.connect(":memory:")
    con.executescript(SAMPLE_SCHEMA)
    con.executemany("INSERT INTO courses (id, code, title, credits) VALUES (?, ?, ?, ?)",
                    [(i + 1, c, t, cr) for i, (c, t, cr) in enumerate(_COURSES)])
    students = [(i, f"{rng.choice(_FIRST)} {rng.choice(_LAST)}", rng.choice(_BRANCHES), rng.randint(1, 4))
                for i in range(1, 241)]
    con.executemany("INSERT INTO students (id, name, branch, year) VALUES (?, ?, ?, ?)", students)
    rows = []
    for sid, *_ in students:
        for cid in rng.sample(range(1, len(_COURSES) + 1), rng.randint(3, 6)):
            rows.append((sid, cid, rng.choice(["2025-I", "2025-II", "2026-I"]), rng.randint(4, 10)))
    con.executemany("INSERT INTO enrollments (student_id, course_id, semester, grade_points) VALUES (?, ?, ?, ?)", rows)
    con.commit()
    data = con.serialize()
    con.close()
    return data


def _authorizer(action, arg1, arg2, _db, _trigger):
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in _BLOCKED_FUNCS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK if action in _OK_ACTIONS else sqlite3.SQLITE_DENY


def _norm(rows: list[tuple]) -> list[tuple]:
    return [tuple(round(v, 2) if isinstance(v, float) else v for v in r) for r in rows]


def run_lab_sql(query: str, with_index: bool, max_rows: int = 200) -> dict:
    """Run one read-only statement against a fresh in-memory copy of the sample DB.

    Defence in depth: fresh in-memory DB per query, `query_only`, an authorizer that allows only
    reads (no ATTACH/PRAGMA/DDL/DML), capped value size, a 0.5 s CPU deadline and a row cap.
    """
    global _template
    if _template is None:
        with _template_lock:
            if _template is None:
                _template = _build_template()
    if not _sql_slots.acquire(timeout=0.25):  # fail fast: never park a shared worker thread for long
        raise HTTPException(status_code=429, detail="SQL lab is busy, retry in a moment")
    con = sqlite3.connect(":memory:", check_same_thread=False)
    try:
        con.deserialize(_template)
        if with_index:
            con.execute("CREATE INDEX ix_enrollments_student ON enrollments(student_id)")
        con.execute("PRAGMA query_only = ON")
        con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 500)
        con.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 4000)
        con.set_authorizer(_authorizer)
        deadline = time.perf_counter() + 0.5
        con.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, 1000)
        t0 = time.perf_counter()
        try:
            cur = con.execute(query)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(max_rows + 1)
        except sqlite3.OperationalError as exc:
            msg = str(exc)
            if "interrupted" in msg:
                msg = "query took longer than 0.5 s and was stopped (try adding a WHERE clause or LIMIT)"
            elif "not authorized" in msg:
                msg = "only read-only SELECT / WITH / EXPLAIN statements are allowed in this lab"
            raise HTTPException(status_code=400, detail=msg) from None
        except (sqlite3.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        ms = round((time.perf_counter() - t0) * 1000, 2)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        plan: list[str] = []
        if not _strip_leading_comments(query).lower().startswith("explain"):
            try:
                plan = [r[3] for r in con.execute("EXPLAIN QUERY PLAN " + query).fetchall()]
            except sqlite3.Error:
                plan = []
        return {"columns": cols, "rows": _norm([tuple(r) for r in rows]), "truncated": truncated, "ms": ms, "plan": plan}
    finally:
        con.close()
        _sql_slots.release()


_SQL_COMMENT = re.compile(r"^\s*(--[^\n]*(\n|$)|/\*.*?\*/)", re.S)


def _strip_leading_comments(sql: str) -> str:
    prev = None
    while prev != sql:
        prev, sql = sql, _SQL_COMMENT.sub("", sql, count=1)
    return sql.strip()


def _check_sql_task(task: str, query: str, with_index: bool, result: dict) -> tuple[bool, str]:
    if task == "index":
        q = " ".join(_strip_leading_comments(query).lower().split())
        if not q.startswith("explain query plan"):
            return False, "Start the statement with EXPLAIN QUERY PLAN."
        if "student_id" not in q:
            return False, "Look up enrollments by student_id."
        if not with_index:
            return False, "Enable the index on enrollments(student_id) first."
        details = " ".join(str(r[-1]) for r in result["rows"]).upper()
        if "IX_ENROLLMENTS_STUDENT" in details:
            return True, "The planner now does a SEARCH using your index instead of a full SCAN."
        return False, "The plan does not use ix_enrollments_student yet: filter enrollments on student_id."
    ref_sql, ordered = SQL_TASKS[task]
    expected = run_lab_sql(ref_sql, with_index=False, max_rows=10_000)
    got = result["rows"]
    if result["truncated"]:
        return False, "Your result has too many rows."
    if len(result["columns"]) != len(expected["columns"]):
        return False, f"Expected {len(expected['columns'])} column(s): {', '.join(expected['columns'])}."
    exp_rows = expected["rows"]
    same_set = sorted(map(repr, got)) == sorted(map(repr, exp_rows))
    if (got == exp_rows) if ordered else same_set:
        return True, f"Correct: {len(got)} row(s) match the reference answer."
    if ordered and same_set:
        return False, "Right rows, wrong order: check the ORDER BY."
    return False, f"Not yet: expected {len(exp_rows)} row(s), got {len(got)}."


class SqlIn(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    with_index: bool = False
    task: str | None = Field(default=None, max_length=40)


@router.get("/api/lab/sql/schema")
def sql_schema():
    return {"schema": SAMPLE_SCHEMA, "tasks": {k: LABS["database"]["tasks"][k][0] for k in LABS["database"]["tasks"]}}


@router.post("/api/lab/sql")
def lab_sql(body: SqlIn, user: dict | None = Depends(optional_user)):
    result = run_lab_sql(body.query, body.with_index)
    if body.task:
        if body.task not in LABS["database"]["tasks"]:
            raise HTTPException(status_code=404, detail="unknown task")
        ok, msg = _check_sql_task(body.task, body.query, body.with_index, result)
        result["check"] = {"task": body.task, "passed": ok, "message": msg,
                           "recorded": bool(ok and user and mark_done(user["id"], "database", body.task))}
    return result


# ---------------------------------------------------------------------------- Dockerfile lab
class DockerfileIn(BaseModel):
    dockerfile_text: str = Field(min_length=1, max_length=config.MAX_DOCKERFILE_BYTES)
    has_dockerignore: bool = True


@router.post("/api/lab/dockerfile")
def lab_dockerfile(body: DockerfileIn, user: dict | None = Depends(optional_user)):
    findings = lint_dockerfile(body.dockerfile_text, body.has_dockerignore)
    ins = parse_dockerfile(body.dockerfile_text)
    froms = [i for i in ins if i.op == "FROM"]
    users = [i for i in ins if i.op == "USER"]
    nonroot = bool(users) and users[-1].args.strip().split(":")[0] not in ("root", "0")
    checks = {
        "clean": (bool(froms) and not any(f.severity in ("critical", "high", "medium") for f in findings),
                  "no critical/high/medium findings"),
        "multistage": (len(froms) >= 2, f"{len(froms)} FROM stage(s)"),
        "hardened": (nonroot and any(i.op == "HEALTHCHECK" for i in ins), "non-root USER + HEALTHCHECK"),
    }
    recorded = []
    if user:
        for task, (ok, _) in checks.items():
            if ok and mark_done(user["id"], "docker", task):
                recorded.append(task)
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    return {
        "findings": [f.model_dump() for f in sorted(findings, key=lambda f: sev_order.get(f.severity, 9))],
        "checks": {k: {"passed": v[0], "detail": v[1]} for k, v in checks.items()},
        "instructions": len(ins), "stages": len(froms), "recorded": recorded,
        "score": max(0, 100 - sum({"critical": 40, "high": 20, "medium": 10, "low": 4, "info": 1}.get(f.severity, 0)
                                  for f in findings)),
    }
