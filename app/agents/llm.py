"""Thin async LLM client: structured output via forced tool use, a global concurrency cap and retries.

Two kinds of provider behind one function (`call_tool`):
* Anthropic (Claude): forced tool use, prompt caching on the shared system block, SDK retries.
* A chain of free OpenAI-compatible APIs (Google Gemini first, then Groq, or any other): forced function calling.
  When a model is rate-limited or out of its daily quota, the call moves straight to the next model or provider,
  and that model is skipped by later calls until its wait is over. If nothing answers before the agent's
  deadline, the agent falls back to its rule-based scorer, so a grading never fails because of the model.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import time
import urllib.error
import urllib.request

from anthropic import AsyncAnthropic

from .. import config
from ..models import TokenUsage

_client: AsyncAnthropic | None = None
# Global cap on in-flight requests across *all* jobs: protects the rate limit so a burst of
# submissions degrades into queueing instead of a storm of 429 retries (which is slower).
_sem = asyncio.Semaphore(config.LLM_CONCURRENCY)


class LLMError(RuntimeError):
    pass


def llm_enabled() -> bool:
    if config.LLM_PROVIDER == "anthropic":
        return bool(config.ANTHROPIC_API_KEY)
    return config.LLM_PROVIDER == "openai" and bool(config.LLM_CHAIN)


def provider_label() -> str:
    """Human-readable provider(s) for health checks, e.g. 'gemini+groq' or 'anthropic'."""
    if not llm_enabled():
        return "heuristic"
    if config.LLM_PROVIDER == "anthropic":
        return "anthropic"
    return "+".join(p.name for p in config.LLM_CHAIN)


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(
            api_key=config.ANTHROPIC_API_KEY,
            max_retries=config.LLM_MAX_RETRIES,
            timeout=max(config.AGENT_TIMEOUT_S, config.JUDGE_TIMEOUT_S),
        )
    return _client


def cached_system(prefix: str, suffix: str) -> list[dict]:
    """System prompt as two blocks; the first (shared) block carries the cache breakpoint.

    Request layout = tools -> system[0] -> system[1] -> user. tools + system[0] are identical
    for all specialists of a job, so that prefix is cached once and re-read by the others.
    """
    return [
        {"type": "text", "text": prefix, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": suffix},
    ]


async def call_tool(*, role: str, dimension: str | None = None, system: list[dict], user: str, tool: dict,
                    max_tokens: int) -> tuple[dict, TokenUsage, str]:
    """Ask for one structured answer. role is "agent" (with its dimension) or "judge".
    Returns the tool arguments, token usage and which model answered ("provider/model")."""
    if config.LLM_PROVIDER == "openai":
        return await _call_chain(role=role, dimension=dimension, system=system, user=user, tool=tool,
                                 max_tokens=max_tokens)
    model = config.JUDGE_MODEL if role == "judge" else config.AGENT_MODEL
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": tool["name"]},
        "messages": [{"role": "user", "content": user}],
    }
    if config.EFFORT:
        kwargs["output_config"] = {"effort": config.EFFORT}
    async with _sem:
        resp = await _get_client().messages.create(**kwargs)
    u = resp.usage
    usage = TokenUsage(
        input=u.input_tokens or 0,
        output=u.output_tokens or 0,
        cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )
    if resp.stop_reason == "max_tokens":
        raise LLMError("structured output truncated at max_tokens")
    for block in resp.content:
        if block.type == "tool_use" and block.name == tool["name"]:
            return dict(block.input), usage, f"anthropic/{model}"
    raise LLMError("model did not return the structured tool call")


# ---------------------------------------------------------------------------- OpenAI-compatible APIs (chain)
_RETRY_STATUS = {500, 502, 503, 504}
# (provider, model) -> monotonic time until which it is rate-limited. Shared by every job in this process, so once a
# free quota runs out, later calls go straight to the next provider instead of asking again.
_cooldown: dict[tuple[str, str], float] = {}
_DAILY_COOLDOWN_S = 15 * 60  # daily quota used up: look again after a while (it resets once a day)
_UA = "autograder-plus/1.0 (+https://github.com/roshanraj9136/auto-grader)"


class _RateLimited(LLMError):
    def __init__(self, wait_s: float, daily: bool):
        super().__init__("rate limited" + (" (daily quota used up)" if daily else ""))
        self.wait_s = wait_s
        self.daily = daily


class _RejectedToolCall(LLMError):
    """The provider rejected the model's tool call as invalid (Groq: 400 tool_use_failed) and returned the raw
    generation, which is usually the right JSON with a small schema slip that our own parsing tolerates."""

    def __init__(self, generation: str):
        super().__init__("model produced an invalid tool call")
        self.generation = generation


def _post_once(provider: config.LLMProvider, body: bytes) -> tuple[int, str, str]:
    """One blocking POST (run in a worker thread): (status, retry-after header, response text)."""
    # A named User-Agent: some providers' firewalls (Groq's Cloudflare, error 1010) block Python's default one.
    req = urllib.request.Request(f"{provider.base_url}/chat/completions", data=body, method="POST", headers={
        "Authorization": f"Bearer {provider.api_key}", "Content-Type": "application/json", "User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=max(config.AGENT_TIMEOUT_S, config.JUDGE_TIMEOUT_S)) as resp:
            return resp.status, "", resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("retry-after", "") or "", exc.read().decode("utf-8", "replace")


def _salvage(generation: str) -> dict | None:
    """The arguments object from a rejected tool call, if it is readable JSON."""
    text = generation.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    for key in ("arguments", "parameters"):  # {"name": ..., "arguments": {...}} wrappers
        inner = obj.get(key)
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except json.JSONDecodeError:
                inner = None
        if isinstance(inner, dict):
            return inner
    return obj or None


def _rate_limit_wait(retry_after: str, text: str) -> tuple[float, bool]:
    """How long a 429 asks us to wait, and whether a *daily* quota is used up (Gemini: "PerDay" quota ids,
    Groq: "per day (RPD/TPD)"). Retry-After header first, then the hints providers put in the body."""
    daily = bool(re.search(r"PerDay|per day|\(RPD\)|\(TPD\)", text, re.I))
    for value in (retry_after,
                  *(m.group(1) for m in [re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', text),
                                         re.search(r"try again in (\d+(?:\.\d+)?)s", text)] if m)):
        try:
            return float(value), daily
        except (TypeError, ValueError):
            continue
    return (_DAILY_COOLDOWN_S if daily else 10.0), daily


async def _post(provider: config.LLMProvider, body: dict) -> dict:
    """POST with retries for transient errors. A 429 is not waited out here: it is raised so the chain can move on."""
    payload = json.dumps(body).encode()
    attempts = config.LLM_MAX_RETRIES + 1
    failures = 0
    while True:
        try:
            async with _sem:  # held only while a request is in flight, never while waiting
                status, retry_after, text = await asyncio.to_thread(_post_once, provider, payload)
        except (urllib.error.URLError, OSError) as exc:  # DNS, connection reset, timeout
            failures += 1
            if failures >= attempts:
                raise LLMError(f"{provider.name}: network error: {exc}") from exc
            await asyncio.sleep(2 ** failures + random.random())
            continue
        if status == 200:
            return json.loads(text)
        if status == 429:
            wait, daily = _rate_limit_wait(retry_after, text)
            raise _RateLimited(_DAILY_COOLDOWN_S if daily else wait, daily)
        if status == 400 and "failed_generation" in text:
            try:
                generation = (json.loads(text).get("error") or {}).get("failed_generation") or ""
            except (json.JSONDecodeError, AttributeError):
                generation = ""
            raise _RejectedToolCall(str(generation))
        # Groq answers 400 "tool_use_failed" when a model produced a malformed tool call; a second try usually works.
        if status in _RETRY_STATUS or (status == 400 and "tool_use_failed" in text):
            failures += 1
            if failures < attempts:
                await asyncio.sleep(2 ** failures + random.random())
                continue
        # Never echo the request (it carries the key in a header, and student code in the body).
        raise LLMError(f"{provider.name} returned HTTP {status}: {text[:200]}")


def _cut_middle(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    tail = max(limit - head - 40, 0)
    return f"{text[:head]}\n\n… [{len(text) - head - tail} chars omitted] …\n\n{text[len(text) - tail:]}"


def _fit(system: str, user: str, limit: int) -> tuple[str, str]:
    """Shorten both prompts proportionally (keeping their beginnings and ends) to fit a small free tier."""
    total = len(system) + len(user)
    if not limit or total <= limit:
        return system, user
    ratio = limit / total
    return _cut_middle(system, max(1500, int(len(system) * ratio))), _cut_middle(user, max(1500, int(len(user) * ratio)))


def _candidates(role: str, dimension: str | None) -> list[tuple[config.LLMProvider, str]]:
    """Every (provider, model) to try, best first: providers in chain order; within one, the model this call
    normally uses first (specialists are spread round-robin), then that provider's other models."""
    out: list[tuple[config.LLMProvider, str]] = []
    for p in config.LLM_CHAIN:
        if role == "judge":
            models = [p.judge_model] + [m for m in p.agent_models if m != p.judge_model]
        else:
            i = config.dimension_index(dimension) % len(p.agent_models)
            models = list(p.agent_models[i:] + p.agent_models[:i])
            models += [p.judge_model] if p.judge_model not in models else []
        out += [(p, m) for m in models]
    return out


async def _call_one(provider: config.LLMProvider, model: str, *, system: list[dict], user: str, tool: dict,
                    max_tokens: int) -> tuple[dict, TokenUsage]:
    system_text, user = _fit("\n\n".join(b["text"] for b in system), user, provider.max_prompt_chars)
    body: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "messages": [{"role": "system", "content": system_text}, {"role": "user", "content": user}],
        "tools": [{"type": "function", "function": {
            "name": tool["name"], "description": tool.get("description", ""), "parameters": tool["input_schema"]}}],
        "tool_choice": {"type": "function", "function": {"name": tool["name"]}},
    }
    if config.LLM_REASONING_EFFORT:
        body["reasoning_effort"] = config.LLM_REASONING_EFFORT
    try:
        data = await _post(provider, body)
    except _RejectedToolCall as exc:
        args = _salvage(exc.generation)
        if args:  # our parsing clamps and defaults every field, so a near-miss is still a usable assessment
            return args, TokenUsage()
        data = await _post(provider, body)  # unreadable: ask once more
    u = data.get("usage") or {}
    usage = TokenUsage(input=u.get("prompt_tokens") or 0, output=u.get("completion_tokens") or 0)
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    for call in msg.get("tool_calls") or []:
        fn = call.get("function") or {}
        if fn.get("name") == tool["name"]:
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError as exc:
                raise LLMError("model returned malformed tool arguments") from exc
            if isinstance(args, dict):
                return args, usage
    if choice.get("finish_reason") == "length":
        raise LLMError("structured output truncated at max_tokens")
    # Some models answer with the JSON object as plain text instead of a tool call.
    text = (msg.get("content") or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if text.startswith("{"):
        try:
            return json.loads(text), usage
        except json.JSONDecodeError:
            pass
    raise LLMError("model did not return the structured tool call")


async def _call_chain(*, role: str, dimension: str | None, system: list[dict], user: str, tool: dict,
                      max_tokens: int) -> tuple[dict, TokenUsage, str]:
    """Try the chain in order. A rate-limited model is skipped (and remembered) and the next one is asked at once;
    when every model is rate-limited, wait for the first to free up. The agent and judge deadlines bound the total,
    and if they pass, the agent falls back to its rule-based scorer."""
    candidates = _candidates(role, dimension)
    failed: set[tuple[str, str]] = set()
    last: Exception | None = None
    while True:
        now = time.monotonic()
        live = [c for c in candidates if (c[0].name, c[1]) not in failed]
        if not live:
            raise last or LLMError("no model available")
        ready = [c for c in live if _cooldown.get((c[0].name, c[1]), 0.0) <= now]
        if not ready:
            wait = min(_cooldown[(c[0].name, c[1])] for c in live) - now
            await asyncio.sleep(min(max(wait, 0.5), 30.0) + random.uniform(0.1, 1.0))
            continue
        provider, model = ready[0]
        try:
            args, usage = await _call_one(provider, model, system=system, user=user, tool=tool, max_tokens=max_tokens)
            return args, usage, f"{provider.name}/{model}"
        except _RateLimited as exc:
            _cooldown[(provider.name, model)] = time.monotonic() + exc.wait_s
            last = exc
        except LLMError as exc:  # broken answer or provider error after its own retries: try the next model
            failed.add((provider.name, model))
            last = exc
