"""Specialist agent contract: evidence selection + LLM assessment + deterministic fallback."""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod

from .. import config
from ..ingest.indexer import RepoIndex
from ..models import AgentReport, DockerResult, Finding, TokenUsage
from .llm import cached_system, call_tool, llm_enabled

SEVERITIES = ("critical", "high", "medium", "low", "info")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}

COMMON_PREAMBLE = """You are one specialist on AutoGrader's review panel. The panel grades student full-stack
projects (frontend, backend APIs, databases, containers, networking/load balancing, testing, CI/CD).
Each specialist scores exactly ONE dimension; a separate judge later cross-examines all reports.

Scoring anchors (0-10, decimals allowed):
  0-2  missing or fundamentally broken      3-4  present but poor / many serious issues
  5-6  adequate for a student project       7-8  good, few issues, sensible practices
  9-10 excellent, near production-grade
Rules:
- Ground every claim in the evidence provided. Cite file paths exactly as shown. Never invent files.
- Judge relative to project size and the instructor brief (if given); do not punish a small
  project for lacking enterprise features it does not need.
- Findings must be actionable: what is wrong, where, and the concrete fix. Max 2 sentences each.
- Lower `confidence` when the evidence is partial (truncated files, docker not built, etc.).
- Respond ONLY by calling the `submit_assessment` tool once. Be concise; brevity is required."""

ASSESSMENT_TOOL = {
    "name": "submit_assessment",
    "description": "Submit the structured assessment for your dimension.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {"type": "number", "minimum": 0, "maximum": 10},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "summary": {"type": "string", "description": "2-3 sentence verdict for this dimension."},
            "strengths": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
            "findings": {
                "type": "array",
                "maxItems": 7,
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {"type": "string", "enum": list(SEVERITIES)},
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "file": {"type": "string"},
                        "recommendation": {"type": "string"},
                    },
                    "required": ["severity", "title", "detail", "recommendation"],
                },
            },
        },
        "required": ["score", "confidence", "summary", "strengths", "findings"],
    },
}


def clamp(v, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def parse_findings(raw, limit: int = 8) -> list[Finding]:
    out: list[Finding] = []
    for item in (raw or [])[:limit]:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        sev = str(item.get("severity", "medium")).lower()
        out.append(Finding(
            severity=sev if sev in SEVERITY_RANK else "medium",
            title=str(item["title"])[:200],
            detail=str(item.get("detail", ""))[:800],
            file=(str(item["file"])[:300] if item.get("file") else None),
            recommendation=str(item.get("recommendation", ""))[:600],
        ))
    return sorted(out, key=lambda f: SEVERITY_RANK[f.severity])


class SpecialistAgent(ABC):
    name: str
    dimension: str
    role_prompt: str
    needs_docker: bool = False

    @abstractmethod
    def evidence(self, idx: RepoIndex, docker: DockerResult | None) -> str: ...

    @abstractmethod
    def heuristic(self, idx: RepoIndex, docker: DockerResult | None) -> AgentReport: ...

    async def run(self, idx: RepoIndex, shared: str, docker: DockerResult | None = None) -> AgentReport:
        t0 = time.perf_counter()
        if not llm_enabled():
            rep = self.heuristic(idx, docker)
            rep.mode = "heuristic"
        else:
            try:
                data, usage = await asyncio.wait_for(self._ask_llm(idx, shared, docker), timeout=config.AGENT_TIMEOUT_S)
                rep = self._to_report(data, usage)
            except Exception as exc:  # noqa: BLE001 - graceful degradation keeps tail latency bounded
                rep = self.heuristic(idx, docker)
                rep.mode = "heuristic-fallback"
                rep.error = f"{type(exc).__name__}: {exc}"[:300]
        rep.latency_ms = int((time.perf_counter() - t0) * 1000)
        return rep

    async def _ask_llm(self, idx: RepoIndex, shared: str, docker: DockerResult | None) -> tuple[dict, TokenUsage]:
        system = cached_system(
            COMMON_PREAMBLE + "\n\n# SHARED REPOSITORY CONTEXT\n" + shared,
            f"# YOUR ROLE: {self.name} (dimension: {self.dimension})\n{self.role_prompt}",
        )
        user = (f"# EVIDENCE FOR DIMENSION `{self.dimension}`\n{self.evidence(idx, docker)}\n\n"
                "Call `submit_assessment` now.")
        return await call_tool(model=config.AGENT_MODEL, system=system, user=user,
                               tool=ASSESSMENT_TOOL, max_tokens=config.AGENT_MAX_TOKENS)

    def _to_report(self, data: dict, usage: TokenUsage) -> AgentReport:
        return AgentReport(
            agent=self.name,
            dimension=self.dimension,
            score=round(clamp(data.get("score"), 0, 10, 5.0), 1),
            confidence=round(clamp(data.get("confidence"), 0, 1, 0.5), 2),
            summary=str(data.get("summary", ""))[:1200] or "(no summary)",
            strengths=[str(s)[:300] for s in (data.get("strengths") or [])[:5]],
            findings=parse_findings(data.get("findings")),
            mode="llm",
            tokens=usage,
        )

    def make_report(self, score: float, summary: str, strengths: list[str], findings: list[Finding],
                    confidence: float = 0.45) -> AgentReport:
        return AgentReport(
            agent=self.name, dimension=self.dimension, score=round(clamp(score, 0, 10, 5), 1),
            confidence=confidence, summary=summary, strengths=strengths[:5],
            findings=sorted(findings, key=lambda f: SEVERITY_RANK[f.severity])[:8],
        )
