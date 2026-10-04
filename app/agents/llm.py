"""Thin async Claude client: structured output via forced tool use, prompt caching,
global concurrency cap, SDK-level retries with exponential backoff (429/5xx)."""
from __future__ import annotations

import asyncio

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
    return bool(config.ANTHROPIC_API_KEY)


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
