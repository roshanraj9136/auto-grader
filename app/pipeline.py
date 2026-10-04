"""The grading DAG.

          ┌─ resolve (ls-remote) ─ cache_lookup ──► HIT: cancel clone, reuse report
 submit ──┤
          └─ clone (speculative, starts at t=0) ─┬─ index ─┬─ agent:code_quality ─┐
                                                 │         ├─ agent:architecture ─┤
                                                 │         ├─ agent:security ─────┼─ judge ─ report
                                                 │         ├─ agent:testing ──────┤
                                                 └─ docker (lint/build/run) ──────┴─ agent:devops

Critical path ≈ clone + max(index + slowest code agent, docker + devops agent) + judge.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone

from . import __version__, config
from .agents.judge import JudgeAgent
from .agents.llm import llm_enabled
from .agents.specialists import SPECIALISTS
from .ingest import git_ops
from .ingest.context import shared_context
from .ingest.indexer import build_index
from .jobs import Job
from .models import AgentReport, DockerResult, GradeReport, TokenUsage
from .report import store
from .report.render import render_html, render_markdown
from .sandbox import docker_runner
from .tracing import METRICS, Tracer


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def run_pipeline(job: Job) -> GradeReport:
    req = job.request
    tracer = Tracer(job.publish)
    work = config.JOBS_DIR / job.id
    repo_dir = work / "repo"
    notes: list[str] = []
    llm = llm_enabled()
    weights = req.rubric.weights
    background: list[asyncio.Task] = []
    try:
        # ---- Stage 1: speculative clone ‖ commit resolution ----------------------------
        clone_task = asyncio.create_task(
            tracer.run("clone", lambda: git_ops.shallow_clone(req.repo_url, req.ref, repo_dir)))
        background.append(clone_task)
        commit: str | None = None
        try:
            commit = await tracer.run("resolve", lambda: git_ops.resolve_commit(req.repo_url, req.ref))
        except git_ops.GitError as exc:
            notes.append(f"ls-remote failed ({exc}); relying on clone result.")

        key: str | None = None
        if req.force:
            tracer.skip("cache_lookup", "force re-grade requested")
        elif commit:
            async with tracer.stage("cache_lookup"):
                key = store.cache_key(req.repo_url, commit, req.dockerfile_text, req.rubric, llm)
                cached = await asyncio.to_thread(store.cache_get, key)
            if cached is not None:
                clone_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await clone_task
                METRICS.incr("cache_hits")
                notes.append("Result-cache hit (same commit, Dockerfile, rubric and models): speculative clone "
                             "cancelled and the stored verdict reused — grading is idempotent.")
                return await _finalize(job, tracer, cached.model_copy(update={"cache_hit": True}), notes, key=None)
            METRICS.incr("cache_misses")

        cloned_sha = await clone_task
        if commit and cloned_sha != commit and not cloned_sha.startswith(commit):
            notes.append(f"Branch moved between resolve ({commit[:10]}) and clone ({cloned_sha[:10]}); using clone.")
        commit = cloned_sha
        key = store.cache_key(req.repo_url, commit, req.dockerfile_text, req.rubric, llm)

        # ---- Stage 2: index ‖ docker sandbox --------------------------------------------
        index_task = asyncio.create_task(tracer.run("index", lambda: asyncio.to_thread(build_index, repo_dir)))
        docker_task: asyncio.Task | None = None
        if "devops" in weights:
            docker_task = asyncio.create_task(
                tracer.run("docker", lambda: docker_runner.evaluate(job.id, repo_dir, req.dockerfile_text)))
            background.append(docker_task)
        else:
            tracer.skip("docker", "devops dimension disabled by rubric")

        idx = await index_task
        stats = idx.stats()
        job.publish("index_ready", code_files=stats["code_files"], source_lines=stats["source_lines"],
                    languages=stats["languages"], stack=stats["stack"])
        shared = shared_context(idx, req.repo_url, commit, req.rubric.notes)

        async def docker_result() -> DockerResult:
            if docker_task is None:
                return DockerResult(skipped_reason="DevOps dimension disabled by rubric")
            try:
                return await docker_task
            except Exception as exc:  # noqa: BLE001
                return DockerResult(skipped_reason=f"Sandbox error: {exc}"[:300])

        # ---- Stage 3: specialist fan-out (DevOps waits only for docker) ---------------------
        async def run_agent(agent) -> AgentReport:
            docker = await docker_result() if agent.needs_docker else None
            rep = await tracer.run(f"agent:{agent.dimension}", lambda: agent.run(idx, shared, docker))
            job.publish("agent_done", dimension=agent.dimension, agent=agent.name, score=rep.score,
                        mode=rep.mode, latency_ms=rep.latency_ms, error=rep.error)
            return rep

        active = [a for a in SPECIALISTS if a.dimension in weights]
        reports = list(await asyncio.gather(*(run_agent(a) for a in active)))
        docker = await docker_result()

        # ---- Stage 4: judge ----------------------------------------------------------------
        verdict = await tracer.run("judge", lambda: JudgeAgent().run(reports, req.rubric, stats, docker))
        job.publish("judge_done", final_score=verdict.final_score, grade=verdict.grade, mode=verdict.mode)

        tokens = TokenUsage()
        for r in reports:
            tokens = tokens + r.tokens
        tokens = tokens + verdict.tokens
        if any(r.mode == "heuristic-fallback" for r in reports) or verdict.mode == "heuristic-fallback":
            notes.append("One or more agents hit an error/timeout and degraded to the heuristic scorer "
                         "(see agent cards); the job still completed within its latency budget.")

        report = GradeReport(
            job_id=job.id, repo_url=req.repo_url, ref=req.ref, commit_sha=commit, created_at=_now(),
            autograder_version=__version__, agent_model=config.AGENT_MODEL if llm else "heuristic",
            judge_model=config.JUDGE_MODEL if llm else "heuristic", llm_mode=llm, repo_stats=stats,
            docker=docker, agents=reports, verdict=verdict, timings=[], critical_path=[], total_ms=0, tokens=tokens,
        )
        return await _finalize(job, tracer, report, notes, key=key)
    finally:
        # Never leave a clone/docker build running for a failed job, then free the disk.
        for t in background:
            if not t.done():
                t.cancel()
        await asyncio.gather(*background, return_exceptions=True)
        await asyncio.to_thread(git_ops.remove_tree, work)


async def _finalize(job: Job, tracer: Tracer, report: GradeReport, notes: list[str], key: str | None) -> GradeReport:
    """Stamp timings/critical path, render artifacts, persist; `key` set => store in result cache."""
    async with tracer.stage("report"):
        if key:
            await asyncio.to_thread(store.cache_put, key, report)
    total = max(1, tracer.now_ms())
    seq = tracer.sequential_ms()
    report = report.model_copy(update={
        "job_id": job.id,
        "created_at": _now(),
        "timings": sorted(tracer.timings, key=lambda t: (t.start_ms, t.name)),
        "critical_path": tracer.critical_path("report"),
        "total_ms": total,
        "sequential_ms": seq,
        "speedup": round(seq / total, 2),
        "pipeline_notes": notes,
    })
    md, html = render_markdown(report), render_html(report)
    await asyncio.to_thread(store.save_artifacts, report, md, html)
    return report
