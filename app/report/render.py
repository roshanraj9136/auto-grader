"""Report rendering: Markdown (for git/LMS) and a self-contained, printable HTML feedback page.

Both are written for the student. Engine internals (stage latency, tokens, model mode) stay in the
JSON report and the instructor-only Platform health page."""
from __future__ import annotations

import re
from html import escape as e

from ..models import GradeReport

DIM_LABEL = {
    "code_quality": "Code quality", "architecture": "Architecture", "security": "Security",
    "testing": "Testing", "devops": "Docker & DevOps",
}
SEV_COLOR = {"critical": "#b91c1c", "high": "#c2410c", "medium": "#a16207", "low": "#1d4ed8", "info": "#4b5563"}


def _label(d: str) -> str:
    return DIM_LABEL.get(d, d.replace("_", " ").title())


_WHERE = re.compile(r"^(.*?)\s*\[([^\]]+)\]\s*$")
_PRIO = re.compile(r"^\[(\w+)\]\s*(.*?)(?:\s+[—-]\s+(.*))?$")


def _group_findings(findings) -> list[tuple]:
    """Merge one issue repeated across files ("Container runs as root [vote/Dockerfile]") into a single
    entry: (finding, base_title, [files]), most severe first."""
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    groups: dict[tuple, list] = {}
    for f in sorted(findings, key=lambda f: rank.get(f.severity, 9)):
        m = _WHERE.match(f.title)
        base, where = (m.group(1), m.group(2)) if m else (f.title, None)
        g = groups.setdefault((f.severity, base), [f, base, []])
        loc = where or f.file
        if loc and loc not in g[2]:
            g[2].append(loc)
    return [tuple(g) for g in groups.values()]


def _priority(p: str) -> tuple[str, str, str]:
    m = _PRIO.match(p)
    return (m.group(1).lower(), m.group(2), m.group(3) or "") if m else ("", p, "")


# ---------------------------------------------------------------------------------------
def render_markdown(r: GradeReport) -> str:
    v = r.verdict
    out = [
        f"# AutoGrader+ feedback: {r.repo_url.removeprefix('https://github.com/')}",
        f"Commit `{r.commit_sha[:7]}` · {r.created_at[:10]}",
        "",
        f"## Score: **{v.final_score}/100 ({v.grade})**",
        "", v.summary, "",
        "| Area | Weight | Score |",
        "|---|---:|---:|",
    ]
    for d in v.dimensions:
        out.append(f"| {_label(d.dimension)} | {d.weight:.0%} | **{d.final_score}/10** |")
    out += ["", "## Fix these first"] + [f"{i}. **{t}**" + (f": {fix}" if fix else "") for i, (_, t, fix) in
                                         enumerate(map(_priority, v.top_priorities), 1)]
    out += ["", "## What to learn next"] + [f"- {p}" for p in v.learning_path]

    for a in r.agents:
        out += ["", f"## {_label(a.dimension)}: {a.score}/10" + (f" (⚠ {a.error})" if a.error else "")]
        if a.mode == "llm" and a.summary:
            out += ["", a.summary]
        if a.strengths:
            out += ["", "**What you did well**"] + [f"- {s}" for s in a.strengths]
        if a.findings:
            out += ["", "**What to improve**", "", "| Severity | Issue | Where | How to fix |", "|---|---|---|---|"]
            for f, title, files in _group_findings(a.findings):
                out.append(f"| {f.severity} | **{title}**: {f.detail} | {', '.join(files)} | {f.recommendation} |".replace("\n", " "))

    d = r.docker
    out += ["", "## Docker", f"- Dockerfile: {d.dockerfile_source} ({d.dockerfile_path or 'n/a'})"
            + (f"; also checked: {', '.join(d.other_dockerfiles)}" if d.other_dockerfiles else "")]
    if d.attempted_build:
        out.append(f"- Build: {_status(d.build_ok, d.attempted_build)}" + (f" in {d.build_seconds}s" if d.build_seconds else "")
                   + (f", image {d.image_size_mb} MB" if d.image_size_mb else "") + f"; test run: {_status(d.run_ok, d.attempted_run)}")
    if d.build_log_tail:
        out += ["", "<details><summary>Build log (tail)</summary>", "", "```", d.build_log_tail, "```", "</details>"]
    out += ["", f"_AutoGrader+ · {r.created_at[:10]}_", ""]
    return "\n".join(out)


def _status(ok, attempted) -> str:
    if not attempted:
        return "not attempted"
    return "✅ success" if ok else "❌ failed"


# ---------------------------------------------------------------------------------------
def render_html(r: GradeReport) -> str:
    """Printable, student-facing feedback page (light theme, matches the web app)."""
    v = r.verdict
    repo = r.repo_url.removeprefix("https://github.com/")

    def tone(score10: float) -> str:
        return "#16a34a" if score10 >= 7.8 else "#2563eb" if score10 >= 6.2 else "#d97706" if score10 >= 4.8 else "#dc2626"

    tiles = "".join(
        f"<div class='tile'><b>{e(_label(d.dimension))}</b><span class='big' style='color:{tone(d.final_score)}'>{d.final_score:.1f}"
        f"<small>/10</small></span><div class='bar'><span style='width:{d.final_score * 10:.0f}%;background:{tone(d.final_score)}'></span></div>"
        f"<span class='muted'>counts {d.weight:.0%}</span></div>" for d in v.dimensions)

    sections = []
    for a in r.agents:
        items = "".join(
            f"<div class='finding'><b><span class='sev' style='background:{SEV_COLOR[f.severity]}'>{e(f.severity)}</span>{e(title)}</b>"
            f"{f'<p>{e(f.detail)}</p>' if f.detail else ''}"
            f"{('<p class=muted>' + ('In ' + str(len(files)) + ' places: ' if len(files) > 1 else 'File: ') + ' '.join(f'<code>{e(x)}</code>' for x in files) + '</p>') if files else ''}"
            f"{f'<p class=fix>How to fix: {e(f.recommendation)}</p>' if f.recommendation else ''}</div>"
            for f, title, files in _group_findings(a.findings))
        sections.append(f"""
<section class="card"><h3>{e(_label(a.dimension))} <span class="pill" style="color:{tone(a.score)}">{a.score:.1f}/10</span></h3>
  {f'<p>{e(a.summary)}</p>' if a.mode == 'llm' and a.summary else ''}
  {('<h4>What you did well</h4><ul>' + ''.join(f'<li>{e(s)}</li>' for s in a.strengths) + '</ul>') if a.strengths else ''}
  {('<h4>What to improve</h4>' + items) if items else '<p class="muted">Nothing to fix here. Nice!</p>'}
</section>""")

    d = r.docker
    stats = r.repo_stats
    langs = ", ".join(e(k) for k, _ in sorted((stats.get("languages") or {}).items(), key=lambda kv: -kv[1])[:5])
    score_tone = tone(v.final_score / 10)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Feedback · {e(repo)} · AutoGrader+</title>
<style>
:root{{--fg:#0f1b2d;--muted:#6b7686;--bg:#f6f8fa;--card:#fff;--line:#e4e8ec;--brand:#059669}}
*{{box-sizing:border-box}} body{{font:15px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--fg);background:var(--bg);margin:0;padding:28px 18px}}
main{{max-width:960px;margin:auto}} h1{{margin:0 0 4px;font-size:1.5rem;letter-spacing:-.02em}} h2{{margin:28px 0 12px;font-size:1.15rem}}
h3{{margin:0 0 8px;font-size:1.05rem;display:flex;gap:10px;align-items:center}} h4{{margin:14px 0 6px;font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}
a{{color:var(--brand)}} .muted{{color:var(--muted);font-size:.86rem}} p{{margin:4px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px 22px;margin:14px 0;box-shadow:0 1px 3px rgba(15,27,45,.05)}}
.hero{{display:flex;gap:26px;align-items:center;flex-wrap:wrap}}
.score{{width:120px;height:120px;border-radius:50%;display:grid;place-items:center;background:conic-gradient({score_tone} {v.final_score}%,#eaeef2 0)}}
.score span{{width:102px;height:102px;border-radius:50%;background:#fff;display:grid;place-items:center;font-size:2rem;font-weight:800;line-height:1}}
.score small{{display:block;font-size:.85rem;color:{score_tone};font-weight:700;margin-top:4px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;display:flex;flex-direction:column;gap:4px}}
.tile .big{{font-size:1.5rem;font-weight:800}} .tile small{{font-size:.8rem;color:var(--muted);font-weight:600}}
.bar{{background:#eaeef2;border-radius:99px;height:7px;overflow:hidden}} .bar span{{display:block;height:7px;border-radius:99px}}
.pill{{background:#f3f6f8;border-radius:999px;padding:2px 10px;font-size:.85rem;font-weight:700}}
.sev{{color:#fff;border-radius:5px;padding:1px 7px;font-size:.7rem;text-transform:uppercase;letter-spacing:.04em;margin-right:8px;vertical-align:1px}}
.finding{{padding:10px 0;border-top:1px solid var(--line)}} .finding:first-of-type{{border-top:0}}
.fix{{background:#e7f8f1;border-radius:10px;padding:8px 12px;margin-top:6px}}
ol,ul{{padding-left:20px;margin:6px 0}} li{{margin:4px 0}} code{{font-size:.85em;background:#f3f6f8;padding:1px 5px;border-radius:5px}}
pre{{background:#0f172a;color:#e2e8f0;padding:12px;border-radius:10px;overflow:auto;max-height:300px;font-size:.8rem}}
@media print{{body{{background:#fff;padding:0}} .card{{box-shadow:none;break-inside:avoid}}}}
</style></head><body><main>
<header class="card hero">
  <div class="score" role="img" aria-label="Score {v.final_score} out of 100, grade {e(v.grade)}"><span>{v.final_score:.0f}<small>{e(v.grade)}</small></span></div>
  <div style="flex:1;min-width:240px"><h1>Feedback for <a href="{e(r.repo_url)}">{e(repo)}</a></h1>
  <p>{e(v.summary)}</p>
  <p class="muted">Commit <code>{e(r.commit_sha[:7])}</code> · {e(r.created_at[:10])} · AutoGrader+</p></div>
</header>
<div class="tiles">{tiles}</div>
<section class="card"><h2 style="margin-top:0">Fix these first</h2><ol>{''.join(
    f"<li>{f'<span class=sev style=background:{SEV_COLOR[s]}>{e(s)}</span>' if s in SEV_COLOR else ''}<strong>{e(t)}</strong>{f': {e(fix)}' if fix else ''}</li>"
    for s, t, fix in map(_priority, v.top_priorities)) or '<li>Nothing urgent. Nice work!</li>'}</ol>
<h2>What to learn next</h2><ul>{''.join(f'<li>{e(p)}</li>' for p in v.learning_path) or '<li>Keep building!</li>'}</ul></section>
<h2>Detailed feedback</h2>
{''.join(sections)}
<section class="card"><h3>Docker</h3>
<p>Dockerfile: <strong>{e(d.dockerfile_source)}</strong> {('(<code>' + e(d.dockerfile_path) + '</code>)') if d.dockerfile_path else ''}</p>
{(f"<p>Build: {_status(d.build_ok, d.attempted_build)}{f' in {d.build_seconds}s' if d.build_seconds else ''}{f', image {d.image_size_mb} MB' if d.image_size_mb else ''} · "
  f"Test run: {_status(d.run_ok, d.attempted_run)}</p>") if d.attempted_build else '<p class="muted">Checked by reading the Dockerfile.</p>'}
{('<details><summary>Build log</summary><pre>' + e(d.build_log_tail) + '</pre></details>') if d.build_log_tail else ''}
{('<details><summary>Run log</summary><pre>' + e(d.run_log_tail) + '</pre></details>') if d.run_log_tail else ''}
</section>
<p class="muted">{stats.get('code_files', 0)} code files · {stats.get('source_lines', 0)} lines · {stats.get('test_files', 0)} test files{(' · ' + langs) if langs else ''}</p>
</main></body></html>"""
