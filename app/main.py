"""HTTP layer: REST + Server-Sent Events + the learning-platform API and single-page web app."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__, config
from .agents.llm import llm_enabled
from .ingest import git_ops
from .jobs import JobManager
from .models import GradeRequest, Rubric
from .platform import api as platform_api
from .platform import labs as platform_labs
from .platform.db import get_db
from .platform.seed import seed
from .platform.security import session_user
from .report import store
from .tracing import METRICS

logging.basicConfig(level=os.getenv("AUTOGRADER_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("autograder")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
API_TOKEN = os.getenv("AUTOGRADER_API_TOKEN", "").strip()

manager: JobManager | None = None


async def _maintenance_loop() -> None:
    """Heartbeat + reap dead replicas' submissions/clone dirs + repair lost state updates."""
    while True:
        try:
            await asyncio.to_thread(platform_api.heartbeat)
            reaped = await asyncio.to_thread(platform_api.reap_dead_instances)
            if manager is not None:
                fixed = await asyncio.to_thread(platform_api.reconcile_own, dict(manager.jobs))
                if reaped or fixed:
                    log.info("maintenance: failed %d orphaned submission(s), reconciled %d", reaped, fixed)
            live = await asyncio.to_thread(platform_api.live_instances)
            jobs_root = config.WORK_DIR / "jobs"
            for d in await asyncio.to_thread(lambda: [p for p in jobs_root.iterdir() if p.is_dir()]):
                if d.name not in live:  # clone dirs left by a replica that is gone for good
                    await asyncio.to_thread(git_ops.remove_tree, d)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - keep the loop alive across DB hiccups
            log.exception("maintenance loop iteration failed")
        await asyncio.sleep(config.HEARTBEAT_S)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global manager
    for d in (config.JOBS_DIR, config.CACHE_DIR, store.REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    # Remove clones orphaned by a previous crash of *this* replica (others share the volume).
    for stale in config.JOBS_DIR.iterdir():
        await asyncio.to_thread(git_ops.remove_tree, stale)
    db = get_db()
    await asyncio.to_thread(db.init_schema, seed)
    await asyncio.to_thread(platform_api.heartbeat)
    docker_ok = await asyncio.to_thread(config.docker_available)  # warm the cached probe off the event loop
    manager = JobManager()
    manager.add_listener(platform_api.on_job_event)
    maintenance = asyncio.create_task(_maintenance_loop(), name="maintenance")
    log.info("AutoGrader+ %s ready | instance=%s db=%s llm=%s agent_model=%s judge_model=%s docker=%s",
             __version__, config.INSTANCE_ID, db.engine_name, llm_enabled(), config.AGENT_MODEL, config.JUDGE_MODEL,
             docker_ok)
    yield
    maintenance.cancel()
    await manager.shutdown()
    try:  # this replica's in-memory jobs die with it
        n = await asyncio.to_thread(platform_api.fail_orphaned_submissions)
        if n:
            log.warning("marked %d unfinished submission(s) as failed on shutdown", n)
    except Exception:  # noqa: BLE001 - DB may already be gone; peers reap them via the heartbeat
        log.exception("could not fail unfinished submissions on shutdown")


app = FastAPI(title="AutoGrader+", version=__version__, lifespan=lifespan,
              description="Full-stack learning platform: multi-agent (5 specialists + judge) grading of GitHub projects, "
                          "assignments, dashboards and hands-on labs for frontend, databases, networks and load balancers.")

_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
# The frontend-lab sandbox runs student-written inline JS; it is loaded in an opaque-origin
# <iframe sandbox="allow-scripts"> so it cannot read the app's cookies, storage or DOM. The CSP
# `sandbox` directive enforces the same even if someone opens /sandbox.html as a top-level page.
_SANDBOX_CSP = ("sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "img-src data:; frame-ancestors 'self'")
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _cross_site(scope) -> bool:
    """CSRF defence in depth on top of SameSite=Lax: refuse state-changing requests that a browser marks
    as coming from another site (Fetch Metadata), or whose Origin host differs from the Host header.
    Non-browser clients (curl, CI with the API token) send neither header and are unaffected."""
    if scope.get("method") not in _UNSAFE_METHODS:
        return False
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    site = headers.get("sec-fetch-site")
    if site:
        return site not in ("same-origin", "none")
    origin = headers.get("origin")
    if not origin or origin == "null":
        return bool(origin)  # "null" origin (sandboxed iframes, data: URLs) is never legitimate here
    host = headers.get("x-forwarded-host") or headers.get("host", "")
    strip_port = lambda h: h.rsplit("]", 1)[-1].split(":")[0] if h else h  # noqa: E731
    origin_host = origin.split("://", 1)[-1].split("/", 1)[0]
    return strip_port(origin_host).lower() != strip_port(host).lower()


class PlatformHeaders:
    """Pure ASGI middleware (does not buffer or wrap streaming bodies, so SSE is unaffected)."""

    def __init__(self, app_) -> None:
        self.app = app_

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if path.startswith("/api/") and _cross_site(scope):
            body = b'{"detail":"cross-site request blocked"}'
            await send({"type": "http.response.start", "status": 403,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", [])]
                present = {k.lower() for k, _ in headers}

                def put(name: str, value: str, override: bool = False):
                    key = name.lower().encode()
                    nonlocal headers
                    if key in present and not override:
                        return
                    headers = [(k, v) for k, v in headers if k.lower() != key]
                    headers.append((key, value.encode()))
                    present.add(key)

                put("X-Served-By", config.INSTANCE_ID, override=True)  # visible in the load-balancer lab
                put("X-Content-Type-Options", "nosniff")
                put("Referrer-Policy", "same-origin")
                if path == "/sandbox.html":
                    put("Content-Security-Policy", _SANDBOX_CSP, override=True)
                elif path != "/docs" and not path.startswith("/redoc"):
                    put("Content-Security-Policy", _CSP)
                    put("X-Frame-Options", "SAMEORIGIN")
                last = path.rsplit("/", 1)[-1]
                if not path.startswith("/api") and ("." not in last or path.endswith(".html") or last == "sw.js"):
                    put("Cache-Control", "no-cache", override=True)  # app shell: revalidate so deploys show at once
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(PlatformHeaders)


def require_submitter(request: Request, authorization: str | None = Header(default=None)) -> dict | None:
    """Grading needs a logged-in user, or the API bearer token (for scripts/CI). Returns the user, if any."""
    user = session_user(request)
    if user:
        return user
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if API_TOKEN and supplied and hmac.compare_digest(supplied, API_TOKEN):
        return None
    if API_TOKEN or config.REQUIRE_LOGIN:
        raise HTTPException(status_code=401, detail="login required (or a valid API token)")
    return None


def _token_ok(authorization: str | None) -> bool:
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    return bool(API_TOKEN and supplied and hmac.compare_digest(supplied, API_TOKEN))


def require_job_access(job_id: str, request: Request, authorization: str | None = Header(default=None)) -> None:
    """Reports and live streams: the submitting student(s), instructors, or the API token holder.
    (With login disabled and no token, the legacy open mode applies.)"""
    if _token_ok(authorization):
        return
    user = session_user(request)
    if not user:
        if not API_TOKEN and not config.REQUIRE_LOGIN:
            return
        raise HTTPException(status_code=401, detail="login required")
    if user["role"] == "instructor":
        return
    if not get_db().one("SELECT id FROM submissions WHERE job_id = ? AND user_id = ? LIMIT 1", (job_id, user["id"])):
        raise HTTPException(status_code=404, detail="job not found")


def require_operator(request: Request, authorization: str | None = Header(default=None)) -> None:
    """Cross-user listings: instructors or the API token only."""
    if _token_ok(authorization):
        return
    user = session_user(request)
    if user and user["role"] == "instructor":
        return
    if not user and not API_TOKEN and not config.REQUIRE_LOGIN:
        return
    raise HTTPException(status_code=403 if user else 401, detail="instructor role or API token required")


class GradeIn(BaseModel):
    repo_url: str = Field(examples=["https://github.com/owner/repo"])
    ref: str | None = Field(default=None, description="branch, tag or commit SHA (default branch if omitted)")
    dockerfile_text: str | None = Field(default=None, max_length=config.MAX_DOCKERFILE_BYTES)
    weights: dict[str, float] | None = Field(default=None, description=f"subset of {list(config.DEFAULT_WEIGHTS)}")
    rubric_notes: str = Field(default="", max_length=config.MAX_RUBRIC_CHARS)
    force: bool = False


class SubmitIn(BaseModel):
    repo_url: str
    ref: str | None = None
    dockerfile_text: str | None = Field(default=None, max_length=config.MAX_DOCKERFILE_BYTES)
    force: bool = False


def build_request(body: GradeIn) -> GradeRequest:
    try:
        url = git_ops.normalize_repo_url(body.repo_url)
        ref = git_ops.validate_ref(body.ref)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raw = body.weights or config.DEFAULT_WEIGHTS
    unknown = set(raw) - set(config.DEFAULT_WEIGHTS)
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown rubric dimensions: {sorted(unknown)}")
    weights = {k: float(v) for k, v in raw.items() if float(v) > 0}
    if not weights:
        raise HTTPException(status_code=422, detail="at least one rubric weight must be > 0")
    total = sum(weights.values())
    weights = {k: round(v / total, 4) for k, v in weights.items()}
    return GradeRequest(repo_url=url, ref=ref, dockerfile_text=(body.dockerfile_text or None),
                        rubric=Rubric(weights=weights, notes=body.rubric_notes.strip()), force=body.force)


async def _submit(body: GradeIn, user: dict | None = None, assignment_id: int | None = None) -> JSONResponse:
    assert manager is not None
    req = build_request(body)
    if user and await asyncio.to_thread(platform_api.active_submissions, user["id"]) >= platform_api.MAX_ACTIVE_PER_USER:
        raise HTTPException(status_code=429, detail=f"you already have {platform_api.MAX_ACTIVE_PER_USER} gradings in "
                                                    "progress; wait for one to finish")
    job, deduped = manager.submit(req)
    submission_id = None
    if user:
        submission_id = await asyncio.to_thread(platform_api.record_submission, user["id"], assignment_id, job)
    return JSONResponse(status_code=202, content={
        "job_id": job.id, "status": job.status, "deduplicated": deduped, "submission_id": submission_id,
        "links": {"self": f"/api/jobs/{job.id}", "events": f"/api/jobs/{job.id}/events",
                  "report": f"/api/jobs/{job.id}/report", "html": f"/api/jobs/{job.id}/report.html",
                  "markdown": f"/api/jobs/{job.id}/report.md"},
    })


@app.post("/api/grade", status_code=202)
async def grade(body: GradeIn, user: dict | None = Depends(require_submitter)):
    """Submit a free-form (practice) grading job. Returns immediately; follow progress via SSE."""
    return await _submit(body, user)


@app.post("/api/grade/upload", status_code=202)
async def grade_upload(
    repo_url: str = Form(...),
    ref: str | None = Form(None),
    rubric_notes: str = Form(""),
    weights: str | None = Form(None, description="JSON object, e.g. {\"security\": 0.3, ...}"),
    force: bool = Form(False),
    dockerfile: UploadFile | None = File(None),
    user: dict | None = Depends(require_submitter),
):
    """Submit with a Dockerfile upload (multipart), e.g. `curl -F repo_url=... -F dockerfile=@Dockerfile`."""
    text = None
    if dockerfile is not None:
        raw = await dockerfile.read(config.MAX_DOCKERFILE_BYTES + 1)
        if len(raw) > config.MAX_DOCKERFILE_BYTES:
            raise HTTPException(status_code=413, detail="Dockerfile too large")
        text = raw.decode("utf-8-sig", errors="replace")
    try:
        parsed = json.loads(weights) if weights else None
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="weights must be a JSON object") from exc
    return await _submit(GradeIn(repo_url=repo_url, ref=ref, dockerfile_text=text, weights=parsed,
                                 rubric_notes=rubric_notes, force=force), user)


@app.post("/api/assignments/{assignment_id}/submit", status_code=202)
async def submit_assignment(assignment_id: int, body: SubmitIn, request: Request):
    """Submit a repository for an assignment: graded with the assignment's rubric weights and brief."""
    user = await asyncio.to_thread(session_user, request)
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    a = await asyncio.to_thread(platform_api.get_assignment, assignment_id)
    # Rubric first: if the combined text has to be truncated, the description loses its tail, not the rubric.
    notes = f"Rubric: {a['rubric_notes']}\n\nAssignment: {a['title']}\n{a['description']}".strip()
    return await _submit(GradeIn(repo_url=body.repo_url, ref=body.ref, dockerfile_text=body.dockerfile_text,
                                 weights=a["weights"], rubric_notes=notes[: config.MAX_RUBRIC_CHARS], force=body.force),
                         user, assignment_id)


@app.get("/api/jobs", dependencies=[Depends(require_operator)])
async def list_jobs(limit: int = 20):
    assert manager is not None
    jobs = list(manager.jobs.values())[-max(1, min(limit, 100)):]
    return [j.summary() for j in reversed(jobs)]


@app.get("/api/jobs/{job_id}", dependencies=[Depends(require_job_access)])
async def get_job(job_id: str):
    assert manager is not None
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found on this replica")
    return {**job.summary(), "events_log": job.events[-200:]}


@app.get("/api/jobs/{job_id}/events", dependencies=[Depends(require_job_access)])
async def job_events(job_id: str, request: Request):
    """Server-Sent Events: full replay, then live stage/agent events until job_done/job_failed."""
    assert manager is not None
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    async def gen():
        async for evt in job.stream():
            if await request.is_disconnected():
                break
            if evt is None:
                yield ": ping\n\n"
                continue
            yield f"id: {evt['seq']}\ndata: {json.dumps(evt)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/jobs/{job_id}/report", dependencies=[Depends(require_job_access)])
async def job_report(job_id: str):
    assert manager is not None
    job = manager.get(job_id)
    if job and job.report:
        return JSONResponse(json.loads(job.report.model_dump_json()))
    if job and job.status in ("queued", "running"):
        raise HTTPException(status_code=409, detail=f"job is {job.status}")
    path = store.artifact_path(job_id, "json")  # survives restarts / store eviction / other replicas
    if not path:
        raise HTTPException(status_code=404, detail="report not found")
    return FileResponse(path, media_type="application/json")


@app.get("/api/jobs/{job_id}/report.{fmt}", dependencies=[Depends(require_job_access)])
async def job_report_file(job_id: str, fmt: str):
    path = store.artifact_path(job_id, fmt)
    if not path:
        raise HTTPException(status_code=404, detail="report not found (yet)")
    media = {"md": "text/markdown; charset=utf-8", "html": "text/html; charset=utf-8", "json": "application/json"}[fmt]
    headers = {"Content-Disposition": f'attachment; filename="autograder-{job_id[:8]}.{fmt}"'} if fmt == "md" else None
    return FileResponse(path, media_type=media, headers=headers)


@app.get("/api/health")
async def health():
    db = get_db()
    try:
        db_ms = await asyncio.to_thread(db.ping_ms)
        db_ok = True
    except Exception:  # noqa: BLE001 - health must answer even when the DB is down
        db_ms, db_ok = None, False
    return {"status": "ok" if db_ok else "degraded", "version": __version__, "instance": config.INSTANCE_ID,
            "llm_mode": llm_enabled(), "agent_model": config.AGENT_MODEL, "judge_model": config.JUDGE_MODEL,
            "docker_available": config.docker_available(), "max_concurrent_jobs": config.MAX_CONCURRENT_JOBS,
            "auth_required": bool(API_TOKEN), "login_required": config.REQUIRE_LOGIN,
            "database": {"engine": db.engine_name, "ok": db_ok, "ping_ms": db_ms}}


@app.get("/api/metrics")
async def metrics():
    """Rolling p50/p95 latency per pipeline stage + job counters (for the latency dashboard)."""
    assert manager is not None
    return {**METRICS.snapshot(), "jobs": manager.stats(), "instance": config.INSTANCE_ID}


app.include_router(platform_api.router)
app.include_router(platform_labs.router)


class SPAStaticFiles(StaticFiles):
    """Static files + single-page-app fallback: unknown non-API paths without an extension get index.html,
    so deep links such as /student/dashboard work on reload."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            last = path.rsplit("/", 1)[-1]
            if exc.status_code == 404 and not path.startswith(("api", "lb")) and "." not in last:
                return await super().get_response("index.html", scope)
            raise


app.mount("/", SPAStaticFiles(directory=WEB_DIR, html=True), name="web")
