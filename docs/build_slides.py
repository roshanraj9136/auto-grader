"""Generates docs/AutoGrader.pptx (16:9, with speaker notes).

    pip install -r requirements-dev.txt
    python docs/build_slides.py
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

OUT = Path(__file__).resolve().parent / "AutoGrader.pptx"
REPO_URL = "github.com/roshanraj9136/auto-grader"

BG = RGBColor(0x0B, 0x10, 0x20)
PANEL = RGBColor(0x12, 0x19, 0x33)
PANEL2 = RGBColor(0x18, 0x22, 0x44)
LINE = RGBColor(0x2C, 0x3A, 0x60)
FG = RGBColor(0xE6, 0xE9, 0xF2)
MUTED = RGBColor(0x9A, 0xA4, 0xBF)
ACC = RGBColor(0x7C, 0x83, 0xFF)
CYAN = RGBColor(0x22, 0xD3, 0xEE)
GREEN = RGBColor(0x22, 0xC5, 0x5E)
AMBER = RGBColor(0xF5, 0x9E, 0x0B)
RED = RGBColor(0xF4, 0x3F, 0x5E)
FONT = "Segoe UI"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
TOTAL_SLIDES = 14


# ---------------------------------------------------------------------------- helpers
def _style(run, size, color=FG, bold=False, italic=False, font=FONT):
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.italic = italic
    run.font.name = font


def text(slide, x, y, w, h, content, size=16, color=FG, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=1.1, font=FONT):
    """content: str | list[str | (str, dict)] -> one paragraph per item."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    items = content if isinstance(content, list) else [content]
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        t, opts = (item, {}) if isinstance(item, str) else item
        r = p.add_run()
        r.text = t
        _style(r, opts.get("size", size), opts.get("color", color), opts.get("bold", bold),
               opts.get("italic", False), opts.get("font", font))
        if opts.get("space_before"):
            p.space_before = Pt(opts["space_before"])
    return tb


def bullets(slide, x, y, w, h, items, size=16, color=FG, bullet_color=ACC, gap=6):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        head, rest = (item, "") if isinstance(item, str) else item
        b = p.add_run()
        b.text = "•  "
        _style(b, size, bullet_color, bold=True)
        r = p.add_run()
        r.text = head
        _style(r, size, color, bold=bool(rest))
        if rest:
            r2 = p.add_run()
            r2.text = f" — {rest}"
            _style(r2, size, MUTED)
    return tb


def box(slide, x, y, w, h, title=None, body=None, fill=PANEL, line=LINE, title_color=FG, title_size=15,
        body_size=12, body_color=MUTED, align=PP_ALIGN.CENTER, radius=0.12, accent=None, anchor=MSO_ANCHOR.MIDDLE):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.adjustments[0] = radius
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.color.rgb = accent or line
    shp.line.width = Pt(1.5 if accent else 1)
    shp.shadow.inherit = False
    tf = shp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right"):
        setattr(tf, m, Inches(0.1))
    tf.margin_top = tf.margin_bottom = Inches(0.05)
    first = True
    if title:
        p = tf.paragraphs[0]
        p.alignment = align
        r = p.add_run()
        r.text = title
        _style(r, title_size, title_color, bold=True)
        first = False
    for line_text in ([body] if isinstance(body, str) else (body or [])):
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = align
        r = p.add_run()
        r.text = line_text
        _style(r, body_size, body_color)
    return shp


def arrow(slide, x1, y1, x2, y2, color=MUTED, width=1.5, dashed=False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    if dashed:
        dash = ln.makeelement(qn("a:prstDash"), {"val": "dash"})
        ln.append(dash)
    ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    return c


def rect(slide, x, y, w, h, color):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()
    s.shadow.inherit = False
    return s


def new_slide(title, kicker=None, number=True):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    rect(s, 0, 0, 13.333, 0.08, ACC)
    if kicker:
        text(s, 0.6, 0.35, 10, 0.35, kicker.upper(), size=12, color=CYAN, bold=True)
    text(s, 0.6, 0.62, 12.2, 0.8, title, size=30, bold=True)
    if number:
        idx = len(prs.slides)
        text(s, 11.3, 7.0, 1.6, 0.3, f"AutoGrader+  ·  {idx}/{TOTAL_SLIDES}", size=10, color=MUTED, align=PP_ALIGN.RIGHT)
    return s


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


# ---------------------------------------------------------------------------- slides
def s_title():
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    rect(s, 0, 0, 0.18, 7.5, ACC)
    rect(s, 0.18, 0, 0.06, 7.5, CYAN)
    logo = box(s, 0.9, 1.25, 1.1, 1.1, "AG", fill=ACC, line=ACC, title_color=BG, title_size=30, radius=0.25)
    logo.line.fill.background()
    text(s, 0.9, 2.5, 11.5, 1.3, "AutoGrader+", size=60, bold=True)
    text(s, 0.9, 3.65, 11.5, 0.7, "Multi-Agent LLM Grading for Full-Stack Projects", size=28, color=ACC, bold=True)
    text(s, 0.9, 4.4, 11.5, 0.6, "5 specialist agents + 1 judge  ·  GitHub repo + Dockerfile  →  full report in under a minute",
         size=18, color=MUTED)
    for i, (label, col) in enumerate([("Parallel agent DAG", ACC), ("2.74× faster than sequential", GREEN),
                                      ("Docker sandbox", CYAN), ("Explainable scores", AMBER)]):
        box(s, 0.9 + i * 2.95, 5.35, 2.75, 0.55, label, fill=PANEL, accent=col, title_size=13)
    text(s, 0.9, 6.55, 8, 0.4, "CSL100 · Group project", size=14, color=FG, bold=True)
    text(s, 7.0, 6.55, 5.6, 0.4, REPO_URL, size=14, color=CYAN, align=PP_ALIGN.RIGHT)
    notes(s, "Hello everyone. We're presenting AutoGrader+, an extension of the Autograder idea we use in CSL100. "
             "Instead of grading single programs with test cases, it grades a whole full-stack project. "
             "Five specialist AI agents review the code, Docker setup, tests and security in parallel, and a judge "
             "agent combines their reports into one explainable grade and a learning path for the student. "
             "The focus of the design is architecture and latency.")


def s_problem():
    s = new_slide("Grading full-stack projects doesn't scale", "The problem")
    box(s, 0.6, 1.65, 5.9, 4.9, None, fill=PANEL)
    text(s, 0.85, 1.8, 5.5, 0.5, "Today", size=20, bold=True, color=AMBER)
    bullets(s, 0.85, 2.35, 5.5, 4.2, [
        ("Many moving parts", "frontend, API, database, Docker, CI. One TA cannot review all of it deeply"),
        ("Inconsistent", "two TAs, two different grades for the same repository"),
        ("Slow feedback", "students hear back days later, after the next assignment has started"),
        ("Test cases are not enough", "they check outputs, not architecture, security or deployability"),
        ("A number, not a lesson", "students don't learn what to improve next"),
    ], size=15)
    box(s, 6.85, 1.65, 5.9, 4.9, None, fill=PANEL, accent=GREEN)
    text(s, 7.1, 1.8, 5.5, 0.5, "Goal", size=20, bold=True, color=GREEN)
    bullets(s, 7.1, 2.35, 5.5, 4.2, [
        ("Grade the whole system", "code quality, architecture, security, testing, DevOps"),
        ("In under a minute", "latency is a first-class requirement"),
        ("Explain every point", "findings with file paths and concrete fixes"),
        ("Actually run it", "build and start the student's Docker image"),
        ("Teach", "personalised learning path: DBs, load balancers, containers, CI"),
    ], size=15, bullet_color=GREEN)
    notes(s, "Full-stack projects have many layers, and manual review is slow and inconsistent. Unit tests only "
             "check outputs. Our goal is to grade the whole system quickly, explain every point, actually run "
             "the container, and give the student a learning path.")


def s_solution():
    s = new_slide("Solution at a glance", "What AutoGrader+ does")
    cols = [
        ("INPUT", CYAN, ["GitHub repository URL", "branch / tag / commit (optional)", "Dockerfile upload (optional)",
                         "rubric weights per dimension", "instructor brief / assignment spec"]),
        ("5 SPECIALISTS + JUDGE", ACC, ["Code Quality agent", "Architecture agent", "Security agent", "Testing agent",
                                        "DevOps & Docker agent (real build + run)", "Judge: cross-examines, calibrates"]),
        ("OUTPUT", GREEN, ["score /100 + letter grade", "per-dimension rationale", "findings with file paths + fixes",
                           "top priorities + learning path", "latency waterfall · HTML / MD / JSON"]),
    ]
    for i, (head, col, items) in enumerate(cols):
        x = 0.6 + i * 4.25
        box(s, x, 1.7, 3.85, 0.6, head, fill=col, line=col, title_color=BG, title_size=15)
        box(s, x, 2.4, 3.85, 3.6, None, fill=PANEL)
        bullets(s, x + 0.2, 2.55, 3.5, 3.4, items, size=14, bullet_color=col, gap=7)
        if i < 2:
            arrow(s, x + 3.9, 4.2, x + 4.2, 4.2, color=col, width=2.5)
    text(s, 0.6, 6.25, 12.2, 0.6, "Works without an API key too: every agent has a deterministic heuristic scorer, "
                                  "so the same pipeline runs offline (and acts as a fallback).", size=14, color=MUTED)
    notes(s, "The input is a GitHub URL plus an optional Dockerfile and rubric. Five specialists each own one dimension. "
             "The judge reads their reports and produces the final verdict. The output is a full report in HTML, Markdown and JSON.")


def s_platform():
    s = new_slide("The platform: learn full-stack in one place", "AutoGrader+ v2")
    cols = [
        ("Students", ACC, ["Dashboard: score history, skill radar, XP & level", "Assignments with rubric-weighted grading",
                           "Live grading pipeline + full report", "Leaderboard and personal learning path"]),
        ("Hands-on labs", CYAN, ["Frontend: live HTML/CSS/JS editor, DOM checks", "Databases: SQL playground + query plans",
                                 "Load balancers: round-robin vs least-conn vs sticky", "Networks: RTT, proxy headers, Server-Timing",
                                 "Containers: Dockerfile linter (20+ rules)"]),
        ("Instructors", GREEN, ["Publish assignments, rubric weights, deadlines", "Class overview: grade distribution, weak dimensions",
                                "Shared-repo flag (group work or copying)", "Gradebook export (CSV)"]),
    ]
    for i, (head, col, items) in enumerate(cols):
        x = 0.6 + i * 4.2
        box(s, x, 1.65, 3.95, 0.6, head, fill=col, line=col, title_color=BG, title_size=16)
        box(s, x, 2.35, 3.95, 3.55, None, fill=PANEL)
        bullets(s, x + 0.18, 2.5, 3.65, 3.4, items, size=13, bullet_color=col, gap=7)
    box(s, 0.6, 6.1, 12.15, 0.75, None, fill=PANEL2, accent=AMBER, radius=0.08)
    text(s, 0.8, 6.18, 11.8, 0.6, "Every lab runs on the platform's real infrastructure: its PostgreSQL, its Nginx load balancer, its "
                                  "API replicas. Web + installable mobile app (PWA). Accounts, sessions, server-verified tasks.",
         size=13, color=FG)
    notes(s, "This is what turns the grader into the platform the course asked for. Students get a dashboard, assignments, "
             "and five labs that cover the stack: frontend, databases, load balancers, networks and containers. The labs are "
             "not simulations. The load-balancer lab sends real requests through our Nginx to three API replicas, and the SQL "
             "lab shows real query plans. Instructors publish assignments and see where the class struggles.")


def s_architecture():
    s = new_slide("System architecture", "Layered, event-driven, single-pass")
    # main flow
    box(s, 0.5, 1.9, 1.9, 1.1, "Web / PWA", ["dashboards · labs", "SSE · report"], accent=CYAN)
    box(s, 2.85, 1.9, 1.9, 1.1, "Nginx LB", ["sticky · rr · least", "rate limit · SSE"], accent=CYAN)
    box(s, 5.2, 1.9, 2.0, 1.1, "API ×3", ["FastAPI replicas", "auth · REST · SSE"], accent=ACC)
    box(s, 7.65, 1.9, 2.2, 1.1, "JobManager", ["admission control", "single-flight · events"], accent=ACC)
    for x1, x2 in ((2.4, 2.85), (4.75, 5.2), (7.2, 7.65)):
        arrow(s, x1, 2.45, x2, 2.45, color=FG)
    # pipeline container
    box(s, 0.5, 3.45, 9.35, 2.95, None, fill=PANEL2, accent=ACC, radius=0.05)
    text(s, 0.7, 3.5, 6, 0.4, "Grading pipeline (asyncio DAG)", size=14, bold=True, color=ACC)
    arrow(s, 8.75, 3.0, 8.75, 3.45, color=FG)
    stages = [("Ingest", "resolve ‖ clone"), ("Index", "1-pass blackboard"), ("Specialists ×5", "parallel"),
              ("Judge", "calibrate"), ("Report", "HTML·MD·JSON")]
    for i, (t, b) in enumerate(stages):
        x = 0.75 + i * 1.82
        box(s, x, 4.05, 1.6, 0.95, t, b, fill=PANEL, title_size=13, body_size=11)
        if i < len(stages) - 1:
            arrow(s, x + 1.6, 4.52, x + 1.82, 4.52, color=FG)
    box(s, 4.39, 5.3, 1.6, 0.8, "Docker sandbox", "lint · build · run", fill=PANEL, accent=AMBER, title_size=12, body_size=10)
    arrow(s, 2.37, 5.0, 4.39, 5.6, color=AMBER, dashed=True)
    arrow(s, 5.19, 5.3, 5.19, 5.0, color=AMBER, dashed=True)
    # externals
    for i, (t, b, col) in enumerate([("GitHub", "ls-remote · shallow clone", MUTED), ("Claude API", "tool-use JSON · prompt cache", ACC),
                                     ("Docker daemon", "BuildKit · locked-down run", AMBER), ("PostgreSQL", "users · grades · reports", GREEN)]):
        y = 1.9 + i * 1.18
        box(s, 10.35, y, 2.5, 0.95, t, b, fill=PANEL, accent=col, title_size=13, body_size=10)
        arrow(s, 9.85, 4.9 if i else 4.3, 10.35, y + 0.47, color=col, width=1.25, dashed=True)
    text(s, 0.5, 6.6, 12.4, 0.4, "Dependencies point one way: UI → API → jobs/pipeline → agents → infrastructure. "
                                 "Agents never touch disk or network directly.",
         size=12, color=MUTED)
    notes(s, "Requests pass through Nginx, which load-balances across three stateless API replicas, rate-limits and passes "
             "Server-Sent Events through. Sessions and grades live in PostgreSQL on a private network, so any replica can "
             "serve any page; live grading streams use sticky routing. A JobManager enforces admission control and "
             "de-duplicates identical requests. The pipeline is an asyncio DAG. Layers depend downward only. "
             "Agents read a shared, read-only repository index (a blackboard), so no agent re-reads the disk.")


def s_agents():
    s = new_slide("Multi-agent design: 5 specialists + 1 judge", "Separation of concerns")
    agents = [
        ("Code Quality", "size · duplication · linting · naming", "largest + diverse files, dup ratio", ACC),
        ("Architecture", "layering · coupling · API & DB design", "module dependency graph + cycles", CYAN),
        ("Security", "OWASP Top 10 · secrets · authN/Z", "scanner leads, auth files (redacted)", RED),
        ("Testing", "unit · integration · e2e · CI", "test files, test/src ratio, CI", GREEN),
        ("DevOps & Docker", "Dockerfile · compose · CI/CD", "lint + real build/run logs", AMBER),
    ]
    for i, (name, scope, ev, col) in enumerate(agents):
        x = 0.6 + i * 2.47
        box(s, x, 1.7, 2.3, 2.15, None, fill=PANEL, accent=col)
        text(s, x + 0.12, 1.8, 2.1, 0.45, name, size=15, bold=True, color=col)
        text(s, x + 0.12, 2.25, 2.1, 0.8, scope, size=12, color=FG)
        text(s, x + 0.12, 3.05, 2.1, 0.75, "evidence: " + ev, size=11, color=MUTED)
        arrow(s, x + 1.15, 3.85, 6.65, 4.45, color=col, width=1.25)
    box(s, 3.4, 4.45, 6.5, 1.25, "Judge agent", ["reads the 5 structured reports, never raw code (~1k tokens)",
                                                 "finds contradictions & double counting · ±1.5 bounded calibration"],
        fill=PANEL2, accent=FG, title_size=17, body_size=12)
    bullets(s, 0.6, 5.95, 12.3, 1.0, [
        ("Structured output", "forced tool-use JSON schema per agent: no free-text parsing, scores clamped in code"),
        ("Reproducible", "final score = Σ weight × dimension score, computed in code, not by the LLM"),
    ], size=13, gap=3)
    notes(s, "Each specialist owns one dimension and gets its own evidence slice from the index. For example, the Architecture "
             "agent gets a module dependency graph with cycles, and the DevOps agent gets the real Docker build and run "
             "logs. The judge only sees the five structured reports, which keeps it fast. It may adjust each "
             "dimension by at most 1.5 points and must give a rationale. The final number is computed in code, so it is reproducible.")


def s_dag():
    s = new_slide("Pipeline DAG and critical path", "Latency by construction")
    Y = 3.35
    box(s, 0.45, Y - 0.35, 1.15, 0.7, "submit", fill=PANEL, title_size=12)
    box(s, 2.0, 1.75, 1.65, 0.75, "resolve", "git ls-remote", fill=PANEL, title_size=12, body_size=10)
    box(s, 2.0, 4.15, 1.65, 0.75, "clone", "speculative · depth 1", fill=PANEL, accent=RED, title_size=12, body_size=10)
    box(s, 4.05, 1.75, 1.5, 0.75, "cache?", "hit → reuse report", fill=PANEL, accent=GREEN, title_size=12, body_size=10)
    box(s, 4.05, 3.35, 1.5, 0.75, "index", "1 pass · 35 ms", fill=PANEL, accent=RED, title_size=12, body_size=10)
    box(s, 4.05, 5.15, 1.5, 0.75, "docker", "lint · build · run", fill=PANEL, accent=AMBER, title_size=12, body_size=10)
    arrow(s, 1.6, Y, 2.0, 2.12)
    arrow(s, 1.6, Y, 2.0, 4.52, color=RED, width=2.5)
    arrow(s, 3.65, 2.12, 4.05, 2.12)
    arrow(s, 3.65, 4.52, 4.05, 3.72, color=RED, width=2.5)
    arrow(s, 4.8, 2.5, 4.8, 3.35, dashed=True)
    arrow(s, 3.65, 4.6, 4.05, 5.5, color=AMBER)
    names = ["Code Quality", "Architecture", "Security", "Testing"]
    for i, n in enumerate(names):
        y = 1.55 + i * 0.85
        crit = n == "Security"
        box(s, 6.05, y, 1.85, 0.65, n, fill=PANEL, accent=RED if crit else ACC, title_size=12)
        arrow(s, 5.55, 3.72, 6.05, y + 0.32, color=RED if crit else MUTED, width=2.5 if crit else 1.25)
        arrow(s, 7.9, y + 0.32, 8.45, 3.9, color=RED if crit else MUTED, width=2.5 if crit else 1.25)
    box(s, 6.05, 5.15, 1.85, 0.75, "DevOps", "waits for docker", fill=PANEL, accent=AMBER, title_size=12, body_size=10)
    arrow(s, 5.55, 5.52, 6.05, 5.52, color=AMBER)
    arrow(s, 5.55, 3.85, 6.05, 5.3, color=MUTED, width=1)
    arrow(s, 7.9, 5.52, 8.45, 4.1, color=AMBER)
    box(s, 8.45, 3.55, 1.45, 0.75, "Judge", "calibrate", fill=PANEL, accent=RED, title_size=13, body_size=10)
    box(s, 10.3, 3.55, 1.45, 0.75, "Report", "HTML·MD·JSON", fill=PANEL, accent=RED, title_size=13, body_size=10)
    arrow(s, 9.9, 3.92, 10.3, 3.92, color=RED, width=2.5)
    box(s, 0.45, 6.1, 12.4, 0.85, None, fill=PANEL2, radius=0.08)
    text(s, 0.65, 6.15, 12.0, 0.8, [
        ("T_total ≈ max(T_resolve, T_clone) + max(T_index + max(T_agent1..4), T_docker + T_devops) + T_judge",
         {"font": "Consolas", "size": 13, "color": FG, "bold": True}),
        ("Red = critical path measured in the benchmark run. Every report computes it by walking back along the last-finishing dependency.",
         {"size": 11, "color": MUTED}),
    ])
    notes(s, "This is the actual DAG. Resolve and clone start at the same time: the clone is speculative. If the commit is "
             "already in the cache, we cancel the clone and return in about one second. Otherwise indexing takes about 35 ms, "
             "and then four code agents run in parallel while Docker builds in the background. Only DevOps waits for "
             "Docker. Total time is the longest branch plus the judge, not the sum. The red path is what we measured.")


def s_latency():
    s = new_slide("Latency engineering: 3 principles, 15 techniques", "Where the milliseconds go")
    cols = [
        ("Do less work", GREEN, [
            ("Result cache", "key = commit SHA + Dockerfile + rubric + models"),
            ("Single-flight", "identical in-flight jobs are merged"),
            ("Shallow clone", "depth 1, single branch, no tags"),
            ("One-pass index", "scan once, every agent reads memory"),
            ("Ranked evidence budgets", "3.6k–7.2k tokens per agent"),
            ("Capped output tokens", "decode time dominates LLM latency"),
        ]),
        ("Do it in parallel / earlier", ACC, [
            ("5-agent fan-out", "pay max(), not sum()"),
            ("Docker ‖ code agents", "build is off the critical path"),
            ("Speculative clone ‖ ls-remote", "cancelled on cache hit"),
            ("Prompt-cache prefix", "byte-identical shared context"),
            ("Tiny judge input", "~1k tokens on the only sequential LLM call"),
        ]),
        ("Bound the tail (p95/p99)", AMBER, [
            ("Deadlines per agent", "timeout → heuristic fallback"),
            ("Retries with backoff", "429 / 5xx handled by the SDK"),
            ("Global LLM semaphore", "queue locally, avoid 429 storms"),
            ("Admission control", "bounded concurrent jobs, FIFO"),
        ]),
    ]
    for i, (head, col, items) in enumerate(cols):
        x = 0.6 + i * 4.15
        box(s, x, 1.65, 3.95, 0.55, head, fill=col, line=col, title_color=BG, title_size=15)
        box(s, x, 2.28, 3.95, 4.15, None, fill=PANEL)
        tb = s.shapes.add_textbox(Inches(x + 0.15), Inches(2.4), Inches(3.7), Inches(4.0))
        tf = tb.text_frame
        tf.word_wrap = True
        for j, (h, d) in enumerate(items):
            p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
            p.space_after = Pt(5)
            r = p.add_run()
            r.text = h
            _style(r, 14, FG, bold=True)
            p2 = tf.add_paragraph()
            p2.space_after = Pt(6)
            r2 = p2.add_run()
            r2.text = d
            _style(r2, 11.5, MUTED)
    text(s, 0.6, 6.6, 12.3, 0.4, "Plus: non-blocking subprocesses (event loop stays free for SSE), live progress over Server-Sent Events, "
                                 "and p50/p95 per stage at /api/metrics.", size=12, color=MUTED)
    notes(s, "Three principles. First, do less work: cache by commit, merge duplicate jobs, clone shallow, index once, "
             "send each agent only its relevant evidence, and cap output tokens, because decoding is the slowest part of an LLM call. "
             "Second, do things in parallel or earlier: five agents at once, Docker overlapping with them, a speculative clone, "
             "and a tiny judge prompt. Third, bound the tail: every call has a deadline and a fallback, so one slow "
             "agent cannot hold the whole grade hostage.")


def s_results():
    s = new_slide("Results", "Benchmark: dockersamples/example-voting-app (5 services)")
    stats = [("2.74×", "speed-up vs sequential", "27.5 s vs 75.5 s*", GREEN), ("1.2 s", "cache-hit re-grade", "real, ls-remote bound", CYAN),
             ("35 ms", "single-pass index", "real, 8 code files + infra", ACC), ("~1k", "judge input tokens", "vs 3.6–7.2k per agent", AMBER)]
    for i, (big, label, sub, col) in enumerate(stats):
        x = 0.6 + i * 3.1
        box(s, x, 1.65, 2.9, 1.55, None, fill=PANEL, accent=col)
        text(s, x, 1.7, 2.9, 0.75, big, size=34, bold=True, color=col, align=PP_ALIGN.CENTER)
        text(s, x, 2.42, 2.9, 0.35, label, size=13, color=FG, bold=True, align=PP_ALIGN.CENTER)
        text(s, x, 2.75, 2.9, 0.35, sub, size=11, color=MUTED, align=PP_ALIGN.CENTER)
    # waterfall from the benchmark run (ms)
    timings = [("resolve", 0, 858), ("clone", 0, 1379), ("index", 1381, 1415), ("docker", 1381, 1393),
               ("code_quality", 1415, 12887), ("architecture", 1415, 13584), ("security", 1416, 15019),
               ("testing", 1418, 13999), ("devops", 1418, 12276), ("judge", 15019, 27537), ("report", 27538, 27539)]
    crit = {"clone", "index", "security", "judge", "report"}
    total, x0, w, y0, row = 27539, 2.3, 9.5, 3.55, 0.27
    text(s, 0.6, 3.3, 1.7, 0.35, "Waterfall", size=12, bold=True, color=MUTED)
    for i, (n, a, b) in enumerate(timings):
        y = y0 + i * row
        text(s, 0.6, y - 0.04, 1.65, 0.28, n, size=10, color=FG, align=PP_ALIGN.RIGHT)
        rect(s, x0, y + 0.03, w, row - 0.08, PANEL)
        rect(s, x0 + a / total * w, y + 0.03, max((b - a) / total * w, 0.03), row - 0.08, RED if n in crit else ACC)
        dur = b - a
        text(s, x0 + b / total * w + 0.05, y - 0.04, 1.0, 0.28, f"{dur / 1000:.1f}s" if dur >= 1000 else f"{dur}ms",
             size=9, color=MUTED)
    text(s, 0.6, 6.62, 12.3, 0.5, "* Clone, index, lint, evidence building and judge clamping are real. LLM latency is simulated "
                                  "(TTFT 0.8 s + 20k tok/s prefill + 70 tok/s decode) to isolate the architecture's effect. "
                                  "Red = measured critical path.", size=10.5, color=MUTED)
    notes(s, "On a five-service voting app, the parallel DAG finishes in 27.5 seconds against 75.5 seconds if the same stages ran "
             "one after another: a 2.74x speed-up. To be transparent, the LLM latency here is simulated with a standard "
             "latency model. Everything else is real. A cache-hit re-grade takes about one second. In the waterfall, "
             "four agents run side by side and the judge is the only sequential LLM step.")


def s_report():
    s = new_slide("The report: explainable and teaching-oriented", "Output")
    sections = [
        ("Score & grade", "weighted /100, letter grade, judge confidence"),
        ("Dimension table", "specialist score → judge score + rationale"),
        ("Top priorities", "highest-impact fixes, ordered"),
        ("Learning path", "what to learn next: DBs, LB, CI, security"),
        ("Agent findings", "severity · file path · concrete fix"),
        ("Docker sandbox", "lint, build time, image size, run logs"),
        ("Grouped fixes", "one issue in 5 files = one item, with every file listed"),
        ("Formats", "in-app feedback page · printable HTML · Markdown · JSON"),
    ]
    for i, (h, d) in enumerate(sections):
        col, r = i % 2, i // 2
        box(s, 0.6 + col * 3.35, 1.65 + r * 1.2, 3.2, 1.05, h, d, fill=PANEL, title_size=14, body_size=11,
            align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)
    box(s, 7.5, 1.65, 5.25, 4.65, None, fill=PANEL2, accent=CYAN, radius=0.05)
    text(s, 7.7, 1.75, 4.9, 0.4, "Real findings on example-voting-app", size=15, bold=True, color=CYAN)
    bullets(s, 7.7, 2.25, 4.9, 4.0, [
        ("Hard-coded DB credential", "result/server.js:21, value redacted in report"),
        ("Containers run as root", "all 5 Dockerfiles in the repo"),
        ("No .dockerignore", "slower builds, risk of leaking .env"),
        ("Flask debug=True", "vote/app.py:51"),
        ("Thin test suite", "test/source ratio 0.09"),
        ("Learning path", "layered backend, OWASP basics, Nginx load balancing"),
    ], size=13, bullet_color=CYAN, gap=5)
    text(s, 0.6, 6.55, 12.3, 0.4, "Students see plain-language feedback only. Engine latency and metrics live on the instructor's Platform health page.",
         size=12, color=MUTED)
    notes(s, "The report explains every point in plain language. Each finding has a severity, the files it appears in, and a fix. "
             "On the right are real findings from the sample repository, including a hard-coded database credential and root "
             "containers. The learning path turns the grade into a lesson. Technical details such as latency stay on the "
             "instructor's Platform health page, so students are not distracted by them.")


def s_security():
    s = new_slide("Security & reliability", "Grading untrusted code safely")
    box(s, 0.6, 1.65, 5.95, 4.8, None, fill=PANEL, accent=RED)
    text(s, 0.85, 1.75, 5.5, 0.45, "Security", size=19, bold=True, color=RED)
    bullets(s, 0.85, 2.3, 5.5, 4.1, [
        ("URL allow-list", "https://github.com/owner/repo only; blocks file://, ext::, SSRF"),
        ("No shell, ever", "argument lists; refs can't start with '-'"),
        ("Secret redaction", "9 scanners; redacted before prompts and reports"),
        ("Locked-down run", "--network none, 512 MB, 1 CPU, 256 PIDs, cap-drop ALL"),
        ("Edge protection", "Nginx rate limits, scrypt passwords, HttpOnly sessions, CSRF checks, strict CSP"),
        ("Opt-in build sandbox", "docker build runs untrusted RUN steps → isolated VM"),
    ], size=13.5, bullet_color=RED)
    box(s, 6.8, 1.65, 5.95, 4.8, None, fill=PANEL, accent=GREEN)
    text(s, 7.05, 1.75, 5.5, 0.45, "Reliability", size=19, bold=True, color=GREEN)
    bullets(s, 7.05, 2.3, 5.5, 4.1, [
        ("Deadlines everywhere", "git, docker, every LLM call, judge"),
        ("Graceful degradation", "an agent failure → heuristic score, job still completes"),
        ("Bounded judge", "±1.5 per dimension, rationale required"),
        ("Clean failure", "cancel clone/build, delete workspace, purge orphans"),
        ("Atomic artifacts", "write-then-rename; reports survive restarts"),
        ("Observability", "per-stage timings, critical path, p50/p95 metrics"),
    ], size=13.5, bullet_color=GREEN)
    notes(s, "Because we run student code, security matters. Only GitHub URLs are accepted, nothing goes through a shell, secrets are "
             "redacted before the LLM sees them, and the container runs with no network and capped resources. Building "
             "Dockerfiles is still risky, so that sandbox is opt-in and meant for an isolated machine. For reliability, everything "
             "has a deadline and a fallback.")


def s_stack():
    s = new_slide("Tech stack", "Built with")
    items = [
        ("Backend", "Python 3.12 · FastAPI · asyncio · Pydantic v2 · scrypt-hashed accounts, HttpOnly sessions", ACC),
        ("AI", "Anthropic Claude: tool-use structured output, prompt caching, model tiering", CYAN),
        ("Data", "PostgreSQL 17 (docker compose) or SQLite (zero setup) · portable SQL layer, heartbeats", GREEN),
        ("Edge", "Nginx: load balancing (sticky / round-robin / least-conn), rate limits, SSE passthrough", AMBER),
        ("Frontend", "Vanilla JS SPA + SSE · SVG charts · installable PWA · strict CSP · sandboxed code lab", ACC),
        ("Packaging", "Multi-stage Dockerfile (non-root, healthcheck) · compose: nginx + 3 API replicas + Postgres", CYAN),
    ]
    for i, (h, d, col) in enumerate(items):
        y = 1.7 + i * 0.8
        box(s, 0.6, y, 2.4, 0.65, h, fill=col, line=col, title_color=BG, title_size=15)
        box(s, 3.15, y, 9.6, 0.65, d, fill=PANEL, title_size=14, title_color=FG, align=PP_ALIGN.LEFT)
    notes(s, "The stack is intentionally simple: FastAPI with asyncio for concurrency, Claude for the agents, PostgreSQL for shared "
             "state, Nginx as the load balancer, and a dependency-free frontend that also installs as a mobile app. The project's "
             "own Dockerfile follows the rules its DevOps agent checks.")


def s_roadmap():
    s = new_slide("Roadmap: from grader to full-stack learning platform", "Where we are")
    phases = [
        ("v1", "Grader", ["5 agents + judge", "Docker sandbox", "parallel DAG, caching", "single API + Nginx"], GREEN),
        ("v2", "Platform (now)", ["accounts, assignments, dashboards", "5 hands-on labs", "3 API replicas + LB", "PostgreSQL · PWA"], ACC),
        ("Next", "At course scale", ["Redis queue + grading workers", "per-student containers", "GitHub classroom sync",
                                     "object store for reports"], CYAN),
    ]
    for i, (tag, head, items, col) in enumerate(phases):
        x = 0.6 + i * 4.2
        box(s, x, 1.75, 3.9, 0.95, f"{tag}: {head}", fill=col, line=col, title_color=BG, title_size=17)
        box(s, x, 2.8, 3.9, 2.2, None, fill=PANEL)
        bullets(s, x + 0.2, 2.95, 3.55, 2.0, items, size=15, bullet_color=col, gap=8)
        if i < 2:
            arrow(s, x + 3.92, 2.22, x + 4.18, 2.22, color=FG, width=2.5)
    text(s, 0.6, 5.35, 12.3, 0.9, "Fits the course vision: backend services hosted in containers, reached through web and mobile apps. "
                                  "Students learn frontend, load balancers, networks and databases in one place, and AutoGrader+ "
                                  "closes the feedback loop with explainable grades and a learning path.",
         size=14, color=FG)
    notes(s, "Version one was the grader. Version two, what we are showing today, is the platform: accounts, assignments, "
             "dashboards and labs, running as three replicas behind a load balancer with PostgreSQL. Next, a Redis queue with "
             "dedicated grading workers, and per-student containers so every student's backend runs on the platform itself.")


def s_demo():
    s = new_slide("Live demo  ·  Q&A", "Thank you")
    steps = ["docker compose up: open http://localhost:8080", "Student: submit a repo for an assignment",
             "Watch the live DAG: agents run in parallel", "Dashboard: score history, skill radar, learning path",
             "Labs: load balancer across 3 replicas, SQL plans", "Instructor: class overview + gradebook export"]
    for i, st in enumerate(steps):
        y = 1.75 + i * 0.68
        box(s, 0.6, y, 0.55, 0.55, str(i + 1), fill=ACC, line=ACC, title_color=BG, title_size=15, radius=0.5)
        text(s, 1.35, y + 0.06, 6.3, 0.5, st, size=16)
    box(s, 8.0, 1.75, 4.75, 3.95, None, fill=PANEL2, accent=CYAN)
    text(s, 8.2, 1.95, 4.4, 0.5, "Source code", size=18, bold=True, color=CYAN, align=PP_ALIGN.CENTER)
    text(s, 8.2, 2.55, 4.4, 0.5, REPO_URL, size=15, color=FG, bold=True, align=PP_ALIGN.CENTER)
    text(s, 8.2, 3.25, 4.4, 2.2, ["README: quick start", "docs/ARCHITECTURE.md: full design",
                                  "scripts/latency_benchmark.py: reproduce results"], size=13, color=MUTED, align=PP_ALIGN.CENTER, spacing=1.4)
    text(s, 0.6, 6.15, 12.3, 0.7, "Questions?", size=30, bold=True, color=ACC, align=PP_ALIGN.CENTER)
    notes(s, "Demo plan: bring the stack up with docker compose, sign in as a student, submit a repository for an assignment and "
             "watch the agents run in parallel. Then the dashboard, the load-balancer lab hitting three replicas, and the "
             "instructor view with the gradebook export. Thank you, happy to take questions.")


for fn in (s_title, s_problem, s_solution, s_platform, s_architecture, s_agents, s_dag, s_latency, s_results,
           s_report, s_security, s_stack, s_roadmap, s_demo):
    fn()

assert len(prs.slides) == TOTAL_SLIDES, len(prs.slides)
prs.save(OUT)
print(f"wrote {OUT} ({len(prs.slides)} slides)")
