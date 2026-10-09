"""Thin async LLM client: structured output via forced tool use, global concurrency cap, retries with
exponential backoff (429/5xx).

Two providers behind one function (`call_tool`):
* Anthropic (Claude): forced tool use, prompt caching on the shared system block, SDK retries.
* Any OpenAI-compatible chat API (Google Gemini by default, Groq, OpenRouter, ...): forced function calling.
  Free tiers rate-limit hard, so 429s are retried with backoff (honouring Retry-After); if a call still fails,
  the calling agent falls back to its rule-based scorer, so a grading never fails because of the model.
"""
from __future__ import annotations

import asyncio
import json
import random
import urllib.error
import urllib.parse
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
    return config.LLM_PROVIDER == "openai" and bool(config.LLM_API_KEY)


def provider_label() -> str:
    """Human-readable provider for health checks and reports, e.g. 'gemini' or 'anthropic'."""
    if not llm_enabled():
        return "heuristic"
    if config.LLM_PROVIDER == "anthropic":
        return "anthropic"
    host = urllib.parse.urlsplit(config.LLM_BASE_URL).hostname or "openai-compatible"
    return {"generativelanguage.googleapis.com": "gemini", "api.groq.com": "groq", "openrouter.ai": "openrouter"}.get(host, host)


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


async def call_tool(*, model: str, system: list[dict], user: str, tool: dict, max_tokens: int) -> tuple[dict, TokenUsage]:
    if config.LLM_PROVIDER == "openai":
        return await _call_openai_compatible(model=model, system=system, user=user, tool=tool, max_tokens=max_tokens)
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
            return dict(block.input), usage
    raise LLMError("model did not return the structured tool call")


# ---------------------------------------------------------------------------- OpenAI-compatible APIs
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _post_once(body: bytes) -> tuple[int, str, str]:
    """One blocking POST (run in a worker thread): (status, retry-after header, response text)."""
    # A named User-Agent: some providers' firewalls (Groq's Cloudflare, error 1010) block Python's default one.
    req = urllib.request.Request(f"{config.LLM_BASE_URL}/chat/completions", data=body, method="POST", headers={
        "Authorization": f"Bearer {config.LLM_API_KEY}", "Content-Type": "application/json",
        "User-Agent": "autograder-plus/1.0 (+https://github.com/roshanraj9136/auto-grader)"})
    try:
        with urllib.request.urlopen(req, timeout=max(config.AGENT_TIMEOUT_S, config.JUDGE_TIMEOUT_S)) as resp:
            return resp.status, "", resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("retry-after", "") or "", exc.read().decode("utf-8", "replace")


class _RejectedToolCall(LLMError):
    """The provider rejected the model's tool call as invalid (Groq: 400 tool_use_failed) and returned the raw
    generation, which is usually the right JSON with a small schema slip that our own parsing tolerates."""

    def __init__(self, generation: str):
        super().__init__("model produced an invalid tool call")
        self.generation = generation


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


def _delay(retry_after: str, fallback: float) -> float:
    try:
        return float(retry_after)
    except ValueError:
        return fallback


async def _post_with_retries(body: dict) -> dict:
    payload = json.dumps(body).encode()
    attempts = config.LLM_MAX_RETRIES + 2  # for errors; rate limits are retried until the caller's deadline
    failures = 0
    while True:
        try:
            async with _sem:  # the slot is held only while a request is in flight, never while waiting
                status, retry_after, text = await asyncio.to_thread(_post_once, payload)
        except (urllib.error.URLError, OSError) as exc:  # DNS, connection reset, timeout
            failures += 1
            if failures >= attempts:
                raise LLMError(f"network error: {exc}") from exc
            await asyncio.sleep(2 ** failures + random.random())
            continue
        if status == 200:
            return json.loads(text)
        if status == 429:
            # Free tiers cap tokens per minute and say how long to wait. Wait that long (plus jitter so parallel
            # reviewers don't retry in lockstep); the agent and judge deadlines bound the total time.
            await asyncio.sleep(min(_delay(retry_after, 5.0), 30.0) + random.uniform(0.2, 1.5))
            continue
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
                await asyncio.sleep(min(_delay(retry_after, 2 ** failures + random.random()), 30.0))
                continue
        # Never echo the request (it carries the key in a header, and student code in the body).
        raise LLMError(f"model API returned HTTP {status}: {text[:200]}")


async def _call_openai_compatible(*, model: str, system: list[dict], user: str, tool: dict, max_tokens: int) -> tuple[dict, TokenUsage]:
    body: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "\n\n".join(b["text"] for b in system)},
            {"role": "user", "content": user},
        ],
        "tools": [{"type": "function", "function": {
            "name": tool["name"], "description": tool.get("description", ""), "parameters": tool["input_schema"]}}],
        "tool_choice": {"type": "function", "function": {"name": tool["name"]}},
    }
    if config.LLM_REASONING_EFFORT:
        body["reasoning_effort"] = config.LLM_REASONING_EFFORT
    try:
        data = await _post_with_retries(body)
    except _RejectedToolCall as exc:
        args = _salvage(exc.generation)
        if args:  # our parsing clamps and defaults every field, so a near-miss is still a usable assessment
            return args, TokenUsage()
        data = await _post_with_retries(body)  # unreadable: ask once more
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
