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
# Any OpenAI-compatible chat API works too, including free tiers: Groq (free key at console.groq.com/keys),
# Google Gemini (aistudio.google.com/apikey) or OpenRouter (https://openrouter.ai/api/v1). A Groq key ("gsk_...")
# selects Groq's endpoint by itself; other keys default to Gemini's. Anthropic is used when ANTHROPIC_API_KEY is
# set, unless the provider is forced.
LLM_API_KEY = (os.getenv("AUTOGRADER_LLM_API_KEY", "") or os.getenv("GROQ_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")).strip()
_DEFAULT_BASE_URL = ("https://api.groq.com/openai/v1" if LLM_API_KEY.startswith("gsk_")
                     else "https://generativelanguage.googleapis.com/v1beta/openai")
LLM_BASE_URL = os.getenv("AUTOGRADER_LLM_BASE_URL", _DEFAULT_BASE_URL).strip().rstrip("/")
LLM_PROVIDER = os.getenv("AUTOGRADER_LLM_PROVIDER", "").strip().lower()  # "", "anthropic" or "openai"
if not LLM_PROVIDER:
    LLM_PROVIDER = "anthropic" if ANTHROPIC_API_KEY else ("openai" if LLM_API_KEY else "")
# Model tiering: specialists and judge can use different models (latency vs. depth trade-off). On Gemini's free
# tier, Flash-Lite answers a reviewer call in about 2 s and Flash in about 4 s (measured with reasoning effort "low").
# AUTOGRADER_AGENT_MODEL may list several models (comma-separated): the five specialists are spread over them.
# Groq's free tier allows about 8k tokens per minute per model, so its default spreads them over two models.
# (Qwen on Groq was also tried: it produced invalid tool calls too often.)
_ANTHROPIC = LLM_PROVIDER == "anthropic"
_GROQ = not _ANTHROPIC and "api.groq.com" in LLM_BASE_URL
# An empty setting (e.g. from docker compose's ${VAR:-}) means "use the provider's default".
AGENT_MODEL = os.getenv("AUTOGRADER_AGENT_MODEL", "").strip() or ("claude-sonnet-5-5" if _ANTHROPIC else (
    "openai/gpt-oss-20b,openai/gpt-oss-120b" if _GROQ else "gemini-3.1-flash-lite"))
AGENT_MODELS = [m.strip() for m in AGENT_MODEL.split(",") if m.strip()]
JUDGE_MODEL = os.getenv("AUTOGRADER_JUDGE_MODEL", "").strip() or ("claude-sonnet-5-5" if _ANTHROPIC else (
    "openai/gpt-oss-120b" if _GROQ else "gemini-3.5-flash"))
# OpenAI-compatible APIs: optional reasoning effort for "thinking" models (e.g. "low"); empty = provider default.
LLM_REASONING_EFFORT = os.getenv("AUTOGRADER_LLM_REASONING_EFFORT", "low").strip()
AGENT_MAX_TOKENS = int(os.getenv("AUTOGRADER_AGENT_MAX_TOKENS", "1500"))  # output tokens dominate LLM latency
JUDGE_MAX_TOKENS = int(os.getenv("AUTOGRADER_JUDGE_MAX_TOKENS", "1600"))
EFFORT = os.getenv("AUTOGRADER_EFFORT", "").strip()  # optional: low|medium|high (sent only if set)
# Global cap on in-flight LLM calls. Free tiers allow only a few requests per minute, so stay gentle there.
LLM_CONCURRENCY = int(os.getenv("AUTOGRADER_LLM_CONCURRENCY", "").strip() or ("8" if LLM_PROVIDER == "anthropic" else "3"))
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
SIGNUP_CODE = os.getenv("AUTOGRADER_SIGNUP_CODE", "").strip()
# Header set by the edge proxy with the real client IP (e.g. cf-connecting-ip on Render, behind Cloudflare). If unset,
# the right-most X-Forwarded-For entry is used: it is the one added by the closest proxy, so a client cannot forge it.
CLIENT_IP_HEADER = os.getenv("AUTOGRADER_CLIENT_IP_HEADER", "").strip().lower()        # optional class join code for self sign-up
INSTRUCTOR_EMAIL = os.getenv("AUTOGRADER_INSTRUCTOR_EMAIL", "").strip().lower()
INSTRUCTOR_PASSWORD = os.getenv("AUTOGRADER_INSTRUCTOR_PASSWORD", "")

# ---- Context budgets (characters, ~4 chars/token) ---------------------------
# Smaller on Groq's free tier, where one minute allows only ~8k tokens per model.
SHARED_CONTEXT_CHARS = int(os.getenv("AUTOGRADER_SHARED_CONTEXT_CHARS", "3500" if _GROQ else "18000"))  # same for all specialists
AGENT_SLICE_CHARS = int(os.getenv("AUTOGRADER_AGENT_SLICE_CHARS", "4500" if _GROQ else "32000"))      # agent-specific evidence
PER_FILE_CHARS = int(os.getenv("AUTOGRADER_PER_FILE_CHARS", "1800" if _GROQ else "6000"))
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


def agent_model(dimension: str) -> str:
    """The model a specialist uses: AGENT_MODELS are assigned round-robin in rubric order."""
    order = list(DEFAULT_WEIGHTS)
    i = order.index(dimension) if dimension in order else 0
    return AGENT_MODELS[i % len(AGENT_MODELS)]
