"""Docker sandbox: lint -> build -> smoke-run, all bounded by timeouts.

Runs concurrently with indexing and the four code-reading agents; only the DevOps agent waits
for it. The smoke run is locked down (no network, capped memory/CPU/PIDs, no capabilities).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from .. import config
from ..ingest.indexer import SKIP_DIRS
from ..models import DockerResult
from ..proc import arun
from . import dockerfile_lint

UPLOADED_NAME = ".autograder.Dockerfile"
_DOCKER_ENV = {"DOCKER_BUILDKIT": "1", "BUILDKIT_PROGRESS": "plain"}


def find_dockerfiles(repo_dir: Path, max_depth: int = 3) -> list[Path]:
    """All Dockerfiles up to `max_depth`, root first, then shallowest/alphabetical."""
    found: list[tuple[int, str]] = []
    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        depth = len(Path(dirpath).relative_to(repo_dir).parts)
        if depth >= max_depth:
            dirnames[:] = []
        for fn in filenames:
            if fn == "Dockerfile" or (fn.startswith("Dockerfile.") and fn != UPLOADED_NAME):
                found.append((depth, os.path.join(dirpath, fn)))
    return [Path(p) for _, p in sorted(found)]


def _tail(text: str, n: int = 3500) -> str:
    return text if len(text) <= n else "…" + text[-n:]


async def evaluate(job_id: str, repo_dir: Path, uploaded_text: str | None) -> DockerResult:
    res = DockerResult()
    repo_dockerfiles = await asyncio.to_thread(find_dockerfiles, repo_dir)
    if uploaded_text and uploaded_text.strip():
        uploaded_text = uploaded_text.lstrip("\ufeff")
        dockerfile = repo_dir / UPLOADED_NAME
        dockerfile.write_text(uploaded_text, encoding="utf-8")
        context = repo_dir
        res.dockerfile_source, res.dockerfile_path = "uploaded", "(uploaded Dockerfile)"
        others = repo_dockerfiles
    else:
        if not repo_dockerfiles:
            res.skipped_reason = "No Dockerfile uploaded or found in the repository"
            return res
        dockerfile, others = repo_dockerfiles[0], repo_dockerfiles[1:]
        context = dockerfile.parent
        res.dockerfile_source = "repo"
        res.dockerfile_path = dockerfile.relative_to(repo_dir).as_posix()

    text = dockerfile.read_text(encoding="utf-8", errors="replace")[: config.MAX_DOCKERFILE_BYTES]
    res.dockerfile_text = text
    res.lint = dockerfile_lint.lint(text, has_dockerignore=(context / ".dockerignore").is_file())
    for f in res.lint:
        f.file = res.dockerfile_path
    # Multi-service repos: statically lint every other service Dockerfile too (~1 ms each).
    for other in others[:6]:
        rel = other.relative_to(repo_dir).as_posix()
        res.other_dockerfiles.append(rel)
        try:
            other_text = other.read_text(encoding="utf-8", errors="replace")[: config.MAX_DOCKERFILE_BYTES]
        except OSError:
            continue
        for f in dockerfile_lint.lint(other_text, has_dockerignore=(other.parent / ".dockerignore").is_file()):
            if f.severity in ("critical", "high", "medium"):
                f.file = rel
                f.title = f"{f.title} [{rel}]"
                res.lint.append(f)

    if not await asyncio.to_thread(config.docker_available):
        res.skipped_reason = ("Docker sandbox disabled by configuration" if not config.ENABLE_DOCKER
                              else "Docker daemon not available on the grading host; static analysis only")
        return res

    tag = f"autograder-{job_id[:12]}:latest"
    name = f"autograder-run-{job_id[:12]}"
    try:
        res.attempted_build = True
        build = await arun(
            ["docker", "build", "-f", str(dockerfile), "-t", tag, "--label", f"autograder.job={job_id}", str(context)],
            timeout=config.DOCKER_BUILD_TIMEOUT_S, env=_DOCKER_ENV, max_output=400_000,
        )
        res.build_seconds = round(build.duration_s, 1)
        res.build_ok = build.ok
        res.build_log_tail = _tail((build.stdout + "\n" + build.stderr).strip())
        if build.timed_out:
            res.build_log_tail += f"\n[autograder] build exceeded {config.DOCKER_BUILD_TIMEOUT_S}s and was killed"
        if not build.ok:
            return res

        size = await arun(["docker", "image", "inspect", "-f", "{{.Size}}", tag], timeout=20)
        if size.ok and size.stdout.strip().isdigit():
            res.image_size_mb = round(int(size.stdout.strip()) / 1_048_576, 1)

        res.attempted_run = True
        run = await arun(
            ["docker", "run", "-d", "--name", name, "--network", "none", "--memory", "512m", "--cpus", "1",
             "--pids-limit", "256", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", tag],
            timeout=60,
        )
        if not run.ok:
            res.run_ok = False
            res.run_log_tail = _tail(run.stderr.strip())
            return res
        await asyncio.sleep(config.DOCKER_RUN_WAIT_S)
        state = await arun(["docker", "inspect", "-f", "{{.State.Running}} {{.State.ExitCode}} {{.State.OOMKilled}}", name], timeout=20)
        logs = await arun(["docker", "logs", "--tail", "80", name], timeout=20)
        running, exit_code, oom = (state.stdout.split() + ["", "", ""])[:3]
        res.run_ok = running == "true" or exit_code == "0"
        summary = f"[autograder] after {config.DOCKER_RUN_WAIT_S}s: running={running} exit_code={exit_code} oom_killed={oom}"
        res.run_log_tail = _tail(f"{logs.stdout}\n{logs.stderr}".strip() + "\n" + summary, 2500)
        return res
    finally:
        # Best-effort cleanup; never let it mask the result.
        await arun(["docker", "rm", "-f", name], timeout=30)
        await arun(["docker", "rmi", "-f", tag], timeout=60)
