"""Prompt-context construction with strict character budgets.

Two layers:
  1. `shared_context` - identical bytes for every specialist of a job, placed first in the
     prompt so Anthropic prompt-caching can reuse the prefix (lower cost, lower prefill time).
  2. `pack_files`     - agent-specific evidence, ranked by relevance and cut to a budget.
Smaller, relevant inputs = faster time-to-first-token and fewer hallucinated citations.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Callable, Iterable

from .. import config
from .indexer import FileInfo, RepoIndex


def truncate_middle(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    tail = limit - head - 40
    return f"{text[:head]}\n\n… [{len(text) - head - tail} chars omitted] …\n\n{text[-tail:]}"


def render_tree(idx: RepoIndex, max_depth: int = 3, max_lines: int = 160, files_per_dir: int = 12) -> str:
    children: dict[str, list[str]] = defaultdict(list)
    files_in: dict[str, list[FileInfo]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    for f in idx.files:
        parts = f.path.split("/")
        for depth in range(len(parts) - 1):
            parent = "/".join(parts[:depth])
            d = "/".join(parts[: depth + 1])
            if d not in children[parent]:
                children[parent].append(d)
            counts[d] += 1
        files_in["/".join(parts[:-1])].append(f)

    out: list[str] = []

    def walk(d: str, depth: int) -> None:
        if len(out) >= max_lines:
            return
        indent = "  " * depth
        fl = files_in.get(d, [])
        for f in fl[:files_per_dir]:
            out.append(f"{indent}{f.name}" + (f"  ({f.lines} lines)" if f.lines else ""))
        if len(fl) > files_per_dir:
            out.append(f"{indent}… +{len(fl) - files_per_dir} more files")
        for sub in sorted(children.get(d, [])):
            if len(out) >= max_lines:
                out.append(f"{indent}… (tree truncated)")
                return
            out.append(f"{indent}{sub.rsplit('/', 1)[-1]}/  [{counts[sub]} files]")
            if depth + 1 < max_depth:
                walk(sub, depth + 1)

    walk("", 0)
    return "\n".join(out[: max_lines + 1])


def shared_context(idx: RepoIndex, repo_url: str, commit: str, rubric_notes: str) -> str:
    """Deterministic, agent-agnostic overview (must be byte-identical across agents)."""
    stats = idx.stats()
    parts = [
        f"Repository: {repo_url} @ {commit[:12]}",
        "## Repository statistics\n" + json.dumps(stats, indent=1, sort_keys=True),
        "## File tree (depth 3)\n" + render_tree(idx),
    ]
    if idx.readme:
        parts.append(f"## README ({idx.readme_path})\n" + truncate_middle(idx.readme, 3500))
    manifests_budget = 4500
    for path in sorted(idx.manifests):
        text = idx.manifests[path]
        if not text or manifests_budget <= 0:
            continue
        snippet = truncate_middle(text, min(1500, manifests_budget))
        manifests_budget -= len(snippet)
        parts.append(f"## Manifest: {path}\n{snippet}")
    if rubric_notes.strip():
        parts.append("## Instructor rubric / assignment brief\n" + rubric_notes.strip()[: config.MAX_RUBRIC_CHARS])
    return truncate_middle("\n\n".join(parts), config.SHARED_CONTEXT_CHARS)


def pack_files(
    files: Iterable[FileInfo],
    budget: int = config.AGENT_SLICE_CHARS,
    per_file: int = config.PER_FILE_CHARS,
    seen: set[str] | None = None,
) -> str:
    """Greedy packing of ranked files into a character budget."""
    seen = seen if seen is not None else set()
    chunks: list[str] = []
    used = 0
    for f in files:
        if f.path in seen or not f.content:
            continue
        body = truncate_middle(f.content, per_file)
        block = f"### FILE: {f.path} ({f.lines} lines)\n```\n{body}\n```"
        if used + len(block) > budget:
            if budget - used > 1200:  # squeeze a shorter version in
                block = f"### FILE: {f.path} ({f.lines} lines, truncated)\n```\n{truncate_middle(f.content, budget - used - 200)}\n```"
            else:
                continue
        chunks.append(block)
        used += len(block)
        seen.add(f.path)
        if used >= budget:
            break
    return "\n\n".join(chunks) if chunks else "(no matching files)"


def ranked(idx: RepoIndex, score: Callable[[FileInfo], float]) -> list[FileInfo]:
    scored = [(score(f), f) for f in idx.files if f.content]
    return [f for s, f in sorted(scored, key=lambda t: (-t[0], t[1].path)) if s > 0]
