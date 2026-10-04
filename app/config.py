"""Central configuration, read from environment / .env."""
from __future__ import annotations

import os
import shutil
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
