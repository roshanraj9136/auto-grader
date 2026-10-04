"""Latency benchmark for the grading DAG with a *simulated* LLM.

Runs the real pipeline (real clone, index, docker lint, evidence building, judge clamping)
but replaces the Claude call with a latency model:

    latency = TTFT + input_tokens / PREFILL_TPS + output_tokens / DECODE_TPS   (x --scale)

so you can compare parallel vs. sequential execution without an API key or spend.
Simulated numbers are a model, not a measurement of Claude - label them as such.

    python scripts/latency_benchmark.py https://github.com/dockersamples/example-voting-app
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents import base as agent_base  # noqa: E402
from app.agents import judge as judge_mod  # noqa: E402
from app import pipeline  # noqa: E402
from app.config import DEFAULT_WEIGHTS  # noqa: E402
from app.ingest.git_ops import normalize_repo_url  # noqa: E402
from app.jobs import Job  # noqa: E402
from app.models import GradeRequest, Rubric, TokenUsage  # noqa: E402

TTFT_S, PREFILL_TPS, DECODE_TPS = 0.8, 20_000, 70  # rough, configurable model of a hosted LLM
prefix_hashes: dict[str, str] = {}
prompt_tokens: dict[str, int] = {}


def make_fake(scale: float):
    async def fake_call_tool(*, model, system, user, tool, max_tokens):
        in_chars = sum(len(b["text"]) for b in system) + len(user)
        in_tok = in_chars // 4
        is_judge = tool["name"] == "submit_verdict"
        out_tok = random.randint(500, 900) if is_judge else random.randint(600, 1100)
        cache_read = 0
        if not is_judge:
            role = system[1]["text"].split("dimension: ")[1].split(")")[0]
            prefix_hashes[role] = hashlib.sha256(system[0]["text"].encode()).hexdigest()[:16]
            prompt_tokens[role] = in_tok
        else:
            prompt_tokens["judge"] = in_tok
        await asyncio.sleep((TTFT_S + in_tok / PREFILL_TPS + out_tok / DECODE_TPS) * scale)
        usage = TokenUsage(input=in_tok, output=out_tok, cache_read=cache_read)
        if is_judge:
            dims = tool["input_schema"]["properties"]["dimensions"]["items"]["properties"]["dimension"]["enum"]
            return {
                "dimensions": [{"dimension": d, "final_score": 9.9, "rationale": "simulated (+ tests the ±1.5 clamp)"} for d in dims],
                "summary": "Simulated judge verdict.", "top_priorities": ["simulated priority"],
                "learning_path": ["simulated topic"], "confidence": 0.7,
            }, usage
        return {"score": round(random.uniform(5, 8), 1), "confidence": 0.7, "summary": "Simulated assessment.",
                "strengths": ["simulated"], "findings": [{"severity": "medium", "title": "simulated finding",
                                                          "detail": "n/a", "recommendation": "n/a"}]}, usage
    return fake_call_tool


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo_url")
    ap.add_argument("--scale", type=float, default=1.0, help="multiply simulated LLM latency (e.g. 0.2 for a quick run)")
    args = ap.parse_args()

    fake = make_fake(args.scale)
    agent_base.call_tool = fake
    judge_mod.call_tool = fake
    for mod in (agent_base, judge_mod, pipeline):
        mod.llm_enabled = lambda: True

    req = GradeRequest(repo_url=normalize_repo_url(args.repo_url), rubric=Rubric(weights=DEFAULT_WEIGHTS), force=True)
    job = Job(req)
    report = await pipeline.run_pipeline(job)

    print(f"\nRepo: {report.repo_url} @ {report.commit_sha[:10]}   (LLM latency SIMULATED, scale={args.scale})")
    print(f"{'stage':<22}{'start':>8}{'end':>8}{'dur':>8}")
    for t in report.timings:
        print(f"{t.name:<22}{t.start_ms:>8}{t.end_ms:>8}{t.duration_ms:>8}  {t.status}")
    print(f"\nwall-clock      {report.total_ms} ms")
    print(f"sequential sum  {report.sequential_ms} ms   -> speed-up {report.speedup}x")
    print(f"critical path   {' -> '.join(report.critical_path)}")
    print(f"judge clamp     " + ", ".join(f"{d.dimension}: {d.agent_score}->{d.final_score}" for d in report.verdict.dimensions))
    print(f"est. prompt tokens per call: {prompt_tokens}")
    unique = set(prefix_hashes.values())
    print(f"shared cached prefix identical across {len(prefix_hashes)} specialists: {len(unique) == 1} ({unique})")


if __name__ == "__main__":
    asyncio.run(main())
