"""Persistence: content-addressed result cache + per-job report artifacts on disk."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from .. import __version__, config
from ..models import GradeReport, Rubric

REPORTS_DIR = config.WORK_DIR / "reports"
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def cache_key(repo_url: str, commit: str, dockerfile_text: str | None, rubric: Rubric, llm_mode: bool) -> str:
    """Same commit + same Dockerfile + same rubric + same models => same report (idempotent grading)."""
    payload = json.dumps({
        "v": __version__, "repo": repo_url, "commit": commit,
        "dockerfile": hashlib.sha256((dockerfile_text or "").encode()).hexdigest(),
        "rubric": rubric.model_dump(), "llm": llm_mode,
        "models": [config.AGENT_MODEL, config.JUDGE_MODEL] if llm_mode else [],
        "docker": config.docker_available(),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    """Write to a unique temp file then rename: replicas sharing the volume never clobber each other's temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def cache_get(key: str) -> GradeReport | None:
    path = config.CACHE_DIR / f"{key}.json"
    if not path.is_file():
        return None
    try:
        return GradeReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cache_put(key: str, report: GradeReport) -> None:
    _atomic_write(config.CACHE_DIR / f"{key}.json", report.model_dump_json())


def save_artifacts(report: GradeReport, markdown: str, html: str) -> None:
    base = REPORTS_DIR / report.job_id
    _atomic_write(base.with_suffix(".json"), report.model_dump_json(indent=1))
    _atomic_write(base.with_suffix(".md"), markdown)
    _atomic_write(base.with_suffix(".html"), html)


def artifact_path(job_id: str, ext: str) -> Path | None:
    if not _JOB_ID_RE.match(job_id) or ext not in ("json", "md", "html"):
        return None  # also prevents path traversal
    p = REPORTS_DIR / f"{job_id}.{ext}"
    return p if p.is_file() else None
