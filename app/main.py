"""HTTP layer: REST + Server-Sent Events. Stateless apart from the in-process job manager."""
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

from . import __version__, config
from .agents.llm import llm_enabled
from .ingest import git_ops
from .jobs import JobManager
from .models import GradeRequest, Rubric
from .report import store
from .tracing import METRICS

logging.basicConfig(level=os.getenv("AUTOGRADER_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("autograder")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
API_TOKEN = os.getenv("AUTOGRADER_API_TOKEN", "").strip()

manager: JobManager | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global manager
    for d in (config.WORK_DIR / "jobs", config.CACHE_DIR, store.REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    # Remove clones orphaned by a previous crash.
    for stale in (config.WORK_DIR / "jobs").iterdir():
        await asyncio.to_thread(git_ops.remove_tree, stale)
    docker_ok = await asyncio.to_thread(config.docker_available)  # warm the cached probe off the event loop
    manager = JobManager()
    log.info("AutoGrader %s ready | llm=%s agent_model=%s judge_model=%s docker=%s",
             __version__, llm_enabled(), config.AGENT_MODEL, config.JUDGE_MODEL, docker_ok)
    yield
    await manager.shutdown()


app = FastAPI(title="AutoGrader", version=__version__, lifespan=lifespan,
              description="Multi-agent (5 specialists + judge) grader for full-stack GitHub projects.")


def require_token(authorization: str | None = Header(default=None)) -> None:
    """Optional bearer-token guard for job submission (enable with AUTOGRADER_API_TOKEN)."""
    if not API_TOKEN:
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, API_TOKEN):
        raise HTTPException(status_code=401, detail="invalid or missing API token")


class GradeIn(BaseModel):
    repo_url: str = Field(examples=["https://github.com/owner/repo"])
    ref: str | None = Field(default=None, description="branch, tag or commit SHA (default branch if omitted)")
    dockerfile_text: str | None = Field(default=None, max_length=config.MAX_DOCKERFILE_BYTES)
    weights: dict[str, float] | None = Field(default=None, description=f"subset of {list(config.DEFAULT_WEIGHTS)}")
    rubric_notes: str = Field(default="", max_length=config.MAX_RUBRIC_CHARS)
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


def _submit(body: GradeIn) -> JSONResponse:
    assert manager is not None
    job, deduped = manager.submit(build_request(body))
    return JSONResponse(status_code=202, content={
        "job_id": job.id, "status": job.status, "deduplicated": deduped,
        "links": {"self": f"/api/jobs/{job.id}", "events": f"/api/jobs/{job.id}/events",
                  "report": f"/api/jobs/{job.id}/report", "html": f"/api/jobs/{job.id}/report.html",
                  "markdown": f"/api/jobs/{job.id}/report.md"},
    })


@app.post("/api/grade", status_code=202, dependencies=[Depends(require_token)])
async def grade(body: GradeIn):
    """Submit a grading job (JSON). Returns immediately; follow progress via SSE."""
    return _submit(body)


@app.post("/api/grade/upload", status_code=202, dependencies=[Depends(require_token)])
async def grade_upload(
    repo_url: str = Form(...),
    ref: str | None = Form(None),
    rubric_notes: str = Form(""),
    weights: str | None = Form(None, description="JSON object, e.g. {\"security\": 0.3, ...}"),
    force: bool = Form(False),
    dockerfile: UploadFile | None = File(None),
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
    return _submit(GradeIn(repo_url=repo_url, ref=ref, dockerfile_text=text, weights=parsed,
                           rubric_notes=rubric_notes, force=force))


@app.get("/api/jobs")
async def list_jobs(limit: int = 20):
    assert manager is not None
    jobs = list(manager.jobs.values())[-max(1, min(limit, 100)):]
    return [j.summary() for j in reversed(jobs)]


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    assert manager is not None
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {**job.summary(), "events_log": job.events[-200:]}


@app.get("/api/jobs/{job_id}/events")
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


@app.get("/api/jobs/{job_id}/report")
async def job_report(job_id: str):
    assert manager is not None
    job = manager.get(job_id)
    if job and job.report:
        return JSONResponse(json.loads(job.report.model_dump_json()))
    if job and job.status in ("queued", "running"):
        raise HTTPException(status_code=409, detail=f"job is {job.status}")
    path = store.artifact_path(job_id, "json")  # survives restarts / store eviction
    if not path:
        raise HTTPException(status_code=404, detail="report not found")
    return FileResponse(path, media_type="application/json")


@app.get("/api/jobs/{job_id}/report.{fmt}")
async def job_report_file(job_id: str, fmt: str):
    path = store.artifact_path(job_id, fmt)
    if not path:
        raise HTTPException(status_code=404, detail="report not found (yet)")
    media = {"md": "text/markdown; charset=utf-8", "html": "text/html; charset=utf-8", "json": "application/json"}[fmt]
    headers = {"Content-Disposition": f'attachment; filename="autograder-{job_id[:8]}.{fmt}"'} if fmt == "md" else None
    return FileResponse(path, media_type=media, headers=headers)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": __version__, "llm_mode": llm_enabled(),
            "agent_model": config.AGENT_MODEL, "judge_model": config.JUDGE_MODEL,
            "docker_available": config.docker_available(), "max_concurrent_jobs": config.MAX_CONCURRENT_JOBS,
            "auth_required": bool(API_TOKEN)}


@app.get("/api/metrics")
async def metrics():
    """Rolling p50/p95 latency per pipeline stage + job counters (for the latency dashboard)."""
    assert manager is not None
    return {**METRICS.snapshot(), "jobs": manager.stats()}


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
