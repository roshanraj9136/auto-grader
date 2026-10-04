"""Central configuration, read from environment / .env."""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---- LLM -------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
# Model tiering: specialists and judge can use different models (latency vs. depth trade-off).
AGENT_MODEL = os.getenv("AUTOGRADER_AGENT_MODEL", "claude-sonnet-5-5")
JUDGE_MODEL = os.getenv("AUTOGRADER_JUDGE_MODEL", "claude-sonnet-5-5")
AGENT_MAX_TOKENS = int(os.getenv("AUTOGRADER_AGENT_MAX_TOKENS", "1500"))  # output tokens dominate LLM latency
JUDGE_MAX_TOKENS = int(os.getenv("AUTOGRADER_JUDGE_MAX_TOKENS", "1600"))
EFFORT = os.getenv("AUTOGRADER_EFFORT", "").strip()  # optional: low|medium|high (sent only if set)
LLM_CONCURRENCY = int(os.getenv("AUTOGRADER_LLM_CONCURRENCY", "8"))   # global cap on in-flight LLM calls
LLM_MAX_RETRIES = int(os.getenv("AUTOGRADER_LLM_MAX_RETRIES", "2"))
AGENT_TIMEOUT_S = float(os.getenv("AUTOGRADER_AGENT_TIMEOUT", "120"))  # hard deadline per specialist
JUDGE_TIMEOUT_S = float(os.getenv("AUTOGRADER_JUDGE_TIMEOUT", "150"))

# ---- Docker sandbox --------------------------------------------------------
ENABLE_DOCKER = os.getenv("AUTOGRADER_ENABLE_DOCKER", "1") == "1"
DOCKER_BUILD_TIMEOUT_S = int(os.getenv("AUTOGRADER_DOCKER_BUILD_TIMEOUT", "600"))
DOCKER_RUN_WAIT_S = int(os.getenv("AUTOGRADER_DOCKER_RUN_WAIT", "8"))

# ---- Jobs / storage --------------------------------------------------------
MAX_CONCURRENT_JOBS = int(os.getenv("AUTOGRADER_MAX_CONCURRENT_JOBS", "2"))
MAX_STORED_JOBS = int(os.getenv("AUTOGRADER_MAX_STORED_JOBS", "200"))
WORK_DIR = Path(os.getenv("AUTOGRADER_WORK_DIR", str(Path(tempfile.gettempdir()) / "autograder")))
CACHE_DIR = WORK_DIR / "cache"
CLONE_TIMEOUT_S = int(os.getenv("AUTOGRADER_CLONE_TIMEOUT", "120"))

# ---- Replica identity ------------------------------------------------------
# Several API replicas can share one /data volume behind the load balancer. Each replica keeps its
# in-flight clones in its own sub-directory, so one replica's startup purge never deletes another's work.
# Containers run the app as PID 1, so the container hostname is unique; on a dev machine two processes
# share a hostname, so the PID is appended.
_host = re.sub(r"[^A-Za-z0-9_.-]", "-", socket.gethostname())[:50] or "local"
INSTANCE_ID = (os.getenv("AUTOGRADER_INSTANCE_ID", "").strip()[:63]
               or (_host if os.getpid() == 1 else f"{_host}-{os.getpid()}"))
JOBS_DIR = WORK_DIR / "jobs" / INSTANCE_ID
HEARTBEAT_S = 20          # replicas refresh instances.last_seen this often
INSTANCE_DEAD_S = 90      # ...and are presumed dead (their unfinished submissions failed) after this

# ---- Learning platform (accounts, assignments, dashboards, labs) ------------
# sqlite:///path (default, zero setup) or postgresql://user:pass@host:5432/db (docker compose).
DATABASE_URL = os.getenv("AUTOGRADER_DATABASE_URL", "").strip() or f"sqlite:///{(WORK_DIR / 'autograder.db').as_posix()}"
REQUIRE_LOGIN = os.getenv("AUTOGRADER_REQUIRE_LOGIN", "1") == "1"   # grading needs a session or the API token
DEMO_SEED = os.getenv("AUTOGRADER_DEMO_SEED", "1") == "1"           # demo accounts + sample assignments on first run
SESSION_TTL_HOURS = int(os.getenv("AUTOGRADER_SESSION_TTL_HOURS", "72"))
COOKIE_SECURE = os.getenv("AUTOGRADER_COOKIE_SECURE", "0") == "1"   # set to 1 behind HTTPS
SIGNUP_CODE = os.getenv("AUTOGRADER_SIGNUP_CODE", "").strip()        # optional class join code for self sign-up
INSTRUCTOR_EMAIL = os.getenv("AUTOGRADER_INSTRUCTOR_EMAIL", "").strip().lower()
INSTRUCTOR_PASSWORD = os.getenv("AUTOGRADER_INSTRUCTOR_PASSWORD", "")

# ---- Context budgets (characters, ~4 chars/token) ---------------------------
SHARED_CONTEXT_CHARS = 18_000   # identical for all specialists -> prompt-cached
AGENT_SLICE_CHARS = 32_000      # agent-specific evidence
PER_FILE_CHARS = 6_000
MAX_INDEXED_FILES = 5_000
MAX_READ_BYTES = 200_000        # files bigger than this are listed but not read

# ---- Input limits ----------------------------------------------------------
MAX_DOCKERFILE_BYTES = 100_000
MAX_RUBRIC_CHARS = 10_000

DEFAULT_WEIGHTS = {
    "code_quality": 0.25,
    "architecture": 0.25,
    "security": 0.15,
    "testing": 0.20,
    "devops": 0.15,
}


@lru_cache(maxsize=1)
def docker_available() -> bool:
    """True only if docker is enabled, installed, and the daemon responds."""
    if not ENABLE_DOCKER or shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(["docker", "info"], capture_output=True, timeout=15)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
