"""Job lifecycle: admission control, single-flight de-duplication, live event fan-out."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import AsyncIterator, Literal

from . import config
from .models import GradeReport, GradeRequest
from .tracing import METRICS

log = logging.getLogger("autograder.jobs")

JobStatus = Literal["queued", "running", "done", "failed"]
TERMINAL_EVENTS = {"job_done", "job_failed"}


def request_fingerprint(req: GradeRequest) -> str:
    payload = json.dumps(
        {
            "repo": req.repo_url,
            "ref": req.ref,
            "dockerfile": hashlib.sha256((req.dockerfile_text or "").encode()).hexdigest(),
            "rubric": req.rubric.model_dump(),
            "force": req.force,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class Job:
    def __init__(self, req: GradeRequest) -> None:
        self.id = uuid.uuid4().hex
        self.request = req
        self.fingerprint = request_fingerprint(req)
        self.status: JobStatus = "queued"
        self.created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.error: str | None = None
        self.report: GradeReport | None = None
        self.events: list[dict] = []
        self._subscribers: set[asyncio.Queue] = set()
        self._t0 = time.perf_counter()

    # Events are published only from the event-loop thread, so no locking is needed.
    def publish(self, type_: str, **data) -> None:
        evt = {"seq": len(self.events), "type": type_, "t_ms": int((time.perf_counter() - self._t0) * 1000), **data}
        self.events.append(evt)
        for q in self._subscribers:
            q.put_nowait(evt)

    async def stream(self, heartbeat_s: float = 15.0) -> AsyncIterator[dict | None]:
        """Replay history then follow live events; yields None as a heartbeat tick."""
        q: asyncio.Queue = asyncio.Queue()
        for evt in self.events:  # replay + subscribe happen without an await in between: no race
            q.put_nowait(evt)
        self._subscribers.add(q)
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=heartbeat_s)
                except asyncio.TimeoutError:
                    yield None
                    continue
                yield evt
                if evt["type"] in TERMINAL_EVENTS:
                    return
        finally:
            self._subscribers.discard(q)

    def summary(self) -> dict:
        out = {
            "job_id": self.id,
            "status": self.status,
            "repo_url": self.request.repo_url,
            "ref": self.request.ref,
            "created_at": self.created_at,
            "error": self.error,
            "events": len(self.events),
        }
        if self.report:
            out.update(
                final_score=self.report.verdict.final_score,
                grade=self.report.verdict.grade,
                total_ms=self.report.total_ms,
                cache_hit=self.report.cache_hit,
            )
        return out


class JobManager:
    """Bounded job store + admission control.

    * `MAX_CONCURRENT_JOBS` semaphore keeps docker builds / LLM fan-out from overloading the host;
      extra jobs wait in FIFO order and see a `queued` event immediately.
    * Single-flight: an identical request that is already queued/running is attached to the
      existing job instead of doing the work twice.
    """

    def __init__(self) -> None:
        self.jobs: OrderedDict[str, Job] = OrderedDict()
        self._inflight: dict[str, str] = {}
        self._sem = asyncio.Semaphore(config.MAX_CONCURRENT_JOBS)
        self._tasks: set[asyncio.Task] = set()
        self._waiting = 0

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def submit(self, req: GradeRequest) -> tuple[Job, bool]:
        fp = request_fingerprint(req)
        existing_id = self._inflight.get(fp)
        if existing_id and existing_id in self.jobs:
            METRICS.incr("jobs_deduplicated")
            return self.jobs[existing_id], True

        job = Job(req)
        self.jobs[job.id] = job
        self._inflight[fp] = job.id
        while len(self.jobs) > config.MAX_STORED_JOBS:
            old_id, old = next(iter(self.jobs.items()))
            if old.status in ("queued", "running"):
                break
            self.jobs.pop(old_id)
        METRICS.incr("jobs_submitted")
        job.publish("queued", position=self._waiting)
        task = asyncio.create_task(self._run(job), name=f"job-{job.id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job, False

    async def _run(self, job: Job) -> None:
        from .pipeline import run_pipeline  # local import avoids a cycle

        self._waiting += 1
        acquired = False
        try:
            async with self._sem:
                self._waiting -= 1
                acquired = True
                job.status = "running"
                job.publish("job_started")
                try:
                    job.report = await run_pipeline(job)
                    job.status = "done"
                    METRICS.incr("jobs_done")
                    METRICS.observe("job_total", job.report.total_ms)
                    job.publish(
                        "job_done",
                        final_score=job.report.verdict.final_score,
                        grade=job.report.verdict.grade,
                        total_ms=job.report.total_ms,
                        cache_hit=job.report.cache_hit,
                    )
                except Exception as exc:  # noqa: BLE001 - surface any failure to the client
                    log.exception("job %s failed", job.id)
                    job.status = "failed"
                    job.error = str(exc) or exc.__class__.__name__
                    METRICS.incr("jobs_failed")
                    job.publish("job_failed", error=job.error)
        finally:
            if not acquired:
                self._waiting -= 1
            if self._inflight.get(job.fingerprint) == job.id:
                self._inflight.pop(job.fingerprint, None)

    async def shutdown(self) -> None:
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def stats(self) -> dict:
        by_status: dict[str, int] = {}
        for j in self.jobs.values():
            by_status[j.status] = by_status.get(j.status, 0) + 1
        return {"stored": len(self.jobs), "waiting_for_slot": self._waiting, "by_status": by_status}
