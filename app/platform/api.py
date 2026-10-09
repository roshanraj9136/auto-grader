"""Platform REST API: auth, assignments, student dashboard, leaderboard, instructor analytics, gradebook."""
from __future__ import annotations

import csv
import hmac
import io
import json
import re
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import config
from ..jobs import Job
from ..report import store
from .db import get_db, iso_ago, loads, now_iso, to_utc_iso
from .labs import TASK_XP, total_tasks, user_progress, verified_tasks
from .labs import SERVER_TASKS
from .security import (LOGIN_ACCOUNT_THROTTLE, LOGIN_IP_THROTTLE, SIGNUP_GLOBAL_THROTTLE, SIGNUP_THROTTLE, authenticate, client_ip, end_session, hash_password,
                       is_demo_account, optional_user, public_user, require_instructor, require_instructor_write,
                       require_user, start_session, verify_password, visible_email)


def _not_demo(user: dict, action: str) -> None:
    if is_demo_account(user):
        raise HTTPException(status_code=403, detail=f"The public demo account can't {action}. Sign in with your own account.")

router = APIRouter()
DIMENSIONS = list(config.DEFAULT_WEIGHTS)
TRACKS = ["frontend", "backend", "database", "networking", "devops", "security", "fullstack"]
GRADES = ["A", "A-", "B", "B-", "C", "C-", "D", "F"]
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
MAX_ACTIVE_PER_USER = 3


# ---------------------------------------------------------------------------- submissions <-> jobs
STALE_ACTIVE_S = 30 * 60  # longer than any job can run (clone + docker build + agents + judge deadlines)


def record_submission(user_id: int, assignment_id: int | None, job: Job) -> int:
    db = get_db()
    existing = db.one("SELECT id FROM submissions WHERE user_id = ? AND job_id = ? AND "
                      "COALESCE(assignment_id, 0) = COALESCE(?, 0)", (user_id, job.id, assignment_id))
    if existing:  # identical in-flight request (single-flight): one row per user + job
        return existing["id"]
    sid = db.insert(
        "INSERT INTO submissions (user_id, assignment_id, job_id, repo_url, ref, status, instance, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)",
        (user_id, assignment_id, job.id, job.request.repo_url, job.request.ref, config.INSTANCE_ID, now_iso()))
    if job.status != "queued":  # it moved on (running / finished, e.g. cache hit) before the row existed
        on_job_event(job)
    return sid


def active_submissions(user_id: int) -> int:
    return get_db().scalar("SELECT COUNT(*) AS n FROM submissions WHERE user_id = ? AND status IN ('queued', 'running') "
                           "AND created_at > ?", (user_id, iso_ago(STALE_ACTIVE_S))) or 0


_ARTIFACT_COLUMNS = {"json": "report_json", "md": "report_md", "html": "report_html"}


def persist_artifacts(job_id: str) -> bool:
    """Copy a finished job's report files into the database (idempotent). Free cloud hosts give the
    container an ephemeral disk, so files alone would vanish on the next restart or spin-down."""
    texts = {}
    for ext in _ARTIFACT_COLUMNS:
        path = store.artifact_path(job_id, ext)
        if not path:
            return False
        texts[ext] = path.read_text(encoding="utf-8")
    get_db().run("INSERT INTO report_artifacts (job_id, report_json, report_md, report_html, created_at) "
                 "VALUES (?, ?, ?, ?, ?) ON CONFLICT (job_id) DO NOTHING",
                 (job_id, texts["json"], texts["md"], texts["html"], now_iso()))
    return True


def artifact_from_db(job_id: str, ext: str) -> str | None:
    col = _ARTIFACT_COLUMNS.get(ext)
    if not col or not re.fullmatch(r"[0-9a-f]{32}", job_id):
        return None
    return get_db().scalar(f"SELECT {col} AS v FROM report_artifacts WHERE job_id = ?", (job_id,))


def on_job_event(job: Job) -> None:
    """JobManager listener: mirror job state into every submission attached to the job."""
    db = get_db()
    if job.status == "done" and job.report:
        r = job.report
        dims = {d.dimension: d.final_score for d in r.verdict.dimensions}
        details = {"summary": r.verdict.summary[:1500], "top_priorities": r.verdict.top_priorities[:6],
                   "learning_path": r.verdict.learning_path[:6], "commit_sha": r.commit_sha,
                   "llm_mode": r.llm_mode, "speedup": r.speedup, "stack": r.repo_stats.get("stack", []),
                   "languages": r.repo_stats.get("languages", {})}
        # Rows an instructor has adjusted keep their adjusted score if the job state is ever replayed.
        db.run("UPDATE submissions SET status = 'done', final_score = ?, grade = ?, dims = ?, details = ?, total_ms = ?, "
               "cache_hit = ?, error = NULL, finished_at = ? WHERE job_id = ? "
               "AND id NOT IN (SELECT submission_id FROM grade_overrides)",
               (r.verdict.final_score, r.verdict.grade, json.dumps(dims), json.dumps(details, default=str), r.total_ms,
                1 if r.cache_hit else 0, now_iso(), job.id))
        persist_artifacts(job.id)
    elif job.status == "failed":
        db.run("UPDATE submissions SET status = 'failed', error = ?, finished_at = ? WHERE job_id = ?",
               ((job.error or "failed")[:500], now_iso(), job.id))
    else:
        db.run("UPDATE submissions SET status = ? WHERE job_id = ? AND status IN ('queued', 'running')",
               (job.status, job.id))


# ---------------------------------------------------------------------------- durable job events
EVENT_RETENTION_S = 3 * 86400


def store_job_events(batch: list[tuple[str, dict]]) -> None:
    """JobManager event sink: append events in order, one transaction per batch."""
    stamp = now_iso()
    with get_db().tx() as t:
        for job_id, evt in batch:
            t.run("INSERT INTO job_events (job_id, seq, event, created_at) VALUES (?, ?, ?, ?) "
                  "ON CONFLICT (job_id, seq) DO NOTHING", (job_id, int(evt["seq"]), json.dumps(evt, default=str), stamp))


def job_events_after(job_id: str, seq: int, limit: int = 500) -> list[dict]:
    rows = get_db().all("SELECT event FROM job_events WHERE job_id = ? AND seq > ? ORDER BY seq LIMIT ?",
                        (job_id, seq, limit))
    return [json.loads(r["event"]) for r in rows]


def job_known(job_id: str) -> bool:
    """A job this server can stream from the database: it has stored events or a submission row."""
    db = get_db()
    return bool(db.one("SELECT job_id FROM job_events WHERE job_id = ? LIMIT 1", (job_id,))
                or db.one("SELECT id FROM submissions WHERE job_id = ? LIMIT 1", (job_id,)))


def job_submission_state(job_id: str) -> dict | None:
    """The saved outcome of a job (for streams whose replica died before writing a final event)."""
    return get_db().one("SELECT status, final_score, grade, error, finished_at FROM submissions WHERE job_id = ? "
                        "ORDER BY id DESC LIMIT 1",
                        (job_id,))


def prune_job_events() -> int:
    return get_db().run("DELETE FROM job_events WHERE created_at < ?", (iso_ago(EVENT_RETENTION_S),))


def fail_orphaned_submissions() -> int:
    """This replica is shutting down: its in-memory jobs die with it, so their submissions can never complete."""
    return get_db().run("UPDATE submissions SET status = 'failed', error = 'grading server stopped before finishing', "
                        "finished_at = ? WHERE instance = ? AND status IN ('queued', 'running')",
                        (now_iso(), config.INSTANCE_ID))


# ---------------------------------------------------------------------------- replica liveness
def heartbeat() -> None:
    get_db().run("INSERT INTO instances (id, started_at, last_seen) VALUES (?, ?, ?) "
                 "ON CONFLICT (id) DO UPDATE SET last_seen = excluded.last_seen", (config.INSTANCE_ID, now_iso(), now_iso()))


def live_instances() -> set[str]:
    rows = get_db().all("SELECT id FROM instances WHERE last_seen >= ?", (iso_ago(config.INSTANCE_DEAD_S),))
    return {r["id"] for r in rows} | {config.INSTANCE_ID}


def reap_dead_instances() -> int:
    """Fail unfinished submissions owned by replicas that stopped heart-beating (crashed, scaled down,
    recreated with a new container ID). Any replica may do this; the UPDATE is idempotent."""
    cutoff = iso_ago(config.INSTANCE_DEAD_S)
    with get_db().tx() as t:
        n = t.run("UPDATE submissions SET status = 'failed', error = 'grading server stopped before finishing', "
                  "finished_at = ? WHERE status IN ('queued', 'running') AND (instance IS NULL OR "
                  "(instance <> ? AND instance NOT IN (SELECT id FROM instances WHERE last_seen >= ?)))",
                  (now_iso(), config.INSTANCE_ID, cutoff))
        t.run("DELETE FROM instances WHERE last_seen < ?", (iso_ago(7 * 86400),))
    return n


def reconcile_own(jobs: dict[str, Job]) -> int:
    """Repair this replica's rows whose state update was lost (e.g. a DB hiccup inside the job listener)."""
    fixed = 0
    rows = get_db().all("SELECT DISTINCT job_id FROM submissions WHERE instance = ? AND status IN ('queued', 'running')",
                        (config.INSTANCE_ID,))
    for r in rows:
        job = jobs.get(r["job_id"])
        if job is None:  # evicted from memory or never existed here: it cannot finish any more
            fixed += get_db().run("UPDATE submissions SET status = 'failed', error = 'job state lost', finished_at = ? "
                                  "WHERE job_id = ? AND status IN ('queued', 'running')", (now_iso(), r["job_id"]))
        elif job.status in ("done", "failed"):
            on_job_event(job)
            fixed += 1
    return fixed


def _sub_out(r: dict) -> dict:
    return {"id": r["id"], "job_id": r["job_id"], "assignment_id": r["assignment_id"], "user_id": r.get("user_id"),
            "assignment_title": r.get("assignment_title"), "repo_url": r["repo_url"], "ref": r["ref"],
            "status": r["status"], "final_score": r["final_score"], "grade": r["grade"], "dims": loads(r["dims"], {}),
            "details": loads(r["details"], {}), "total_ms": r["total_ms"], "cache_hit": bool(r["cache_hit"]),
            "error": r["error"], "created_at": r["created_at"], "finished_at": r["finished_at"],
            "student": r.get("student_name"), "entry_no": r.get("entry_no")}


def demo_student() -> dict | None:
    return get_db().one("SELECT * FROM users WHERE email = 'student@autograder.local' AND role = 'student'")


def submission_row(submission_id: int) -> dict:
    row = get_db().one("SELECT * FROM submissions WHERE id = ?", (submission_id,))
    if not row:
        raise HTTPException(status_code=404, detail="submission not found")
    return row


def latest_submissions(assignment_id: int) -> list[dict]:
    """Each student's most recent submission for an assignment."""
    rows = get_db().all("SELECT s.* FROM submissions s JOIN users u ON u.id = s.user_id AND u.role = 'student' "
                        "WHERE s.assignment_id = ? ORDER BY s.created_at DESC, s.id DESC", (assignment_id,))
    seen, out = set(), []
    for r in rows:
        if r["user_id"] not in seen:
            seen.add(r["user_id"])
            out.append(r)
    return out


def overrides_map() -> dict[int, dict]:
    """Every instructor grade adjustment, keyed by submission id (a small table: one row per adjusted grade)."""
    rows = get_db().all("SELECT o.submission_id, o.original_score, o.original_grade, o.score, o.grade, o.reason, "
                        "o.created_at, u.name AS by_name FROM grade_overrides o LEFT JOIN users u ON u.id = o.by_user")
    return {r["submission_id"]: r for r in rows}


def pinned_grades(user_id: int | None = None) -> dict[tuple[int, int], dict]:
    """(student, assignment) -> the instructor-adjusted submission. An adjustment *is* the student's grade for that
    assignment (it replaces their best attempt, including later resubmissions) until the instructor restores it."""
    sql = ("SELECT s.id, s.user_id, s.assignment_id, s.job_id, s.final_score, s.grade, s.created_at FROM grade_overrides o "
           "JOIN submissions s ON s.id = o.submission_id JOIN users u ON u.id = s.user_id AND u.role = 'student' "
           "WHERE s.assignment_id IS NOT NULL AND s.status = 'done'")
    args: tuple = ()
    if user_id is not None:
        sql += " AND s.user_id = ?"
        args = (user_id,)
    rows = get_db().all(sql + " ORDER BY o.created_at, o.submission_id", args)
    return {(r["user_id"], r["assignment_id"]): r for r in rows}  # the latest adjustment wins


def with_overrides(subs: list[dict]) -> list[dict]:
    """Attach `override` (or None) to submissions from `_sub_out`, so students see why a score was adjusted."""
    ovr = overrides_map() if subs else {}
    for s in subs:
        o = ovr.get(s["id"])
        s["override"] = None if not o else {k: o[k] for k in ("original_score", "original_grade", "reason", "by_name",
                                                                 "created_at")}
    return subs


def _assignment_out(r: dict) -> dict:
    return {"id": r["id"], "title": r["title"], "description": r["description"], "track": r["track"],
            "weights": loads(r["weights"], {}), "rubric_notes": r["rubric_notes"], "due_at": r["due_at"],
            "created_at": r["created_at"]}


def get_assignment(assignment_id: int) -> dict:
    row = get_db().one("SELECT * FROM assignments WHERE id = ?", (assignment_id,))
    if not row:
        raise HTTPException(status_code=404, detail="assignment not found")
    return _assignment_out(row)


# ---------------------------------------------------------------------------- auth
class SignupIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=200)
    entry_no: str | None = Field(default=None, max_length=20)
    code: str | None = Field(default=None, max_length=100)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


@router.post("/api/auth/signup", status_code=201)
def signup(body: SignupIn, request: Request, response: Response):
    # A public demo publishes an instructor login, so real students must not put their data on it.
    if config.DEMO_SEED:
        raise HTTPException(status_code=403, detail="sign-up is turned off on this public demo; use a demo account to sign in")
    ip = f"ip:{client_ip(request)}"
    if SIGNUP_THROTTLE.blocked(ip) or SIGNUP_GLOBAL_THROTTLE.blocked("all"):
        raise HTTPException(status_code=429, detail="too many attempts; try again in an hour")
    if config.SIGNUP_CODE and not hmac.compare_digest((body.code or "").strip().encode(), config.SIGNUP_CODE.encode()):
        SIGNUP_THROTTLE.fail(ip)  # the join code must not be guessable by brute force
        SIGNUP_GLOBAL_THROTTLE.fail("all")
        raise HTTPException(status_code=403, detail="invalid class join code")
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email) or email.endswith("autograder.local"):  # reserved for the demo accounts
        raise HTTPException(status_code=422, detail="enter a valid email address")
    db = get_db()
    if db.one("SELECT id FROM users WHERE email = ?", (email,)):
        raise HTTPException(status_code=409, detail="an account with this email already exists")
    entry = (body.entry_no or "").strip().upper() or None
    uid = db.insert("INSERT INTO users (email, name, entry_no, password_hash, role, created_at) VALUES (?, ?, ?, ?, 'student', ?)",
                    (email, body.name.strip(), entry, hash_password(body.password), now_iso()))
    start_session(response, uid)
    return {"user": public_user(db.one("SELECT * FROM users WHERE id = ?", (uid,)))}


@router.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    ip, account = f"ip:{client_ip(request)}", f"email:{body.email.strip().lower()}"
    if LOGIN_IP_THROTTLE.blocked(ip) or LOGIN_ACCOUNT_THROTTLE.blocked(account):
        raise HTTPException(status_code=429, detail="too many failed sign-ins; wait 15 minutes and try again")
    user = authenticate(body.email, body.password)
    if not user:
        LOGIN_IP_THROTTLE.fail(ip)
        LOGIN_ACCOUNT_THROTTLE.fail(account)
        raise HTTPException(status_code=401, detail="wrong email or password")
    start_session(response, user["id"])
    return {"user": public_user(user)}


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    end_session(request, response)
    return {"ok": True}


@router.get("/api/auth/me")
def me(user: dict | None = Depends(optional_user)):
    return {"user": public_user(user) if user else None, "signup_code_required": bool(config.SIGNUP_CODE),
            "demo": config.DEMO_SEED, "signup_open": not config.DEMO_SEED}


class ProfileIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    entry_no: str | None = Field(default=None, max_length=20)


class PasswordIn(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(min_length=8, max_length=200)


@router.put("/api/me")
def update_profile(body: ProfileIn, user: dict = Depends(require_user)):
    _not_demo(user, "change its profile")
    db = get_db()
    db.run("UPDATE users SET name = ?, entry_no = ? WHERE id = ?",
           (body.name.strip(), (body.entry_no or "").strip().upper() or None, user["id"]))
    return {"user": public_user(db.one("SELECT * FROM users WHERE id = ?", (user["id"],)))}


@router.post("/api/me/password")
def change_password(body: PasswordIn, request: Request, response: Response, user: dict = Depends(require_user)):
    _not_demo(user, "change its password")
    if not verify_password(body.current, user["password_hash"]):
        raise HTTPException(status_code=403, detail="current password is wrong")
    db = get_db()
    with db.tx() as t:
        t.run("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.new), user["id"]))
        t.run("DELETE FROM sessions WHERE user_id = ?", (user["id"],))  # sign out every other device
    start_session(response, user["id"])
    return {"ok": True}


# ---------------------------------------------------------------------------- assignments
class AssignmentIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=4000)
    track: str = "fullstack"
    weights: dict[str, float] | None = None
    rubric_notes: str = Field(default="", max_length=config.MAX_RUBRIC_CHARS)
    due_at: str | None = Field(default=None, max_length=40)


def _clean_assignment(body: AssignmentIn) -> tuple:
    if body.track not in TRACKS:
        raise HTTPException(status_code=422, detail=f"track must be one of {TRACKS}")
    raw = body.weights or config.DEFAULT_WEIGHTS
    if set(raw) - set(DIMENSIONS):
        raise HTTPException(status_code=422, detail=f"unknown rubric dimensions: {sorted(set(raw) - set(DIMENSIONS))}")
    weights = {k: float(v) for k, v in raw.items() if float(v) > 0}
    if not weights:
        raise HTTPException(status_code=422, detail="at least one rubric weight must be > 0")
    total = sum(weights.values())
    weights = {k: round(v / total, 4) for k, v in weights.items()}
    due = None
    if body.due_at:
        try:
            due = to_utc_iso(body.due_at)  # stored as UTC so text comparison is chronological
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="due_at must be an ISO date, e.g. 2026-11-01T23:59:00Z") from exc
    return body.title.strip(), body.description.strip(), body.track, json.dumps(weights), body.rubric_notes.strip(), due


@router.get("/api/assignments")
def list_assignments(user: dict | None = Depends(optional_user)):
    db = get_db()
    rows = [_assignment_out(r) for r in db.all("SELECT * FROM assignments ORDER BY COALESCE(due_at, created_at), id")]
    stats = {r["assignment_id"]: r for r in db.all(
        "SELECT s.assignment_id, COUNT(*) AS submissions, COUNT(DISTINCT s.user_id) AS students, MAX(s.final_score) AS top "
        "FROM submissions s JOIN users u ON u.id = s.user_id AND u.role = 'student' "
        "WHERE s.assignment_id IS NOT NULL GROUP BY s.assignment_id")}
    mine: dict[int, dict] = {}
    if user:
        for r in db.all("SELECT assignment_id, COUNT(*) AS attempts, MAX(final_score) AS best, MAX(created_at) AS last_at "
                        "FROM submissions WHERE user_id = ? AND assignment_id IS NOT NULL GROUP BY assignment_id", (user["id"],)):
            mine[r["assignment_id"]] = dict(r)
        for (_, aid), pin in pinned_grades(user["id"]).items():
            if aid in mine:
                mine[aid]["best"] = pin["final_score"]
    for a in rows:
        s = stats.get(a["id"], {})
        a["class_stats"] = {"submissions": s.get("submissions", 0), "students": s.get("students", 0), "top": s.get("top")}
        m = mine.get(a["id"])
        a["mine"] = {"attempts": m["attempts"], "best": m["best"], "last_at": m["last_at"]} if m else None
    return rows


@router.get("/api/assignments/{assignment_id}")
def assignment_detail(assignment_id: int, user: dict | None = Depends(optional_user)):
    a = get_assignment(assignment_id)
    if user:
        a["submissions"] = with_overrides([_sub_out(r) for r in get_db().all(
            "SELECT * FROM submissions WHERE user_id = ? AND assignment_id = ? ORDER BY created_at DESC, id DESC LIMIT 50",
            (user["id"], assignment_id))])
    return a


@router.post("/api/assignments", status_code=201)
def create_assignment(body: AssignmentIn, user: dict = Depends(require_instructor_write)):
    vals = _clean_assignment(body)
    aid = get_db().insert("INSERT INTO assignments (title, description, track, weights, rubric_notes, due_at, created_by, "
                          "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (*vals, user["id"], now_iso()))
    return get_assignment(aid)


@router.put("/api/assignments/{assignment_id}")
def update_assignment(assignment_id: int, body: AssignmentIn, _: dict = Depends(require_instructor_write)):
    get_assignment(assignment_id)
    get_db().run("UPDATE assignments SET title = ?, description = ?, track = ?, weights = ?, rubric_notes = ?, due_at = ? "
                 "WHERE id = ?", (*_clean_assignment(body), assignment_id))
    return get_assignment(assignment_id)


@router.delete("/api/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, _: dict = Depends(require_instructor_write)):
    get_assignment(assignment_id)
    with get_db().tx() as t:
        t.run("DELETE FROM submissions WHERE assignment_id = ?", (assignment_id,))
        t.run("DELETE FROM assignments WHERE id = ?", (assignment_id,))
    return {"ok": True}


# ---------------------------------------------------------------------------- student views
def _best_per_assignment(rows: list[dict], pins: dict | None = None) -> dict[int, float]:
    """Best graded attempt per assignment for one student's rows; instructor adjustments (pins) take precedence."""
    best: dict[int, float] = {}
    for r in rows:
        if r["status"] == "done" and r["assignment_id"] is not None and r["final_score"] is not None:
            best[r["assignment_id"]] = max(best.get(r["assignment_id"], 0.0), r["final_score"])
    for (_, aid), pin in (pins or {}).items():
        best[aid] = pin["final_score"]
    return best


def _xp(best: dict[int, float], verified_lab_tasks: int) -> int:
    """XP = best score per assignment + TASK_XP per *server-verified* lab task."""
    return int(round(sum(best.values()))) + verified_lab_tasks * TASK_XP


def _level(xp: int) -> dict:
    level, need = 1, 150
    remaining = xp
    while remaining >= need:
        remaining -= need
        level += 1
        need = int(need * 1.25)
    return {"level": level, "into_level": remaining, "level_size": need}


def leaderboard_rows(limit: int = 50) -> list[dict]:
    db = get_db()
    users = {u["id"]: u for u in db.all("SELECT id, name, entry_no FROM users WHERE role = 'student'")}
    best: dict[int, dict[int, float]] = defaultdict(dict)
    for r in db.all("SELECT user_id, assignment_id, MAX(final_score) AS best FROM submissions "
                    "WHERE status = 'done' AND assignment_id IS NOT NULL GROUP BY user_id, assignment_id"):
        best[r["user_id"]][r["assignment_id"]] = r["best"]
    for (uid, aid), pin in pinned_grades().items():
        best[uid][aid] = pin["final_score"]
    labs: dict[int, int] = defaultdict(int)
    verified: dict[int, int] = defaultdict(int)
    for r in db.all("SELECT user_id, lab, task FROM lab_progress"):
        labs[r["user_id"]] += 1
        if (r["lab"], r["task"]) in SERVER_TASKS:
            verified[r["user_id"]] += 1
    out = []
    for uid, u in users.items():
        b = best.get(uid, {})
        n_labs = labs.get(uid, 0)
        if not b and not n_labs:
            continue
        out.append({"user_id": uid, "name": u["name"], "entry_no": u["entry_no"], "xp": _xp(b, verified.get(uid, 0)),
                    "assignments_done": len(b), "avg_best": round(sum(b.values()) / len(b), 1) if b else None,
                    "labs_done": n_labs})
    out.sort(key=lambda r: (-r["xp"], -(r["avg_best"] or 0), r["name"]))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out[:limit]


@router.get("/api/leaderboard")
def leaderboard(user: dict = Depends(require_user)):  # names + entry numbers: class members only
    rows = leaderboard_rows(100)
    me_row = next((r for r in rows if user and r["user_id"] == user["id"]), None)
    return {"rows": rows, "me": me_row}


@router.get("/api/student/dashboard")
def student_dashboard(user: dict = Depends(require_user)):
    db = get_db()
    subs = db.all("SELECT s.*, a.title AS assignment_title FROM submissions s LEFT JOIN assignments a ON a.id = s.assignment_id "
                  "WHERE s.user_id = ? ORDER BY s.created_at DESC, s.id DESC LIMIT 300", (user["id"],))
    done = [s for s in subs if s["status"] == "done" and s["final_score"] is not None]
    best = _best_per_assignment(subs, pinned_grades(user["id"]))
    progress = user_progress(user["id"])
    lab_tasks = sum(len(v) for v in progress.values())
    xp = _xp(best, verified_tasks(progress))

    skills: dict[str, list[float]] = defaultdict(list)
    for s in done[:10]:
        for d, v in loads(s["dims"], {}).items():
            skills[d].append(v)
    skill_avg = {d: round(sum(skills[d]) / len(skills[d]), 1) if skills.get(d) else None for d in DIMENSIONS}

    assignments = list_assignments(user)
    upcoming = [a for a in assignments if a["due_at"] and a["due_at"] >= now_iso()][:5]
    latest = next((s for s in done), None)
    rank = next((r["rank"] for r in leaderboard_rows(10_000) if r["user_id"] == user["id"]), None)
    scores = [s["final_score"] for s in done]
    return {
        "user": public_user(user),
        "stats": {
            "submissions": len(subs), "graded": len(done),
            "avg_score": round(sum(best.values()) / len(best), 1) if best else (round(sum(scores) / len(scores), 1) if scores else None),
            "best_score": max(scores) if scores else None,
            "assignments_total": len(assignments), "assignments_done": len(best),
            "labs_done": lab_tasks, "labs_total": total_tasks(), "xp": xp, "rank": rank, **_level(xp),
        },
        "timeline": [{"t": s["created_at"], "score": s["final_score"], "grade": s["grade"],
                      "label": s["assignment_title"] or "Practice"} for s in reversed(done[:30])],
        "skills": skill_avg,
        "recent": with_overrides([_sub_out(s) for s in subs[:10]]),
        "assignments": assignments,
        "upcoming": upcoming,
        "learning_path": loads(latest["details"], {}).get("learning_path", []) if latest else [],
        "top_priorities": loads(latest["details"], {}).get("top_priorities", []) if latest else [],
        "lab_progress": progress,
    }


@router.get("/api/student/submissions")
def my_submissions(limit: int = 50, user: dict = Depends(require_user)):
    rows = get_db().all("SELECT s.*, a.title AS assignment_title FROM submissions s LEFT JOIN assignments a ON a.id = s.assignment_id "
                        "WHERE s.user_id = ? ORDER BY s.created_at DESC, s.id DESC LIMIT ?", (user["id"], max(1, min(limit, 200))))
    return with_overrides([_sub_out(r) for r in rows])


@router.get("/api/submissions/by-job/{job_id}")
def submission_by_job(job_id: str, user: dict = Depends(require_user)):
    row = get_db().one("SELECT s.*, a.title AS assignment_title FROM submissions s LEFT JOIN assignments a ON a.id = s.assignment_id "
                       "WHERE s.job_id = ? AND (s.user_id = ? OR ? = 'instructor') ORDER BY s.id DESC LIMIT 1",
                       (job_id, user["id"], user["role"]))
    if not row:
        raise HTTPException(status_code=404, detail="submission not found")
    return with_overrides([_sub_out(row)])[0]


# ---------------------------------------------------------------------------- instructor views
@router.get("/api/instructor/overview")
def instructor_overview(_: dict = Depends(require_instructor)):
    db = get_db()
    student_subs = "FROM submissions s JOIN users u ON u.id = s.user_id AND u.role = 'student'"
    best_map = {(r["user_id"], r["assignment_id"]): r["best"] for r in db.all(
        f"SELECT s.user_id, s.assignment_id, MAX(s.final_score) AS best {student_subs} "
        "WHERE s.status = 'done' AND s.assignment_id IS NOT NULL GROUP BY s.user_id, s.assignment_id")}
    best_map.update({k: pin["final_score"] for k, pin in pinned_grades().items()})
    best_rows = [{"user_id": u, "assignment_id": a, "best": v} for (u, a), v in best_map.items()]
    from ..agents.judge import letter_grade  # local import keeps the platform layer decoupled from agents at import time

    dist = {g: 0 for g in GRADES}
    for r in best_rows:
        dist[letter_grade(r["best"])] += 1
    dim_vals: dict[str, list[float]] = defaultdict(list)
    for r in db.all(f"SELECT s.dims {student_subs} WHERE s.status = 'done' ORDER BY s.id DESC LIMIT 500"):
        for d, v in loads(r["dims"], {}).items():
            dim_vals[d].append(v)
    per_assignment = []
    by_a: dict[int, list[float]] = defaultdict(list)
    for r in best_rows:
        by_a[r["assignment_id"]].append(r["best"])
    counts = {r["assignment_id"]: r["n"] for r in db.all(
        f"SELECT s.assignment_id, COUNT(*) AS n {student_subs} WHERE s.assignment_id IS NOT NULL GROUP BY s.assignment_id")}
    n_students = db.scalar("SELECT COUNT(*) AS n FROM users WHERE role = 'student'") or 0
    for a in db.all("SELECT id, title, track, due_at FROM assignments ORDER BY COALESCE(due_at, created_at), id"):
        vals = by_a.get(a["id"], [])
        per_assignment.append({**a, "students_submitted": len(vals), "submissions": counts.get(a["id"], 0),
                               "avg_best": round(sum(vals) / len(vals), 1) if vals else None,
                               "max_best": max(vals) if vals else None,
                               "completion": round(len(vals) / n_students, 3) if n_students else 0})
    recent = db.all("SELECT s.*, a.title AS assignment_title, u.name AS student_name, u.entry_no FROM submissions s "
                    "JOIN users u ON u.id = s.user_id LEFT JOIN assignments a ON a.id = s.assignment_id "
                    "ORDER BY s.created_at DESC, s.id DESC LIMIT 25")
    # Same repository submitted by several students for one assignment: a group project, or copying.
    shared = {(r["assignment_id"], r["repo_url"]): r["n"] for r in db.all(
        f"SELECT s.assignment_id, s.repo_url, COUNT(DISTINCT s.user_id) AS n {student_subs} "
        "WHERE s.assignment_id IS NOT NULL GROUP BY s.assignment_id, s.repo_url HAVING COUNT(DISTINCT s.user_id) > 1")}
    labs = db.all("SELECT lab, COUNT(*) AS n, COUNT(DISTINCT user_id) AS students FROM lab_progress GROUP BY lab")
    all_best = [r["best"] for r in best_rows]
    return {
        "counts": {"students": n_students,
                   "assignments": db.scalar("SELECT COUNT(*) AS n FROM assignments") or 0,
                   "submissions": db.scalar(f"SELECT COUNT(*) AS n {student_subs}") or 0,
                   "graded": db.scalar(f"SELECT COUNT(*) AS n {student_subs} WHERE s.status = 'done'") or 0,
                   "active": db.scalar(f"SELECT COUNT(*) AS n {student_subs} WHERE s.status IN ('queued', 'running') "
                                       "AND s.created_at > ?", (iso_ago(STALE_ACTIVE_S),)) or 0},
        "class_avg": round(sum(all_best) / len(all_best), 1) if all_best else None,
        "grade_distribution": dist,
        "dimension_avg": {d: round(sum(dim_vals[d]) / len(dim_vals[d]), 1) if dim_vals.get(d) else None for d in DIMENSIONS},
        "assignments": per_assignment,
        "recent": [{**_sub_out(r), "shared_by": shared.get((r["assignment_id"], r["repo_url"]), 0)} for r in recent],
        "shared_repos": len(shared),
        "labs": labs,
    }


@router.get("/api/instructor/students")
def instructor_students(viewer: dict = Depends(require_instructor)):
    lb = {r["user_id"]: r for r in leaderboard_rows(10_000)}
    rows = get_db().all("SELECT u.id, u.name, u.email, u.entry_no, u.created_at, COUNT(s.id) AS submissions, "
                        "MAX(s.created_at) AS last_active FROM users u LEFT JOIN submissions s ON s.user_id = u.id "
                        "WHERE u.role = 'student' GROUP BY u.id, u.name, u.email, u.entry_no, u.created_at ORDER BY u.name")
    for r in rows:
        x = lb.get(r["id"], {})
        r.update(xp=x.get("xp", 0), rank=x.get("rank"), avg_best=x.get("avg_best"), labs_done=x.get("labs_done", 0),
                 email=visible_email(viewer, r["email"]))
    return rows


def _csv_safe(v) -> str:
    """Neutralise spreadsheet formula injection (=, +, -, @ at the start of a cell)."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@router.get("/api/instructor/gradebook.csv")
def gradebook_csv(viewer: dict = Depends(require_instructor)):
    db = get_db()
    assignments = db.all("SELECT id, title FROM assignments ORDER BY COALESCE(due_at, created_at), id")
    best: dict[int, dict[int, float]] = defaultdict(dict)
    for r in db.all("SELECT user_id, assignment_id, MAX(final_score) AS best FROM submissions "
                    "WHERE status = 'done' AND assignment_id IS NOT NULL GROUP BY user_id, assignment_id"):
        best[r["user_id"]][r["assignment_id"]] = r["best"]
    for (uid, aid), pin in pinned_grades().items():
        best[uid][aid] = pin["final_score"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Name", "Entry No", "Email", *[a["title"] for a in assignments], "Average"])
    for u in db.all("SELECT id, name, entry_no, email FROM users WHERE role = 'student' ORDER BY name"):
        scores = [best[u["id"]].get(a["id"]) for a in assignments]
        got = [s for s in scores if s is not None]
        w.writerow([_csv_safe(u["name"]), _csv_safe(u["entry_no"]), _csv_safe(visible_email(viewer, u["email"])),
                    *["" if s is None else s for s in scores], round(sum(got) / len(got), 1) if got else ""])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="autograder-gradebook.csv"'})
