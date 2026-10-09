"""Central configuration, read from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
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
# Free model APIs (OpenAI-compatible), used as a chain: the first provider answers while it has quota; when it is
# rate-limited or out of its daily quota, the call moves to the next one, so a review keeps running on free tiers.
#   GEMINI_API_KEY  Google Gemini free tier (aistudio.google.com/apikey): large quotas, used first.
#   GROQ_API_KEY    Groq free tier (console.groq.com/keys): fast, ~8k tokens per minute per model; the backup.
#   AUTOGRADER_LLM_API_KEY  either kind of key (recognised by its prefix), or any other OpenAI-compatible API
#                   together with AUTOGRADER_LLM_BASE_URL (e.g. OpenRouter https://openrouter.ai/api/v1).
# Order: AUTOGRADER_LLM_ORDER (default "gemini,groq,custom"). Anthropic (Claude) is used instead of the chain when
# ANTHROPIC_API_KEY is set, unless AUTOGRADER_LLM_PROVIDER=openai.
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


@dataclass(frozen=True)
class LLMProvider:
    name: str
    base_url: str
    api_key: str
    agent_models: tuple[str, ...]  # the five specialists are spread over these, round-robin
    judge_model: str
    max_prompt_chars: int = 0      # 0 = no limit; prompts are shortened (middle cut) to fit small free tiers


# On Gemini's free tier, Flash-Lite answers a reviewer call in about 2 s and Flash in about 4 s (reasoning effort
# "low"). Groq's free tier allows ~8k tokens per minute per model, so its reviewers are spread over two models and
# prompts are capped (Qwen on Groq was also tried: it produced invalid tool calls too often).
_PRESETS = {
    "gemini": dict(base_url=GEMINI_BASE_URL, agent_models=("gemini-3.1-flash-lite",), judge_model="gemini-3.5-flash"),
    "groq": dict(base_url=GROQ_BASE_URL, agent_models=("openai/gpt-oss-20b", "openai/gpt-oss-120b"),
                 judge_model="openai/gpt-oss-120b", max_prompt_chars=12_000),
}


def _env_list(name: str) -> tuple[str, ...]:
    return tuple(m.strip() for m in os.getenv(name, "").split(",") if m.strip())


def _build_chain() -> list[LLMProvider]:
    keys: dict[str, str] = {}
    if os.getenv("GEMINI_API_KEY", "").strip():
        keys["gemini"] = os.getenv("GEMINI_API_KEY", "").strip()
    if os.getenv("GROQ_API_KEY", "").strip():
        keys["groq"] = os.getenv("GROQ_API_KEY", "").strip()
    generic = os.getenv("AUTOGRADER_LLM_API_KEY", "").strip()
    base = os.getenv("AUTOGRADER_LLM_BASE_URL", "").strip().rstrip("/")
    if generic:
        kind = "custom" if base else "groq" if generic.startswith("gsk_") else "gemini"
        keys.setdefault(kind, generic)
    order = [k.strip() for k in os.getenv("AUTOGRADER_LLM_ORDER", "gemini,groq,custom").split(",") if k.strip()]
    order += [k for k in ("gemini", "groq", "custom") if k not in order]
    chain: list[LLMProvider] = []
    for kind in order:
        if kind not in keys:
            continue
        if kind == "custom":
            host = base.split("//")[-1].split("/")[0]
            chain.append(LLMProvider(name=host, base_url=base, api_key=keys[kind],
                                     agent_models=_env_list("AUTOGRADER_AGENT_MODEL") or ("gpt-4o-mini",),
                                     judge_model=os.getenv("AUTOGRADER_JUDGE_MODEL", "").strip() or "gpt-4o-mini"))
        else:
            chain.append(LLMProvider(name=kind, api_key=keys[kind], **_PRESETS[kind]))
    # AUTOGRADER_AGENT_MODEL / AUTOGRADER_JUDGE_MODEL override the first provider's models (empty = its defaults).
    if chain and chain[0].name in _PRESETS:
        first = chain[0]
        chain[0] = LLMProvider(name=first.name, base_url=first.base_url, api_key=first.api_key,
                               agent_models=_env_list("AUTOGRADER_AGENT_MODEL") or first.agent_models,
                               judge_model=os.getenv("AUTOGRADER_JUDGE_MODEL", "").strip() or first.judge_model,
                               max_prompt_chars=first.max_prompt_chars)
    return chain


LLM_CHAIN = _build_chain()
LLM_PROVIDER = os.getenv("AUTOGRADER_LLM_PROVIDER", "").strip().lower()  # "", "anthropic" or "openai"
if not LLM_PROVIDER:
    LLM_PROVIDER = "anthropic" if ANTHROPIC_API_KEY else ("openai" if LLM_CHAIN else "")
_ANTHROPIC = LLM_PROVIDER == "anthropic"
# Only Groq on its own: build smaller prompts up front instead of shortening them per call.
_SMALL_CONTEXT = not _ANTHROPIC and bool(LLM_CHAIN) and LLM_CHAIN[0].max_prompt_chars > 0
# Labels for health checks and reports.
if _ANTHROPIC:
    AGENT_MODEL = os.getenv("AUTOGRADER_AGENT_MODEL", "").strip() or "claude-sonnet-5-5"
    JUDGE_MODEL = os.getenv("AUTOGRADER_JUDGE_MODEL", "").strip() or "claude-sonnet-5-5"
elif LLM_CHAIN:
    AGENT_MODEL = " then ".join(f"{p.name}: {', '.join(p.agent_models)}" for p in LLM_CHAIN)
    JUDGE_MODEL = " then ".join(f"{p.name}: {p.judge_model}" for p in LLM_CHAIN)
else:
    AGENT_MODEL = JUDGE_MODEL = "heuristic"
# OpenAI-compatible APIs: optional reasoning effort for "thinking" models (e.g. "low"); empty = provider default.
LLM_REASONING_EFFORT = os.getenv("AUTOGRADER_LLM_REASONING_EFFORT", "low").strip()
AGENT_MAX_TOKENS = int(os.getenv("AUTOGRADER_AGENT_MAX_TOKENS", "1500"))  # output tokens dominate LLM latency
JUDGE_MAX_TOKENS = int(os.getenv("AUTOGRADER_JUDGE_MAX_TOKENS", "1600"))
EFFORT = os.getenv("AUTOGRADER_EFFORT", "").strip()  # optional: low|medium|high (sent only if set)
# Global cap on in-flight LLM calls. Free tiers allow only a few requests per minute, so stay gentle there.
LLM_CONCURRENCY = int(os.getenv("AUTOGRADER_LLM_CONCURRENCY", "").strip() or ("8" if _ANTHROPIC else "4"))
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
# ---- Sign in with Google (optional) -----------------------------------------
# Credentials from a Google Cloud OAuth 2.0 "Web application" client. The redirect URI registered there must be
# <your site>/api/auth/google/callback. GOOGLE_ALLOWED_DOMAIN restricts who may sign in: with "iitbhilai.ac.in"
# only @iitbhilai.ac.in addresses are accepted, so the class stays closed to outsiders. Empty = anyone with a
# Google account, which is only sensible for a private deployment.
GOOGLE_CLIENT_ID = os.getenv("AUTOGRADER_GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("AUTOGRADER_GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_ALLOWED_DOMAIN = os.getenv("AUTOGRADER_GOOGLE_ALLOWED_DOMAIN", "").strip().lower().lstrip("@")


def google_enabled() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


CLIENT_IP_HEADER = os.getenv("AUTOGRADER_CLIENT_IP_HEADER", "").strip().lower()        # optional class join code for self sign-up
INSTRUCTOR_EMAIL = os.getenv("AUTOGRADER_INSTRUCTOR_EMAIL", "").strip().lower()
INSTRUCTOR_PASSWORD = os.getenv("AUTOGRADER_INSTRUCTOR_PASSWORD", "")

# ---- Context budgets (characters, ~4 chars/token) ---------------------------
# Smaller when Groq's free tier comes first, where one minute allows only ~8k tokens per model.
SHARED_CONTEXT_CHARS = int(os.getenv("AUTOGRADER_SHARED_CONTEXT_CHARS", "3500" if _SMALL_CONTEXT else "18000"))  # same for all specialists
AGENT_SLICE_CHARS = int(os.getenv("AUTOGRADER_AGENT_SLICE_CHARS", "4500" if _SMALL_CONTEXT else "32000"))      # agent-specific evidence
PER_FILE_CHARS = int(os.getenv("AUTOGRADER_PER_FILE_CHARS", "1800" if _SMALL_CONTEXT else "6000"))
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


def dimension_index(dimension: str | None) -> int:
    """Position in rubric order, used to spread specialists over several models."""
    order = list(DEFAULT_WEIGHTS)
    return order.index(dimension) if dimension in order else 0
