"""Per-job stage tracing, critical-path analysis and process-wide latency metrics."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Awaitable, Callable, TypeVar

from .models import StageTiming

T = TypeVar("T")

# DAG of the grading pipeline: stage -> stages it waits on.
# Used to reconstruct the critical path from measured timings.
PIPELINE_DEPS: dict[str, list[str]] = {
    "resolve": [],
    "clone": [],  # starts speculatively, in parallel with resolve
    "cache_lookup": ["resolve"],
    "index": ["clone", "cache_lookup"],
    "docker": ["clone", "cache_lookup"],
    "agent:code_quality": ["index"],
    "agent:architecture": ["index"],
    "agent:security": ["index"],
    "agent:testing": ["index"],
    "agent:devops": ["index", "docker"],
    "judge": [
        "agent:code_quality",
        "agent:architecture",
        "agent:security",
        "agent:testing",
        "agent:devops",
    ],
    "report": ["judge", "cache_lookup"],
}


class LatencyMetrics:
    """Rolling per-stage latency samples (process-wide) for /api/metrics."""

    def __init__(self, window: int = 500) -> None:
        self._samples: dict[str, deque[int]] = defaultdict(lambda: deque(maxlen=window))
        self.counters: dict[str, int] = defaultdict(int)

    def observe(self, name: str, ms: int) -> None:
        self._samples[name].append(ms)

    def incr(self, name: str, by: int = 1) -> None:
        self.counters[name] += by

    @staticmethod
    def _pct(sorted_vals: list[int], p: float) -> int:
        if not sorted_vals:
            return 0
        k = min(len(sorted_vals) - 1, max(0, round(p / 100 * (len(sorted_vals) - 1))))
        return sorted_vals[k]

    def snapshot(self) -> dict:
        stages = {}
        for name, vals in sorted(self._samples.items()):
            s = sorted(vals)
            stages[name] = {
                "count": len(s),
                "p50_ms": self._pct(s, 50),
                "p95_ms": self._pct(s, 95),
                "max_ms": s[-1] if s else 0,
            }
        return {"stages": stages, "counters": dict(self.counters)}


METRICS = LatencyMetrics()


class Tracer:
    """Records stage start/end relative to job start and publishes live events."""

    def __init__(self, publish: Callable[..., None]) -> None:
        self._t0 = time.perf_counter()
        self._publish = publish
        self.timings: list[StageTiming] = []

    def now_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    @asynccontextmanager
    async def stage(self, name: str):
        start = self.now_ms()
        self._publish("stage_start", stage=name)
        status = "done"
        try:
            yield
        except asyncio.CancelledError:
            status = "skipped"  # e.g. speculative clone aborted on cache hit
            raise
        except BaseException:
            status = "failed"
            raise
        finally:
            end = self.now_ms()
            self.timings.append(StageTiming(name=name, start_ms=start, end_ms=end, status=status))
            METRICS.observe(name, end - start)
            self._publish("stage_end", stage=name, status=status, duration_ms=end - start)

    async def run(self, name: str, factory: Callable[[], Awaitable[T]]) -> T:
        async with self.stage(name):
            return await factory()

    def skip(self, name: str, reason: str) -> None:
        now = self.now_ms()
        self.timings.append(StageTiming(name=name, start_ms=now, end_ms=now, status="skipped"))
        self._publish("stage_end", stage=name, status="skipped", duration_ms=0, reason=reason)

    # ---- analysis -------------------------------------------------------
    def critical_path(self, sink: str = "report") -> list[str]:
        """Walk back from `sink`, always following the dependency that finished last."""
        by_name = {t.name: t for t in self.timings if t.status != "skipped"}
        if sink not in by_name:
            return []
        path, node = [sink], sink
        while True:
            deps = [d for d in PIPELINE_DEPS.get(node, []) if d in by_name]
            if not deps:
                break
            node = max(deps, key=lambda d: by_name[d].end_ms)
            path.append(node)
        return list(reversed(path))

    def sequential_ms(self) -> int:
        return sum(t.duration_ms for t in self.timings if t.status != "skipped")
