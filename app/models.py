"""Typed contracts passed between pipeline stages (the 'blackboard' schema)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low", "info"]
Mode = Literal["llm", "heuristic", "heuristic-fallback"]


class Finding(BaseModel):
    severity: Severity = "medium"
    title: str
    detail: str = ""
    file: str | None = None
    recommendation: str = ""


class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input=self.input + other.input,
            output=self.output + other.output,
            cache_read=self.cache_read + other.cache_read,
            cache_write=self.cache_write + other.cache_write,
        )


class AgentReport(BaseModel):
    agent: str
    dimension: str
    score: float = Field(ge=0, le=10)
    confidence: float = Field(ge=0, le=1, default=0.5)
    summary: str
    strengths: list[str] = []
    findings: list[Finding] = []
    mode: Mode = "llm"
    latency_ms: int = 0
    tokens: TokenUsage = TokenUsage()
    error: str | None = None
    model: str = ""  # which model answered, "provider/model"; empty in heuristic mode


class DimensionVerdict(BaseModel):
    dimension: str
    agent_score: float
    final_score: float
    weight: float
    rationale: str


class JudgeVerdict(BaseModel):
    final_score: float  # 0-100, computed in code from weighted dimension scores
    grade: str
    summary: str
    dimensions: list[DimensionVerdict]
    top_priorities: list[str]
    learning_path: list[str] = []      # teaching-oriented "what to learn next" for the student
    calibration_notes: list[str] = []
    confidence: float = 0.5
    mode: Mode = "llm"
    latency_ms: int = 0
    tokens: TokenUsage = TokenUsage()
    error: str | None = None
    model: str = ""


class DockerResult(BaseModel):
    dockerfile_source: Literal["uploaded", "repo", "none"] = "none"
    dockerfile_path: str | None = None
    dockerfile_text: str = Field(default="", exclude=True)  # evidence for the DevOps agent; not persisted
    other_dockerfiles: list[str] = []  # additional service Dockerfiles (statically linted, not built)
    lint: list[Finding] = []
    attempted_build: bool = False
    build_ok: bool | None = None
    build_seconds: float | None = None
    build_log_tail: str = ""
    attempted_run: bool = False
    run_ok: bool | None = None
    run_log_tail: str = ""
    image_size_mb: float | None = None
    skipped_reason: str | None = None


class StageTiming(BaseModel):
    name: str
    start_ms: int
    end_ms: int
    status: Literal["done", "failed", "skipped"] = "done"

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


class Rubric(BaseModel):
    weights: dict[str, float]
    notes: str = ""  # assignment brief / teacher rubric text, given to every agent and the judge


class GradeRequest(BaseModel):
    repo_url: str
    ref: str | None = None
    dockerfile_text: str | None = None
    rubric: Rubric
    force: bool = False


class GradeReport(BaseModel):
    job_id: str
    repo_url: str
    ref: str | None
    commit_sha: str
    created_at: str
    autograder_version: str
    agent_model: str
    judge_model: str
    llm_mode: bool
    repo_stats: dict
    docker: DockerResult
    agents: list[AgentReport]
    verdict: JudgeVerdict
    timings: list[StageTiming]
    critical_path: list[str]
    total_ms: int
    sequential_ms: int = 0   # what the same stages would cost if run one after another
    speedup: float = 1.0     # sequential_ms / total_ms
    tokens: TokenUsage
    cache_hit: bool = False
    pipeline_notes: list[str] = []
