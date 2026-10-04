"""Judge agent: cross-examines the five specialist reports and produces the final verdict.

Design choices:
- The judge never re-reads code: it gets compact structured reports (~3-6k tokens), which keeps
  the only *sequential* LLM call on the critical path short.
- The final number is computed in code (weighted sum), not by the LLM, so it is reproducible;
  the judge may move each dimension by at most +/-MAX_ADJUST with a written rationale.
"""
from __future__ import annotations

import asyncio
import json
import re
import time

from .. import config
from ..models import AgentReport, DimensionVerdict, DockerResult, JudgeVerdict, Rubric, TokenUsage
from .base import SEVERITY_RANK, clamp
from .llm import call_tool, llm_enabled

MAX_ADJUST = 1.5

JUDGE_SYSTEM = f"""You are the head examiner (judge) of AutoGrader. Five specialist agents have each
graded one dimension of a student's full-stack project. Your job:
1. Cross-examine: look for contradictions between reports (e.g. architecture praises auth while
   security finds none), double-counting of the same issue in several dimensions, and scores that
   are inconsistent with their own findings or confidence. Treat heuristic-mode reports as less reliable.
2. Calibrate: output a final score for EVERY dimension. You may move a specialist's score by at most
   +/-{MAX_ADJUST} and must explain any change in `rationale` (otherwise say 'consistent with evidence').
3. Summarise for the student in 3-4 sentences, then list the top 3-6 highest-impact fixes
   (most important first) and a learning path of 3-6 concrete topics the student should learn next
   to become a better full-stack engineer (frontend, APIs, databases, containers, networking/load
   balancing, testing, CI/CD) - tailored to the gaps you see.
Do not compute the overall score; the system computes it from your dimension scores and the rubric weights.
Respond ONLY by calling `submit_verdict` once. Be concise."""


def _verdict_tool(dimensions: list[str]) -> dict:
    return {
        "name": "submit_verdict",
        "description": "Submit the calibrated verdict.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimensions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dimension": {"type": "string", "enum": dimensions},
                            "final_score": {"type": "number", "minimum": 0, "maximum": 10},
                            "rationale": {"type": "string"},
                        },
                        "required": ["dimension", "final_score", "rationale"],
                    },
                },
                "summary": {"type": "string"},
                "top_priorities": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                "learning_path": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                "calibration_notes": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["dimensions", "summary", "top_priorities", "learning_path", "confidence"],
        },
    }


GRADE_BANDS = [(85, "A"), (78, "A-"), (70, "B"), (62, "B-"), (55, "C"), (48, "C-"), (40, "D"), (0, "F")]
DIM_NAMES = {"code_quality": "code quality", "architecture": "architecture", "security": "security",
             "testing": "testing", "devops": "Docker & DevOps"}

LEARNING_TOPICS = {
    "code_quality": "Clean code: small single-purpose functions, linting (ESLint/Ruff) and auto-formatting in CI.",
    "architecture": "Layered backend design (routes -> services -> repositories), REST API design and env-based config.",
    "security": "Web security fundamentals (OWASP Top 10): parameterised queries, password hashing, secrets management, authZ checks.",
    "testing": "Testing pyramid: unit tests, API integration tests with a test DB, and a CI gate that blocks failing builds.",
    "devops": "Containers: multi-stage Dockerfiles, non-root images, docker-compose for app + DB, healthchecks.",
}


def letter_grade(score: float) -> str:
    return next(g for cutoff, g in GRADE_BANDS if score >= cutoff)


def weighted_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    total_w = sum(weights.values()) or 1.0
    return round(sum(scores[d] * w for d, w in weights.items() if d in scores) / total_w * 10, 1)


class JudgeAgent:
    name = "Judge Agent"

    async def run(self, reports: list[AgentReport], rubric: Rubric, repo_stats: dict, docker: DockerResult) -> JudgeVerdict:
        t0 = time.perf_counter()
        if not llm_enabled():
            v = self.heuristic(reports, rubric, repo_stats)
        else:
            try:
                v = await asyncio.wait_for(self._ask_llm(reports, rubric, repo_stats, docker), timeout=config.JUDGE_TIMEOUT_S)
            except Exception as exc:  # noqa: BLE001
                v = self.heuristic(reports, rubric, repo_stats)
                v.mode = "heuristic-fallback"
                v.error = f"{type(exc).__name__}: {exc}"[:300]
        v.latency_ms = int((time.perf_counter() - t0) * 1000)
        return v

    # ---- LLM path ------------------------------------------------------------------
    async def _ask_llm(self, reports, rubric: Rubric, repo_stats: dict, docker: DockerResult) -> JudgeVerdict:
        compact = [{
            "dimension": r.dimension, "agent": r.agent, "score": r.score, "confidence": r.confidence, "mode": r.mode,
            "summary": r.summary, "strengths": r.strengths,
            "findings": [{"severity": f.severity, "title": f.title, "file": f.file, "detail": f.detail[:240]} for f in r.findings],
        } for r in reports]
        stats = {k: repo_stats.get(k) for k in ("code_files", "source_lines", "test_files", "test_to_source_ratio",
                                                 "languages", "stack", "ci", "duplication_ratio")}
        dock = docker.model_dump(include={"dockerfile_source", "build_ok", "run_ok", "image_size_mb", "skipped_reason"})
        user = (f"## Rubric weights\n{json.dumps(rubric.weights)}\n\n## Instructor notes\n{rubric.notes or '(none)'}\n\n"
                f"## Repository facts\n{json.dumps(stats)}\n\n## Docker sandbox\n{json.dumps(dock)}\n\n"
                f"## Specialist reports\n{json.dumps(compact, indent=1)}\n\nCall `submit_verdict` now.")
        data, usage = await call_tool(model=config.JUDGE_MODEL, system=[{"type": "text", "text": JUDGE_SYSTEM}],
                                      user=user, tool=_verdict_tool(list(rubric.weights)), max_tokens=config.JUDGE_MAX_TOKENS)
        return self._finalize(reports, rubric, data, usage)

    def _finalize(self, reports, rubric: Rubric, data: dict, usage: TokenUsage) -> JudgeVerdict:
        by_dim = {r.dimension: r for r in reports}
        judged = {d.get("dimension"): d for d in data.get("dimensions", []) if isinstance(d, dict)}
        dims: list[DimensionVerdict] = []
        notes = [str(n)[:400] for n in (data.get("calibration_notes") or [])[:5]]
        for dim, w in rubric.weights.items():
            agent_score = by_dim[dim].score if dim in by_dim else 5.0
            j = judged.get(dim, {})
            proposed = clamp(j.get("final_score"), 0, 10, agent_score)
            final = clamp(proposed, agent_score - MAX_ADJUST, agent_score + MAX_ADJUST, agent_score)
            if abs(final - proposed) > 1e-6:
                notes.append(f"{dim}: judge proposed {proposed:.1f}, clamped to ±{MAX_ADJUST} of specialist score.")
            dims.append(DimensionVerdict(dimension=dim, agent_score=agent_score, final_score=round(final, 1), weight=w,
                                         rationale=str(j.get("rationale", "not addressed by judge"))[:600]))
        score = weighted_score({d.dimension: d.final_score for d in dims}, rubric.weights)
        return JudgeVerdict(
            final_score=score, grade=letter_grade(score),
            summary=str(data.get("summary", ""))[:1500],
            dimensions=dims,
            top_priorities=[str(p)[:400] for p in (data.get("top_priorities") or [])[:6]],
            learning_path=[str(p)[:400] for p in (data.get("learning_path") or [])[:6]],
            calibration_notes=notes,
            confidence=round(clamp(data.get("confidence"), 0, 1, 0.6), 2),
            mode="llm", tokens=usage,
        )

    # ---- deterministic fallback ----------------------------------------------------
    def heuristic(self, reports: list[AgentReport], rubric: Rubric, repo_stats: dict) -> JudgeVerdict:
        by_dim = {r.dimension: r for r in reports}
        dims = [DimensionVerdict(dimension=d, agent_score=by_dim[d].score if d in by_dim else 5.0,
                                 final_score=by_dim[d].score if d in by_dim else 5.0, weight=w,
                                 rationale="Heuristic mode: specialist score accepted without cross-examination.")
                for d, w in rubric.weights.items()]
        score = weighted_score({d.dimension: d.final_score for d in dims}, rubric.weights)

        ranked_findings = sorted(
            ((f, rubric.weights.get(r.dimension, 0)) for r in reports for f in r.findings),
            key=lambda t: (SEVERITY_RANK[t[0].severity], -t[1]),
        )
        # The same issue in several files ("Container runs as root [vote/Dockerfile]") is one priority.
        base = lambda title: re.sub(r"\s*\[[^\]]+\]\s*$", "", title)  # noqa: E731
        places: dict[str, int] = {}
        for f, _ in ranked_findings:
            places[base(f.title)] = places.get(base(f.title), 0) + 1
        priorities, seen = [], set()
        for f, _ in ranked_findings:
            title = base(f.title)
            if title in seen or f.severity == "info":
                continue
            seen.add(title)
            n = places[title]
            priorities.append(f"[{f.severity}] {title}{f' ({n} places)' if n > 1 else ''} — {f.recommendation}")
            if len(priorities) == 5:
                break

        weakest = sorted(dims, key=lambda d: d.final_score)
        path = [LEARNING_TOPICS[d.dimension] for d in weakest if d.final_score < 7.5 and d.dimension in LEARNING_TOPICS][:4]
        stack = repo_stats.get("stack", {})
        if not stack.get("database"):
            path.append("Databases: model your data in PostgreSQL with migrations and an ORM/query builder.")
        if not stack.get("proxy_lb"):
            path.append("Networking: put Nginx in front as a reverse proxy and load-balance two app replicas.")
        strongest = max(dims, key=lambda d: d.final_score)
        summary = (f"Your project scored {score}/100 ({letter_grade(score)}). Your strongest area is "
                   f"{DIM_NAMES.get(strongest.dimension, strongest.dimension)} ({strongest.final_score}/10); start improving "
                   f"{DIM_NAMES.get(weakest[0].dimension, weakest[0].dimension)} ({weakest[0].final_score}/10) first.")
        return JudgeVerdict(final_score=score, grade=letter_grade(score), summary=summary, dimensions=dims,
                            top_priorities=priorities, learning_path=path[:6],
                            calibration_notes=["Heuristic mode: no cross-examination performed."],
                            confidence=0.4, mode="heuristic")
