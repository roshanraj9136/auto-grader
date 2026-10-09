"""Generates docs/AutoGrader.pptx (16:9, with speaker notes on every slide).

    pip install -r requirements-dev.txt
    python docs/build_slides.py

Screenshots come from docs/img/ (taken from a running local instance).
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
OUT = HERE / "AutoGrader.pptx"
IMG = HERE / "img"
REPO_URL = "github.com/roshanraj9136/auto-grader"
LIVE_URL = "autograder-plus.onrender.com"

# "Marking" palette, same as the web app: ink, ballpoint blue, highlighter, red pen.
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PAPER = RGBColor(0xF1, 0xF3, 0xF6)
INK = RGBColor(0x14, 0x1C, 0x2E)
INK2 = RGBColor(0x4A, 0x54, 0x68)
INK3 = RGBColor(0x7F, 0x89, 0x9B)
RULE = RGBColor(0xD5, 0xDB, 0xE3)
PEN = RGBColor(0x21, 0x40, 0xD9)
MARK = RGBColor(0xFF, 0xE1, 0x4A)
RED = RGBColor(0xC4, 0x30, 0x2B)
GREEN = RGBColor(0x16, 0x79, 0x4A)
AMBER = RGBColor(0xA8, 0x5D, 0x06)
FONT = "Segoe UI"
FONT_B = "Segoe UI Semibold"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
TOTAL_SLIDES = 19


# ---------------------------------------------------------------------------- helpers
def _style(run, size, color=INK, bold=False, font=FONT):
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.name = font


def text(slide, x, y, w, h, content, size=16, color=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=1.12, font=FONT):
    """content: str | list[str | (str, dict)]: one paragraph per item."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.03)
    items = content if isinstance(content, list) else [content]
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        t, o = (item, {}) if isinstance(item, str) else item
        r = p.add_run()
        r.text = t
        _style(r, o.get("size", size), o.get("color", color), o.get("bold", bold), o.get("font", font))
        if o.get("space_before"):
            p.space_before = Pt(o["space_before"])
    return tb


def bullets(slide, x, y, w, h, items, size=15, gap=7, marker="•", marker_color=PEN):
    """items: str | (bold head, rest)."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        p.line_spacing = 1.1
        head, rest = (item, "") if isinstance(item, str) else item
        m = p.add_run()
        m.text = f"{marker}  "
        _style(m, size, marker_color, bold=True)
        r = p.add_run()
        r.text = head
        _style(r, size, INK, bold=bool(rest), font=FONT_B if rest else FONT)
        if rest:
            r2 = p.add_run()
            r2.text = f"  {rest}"
            _style(r2, size, INK2)
    return tb


def box(slide, x, y, w, h, title=None, body=None, fill=WHITE, line=RULE, title_color=INK, title_size=15, body_size=12,
        body_color=INK2, align=PP_ALIGN.CENTER, radius=0.1, weight=1.0, anchor=MSO_ANCHOR.MIDDLE, dashed=False):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.adjustments[0] = radius
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.color.rgb = line
    shp.line.width = Pt(weight)
    if dashed:
        ln = shp.line._get_or_add_ln()
        ln.append(ln.makeelement(qn("a:prstDash"), {"val": "dash"}))
    shp.shadow.inherit = False
    tf = shp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.1)
    tf.margin_top = tf.margin_bottom = Inches(0.05)
    first = True
    if title:
        p = tf.paragraphs[0]
        p.alignment = align
        r = p.add_run()
        r.text = title
        _style(r, title_size, title_color, bold=True, font=FONT_B)
        first = False
    for line_text in ([body] if isinstance(body, str) else (body or [])):
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.alignment = align
        if align == PP_ALIGN.LEFT:  # left-aligned boxes hold lists: give each line room
            p.space_before = Pt(5)
        r = p.add_run()
        r.text = line_text
        _style(r, body_size, body_color)
    return shp


def arrow(slide, x1, y1, x2, y2, color=INK3, width=1.5):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    return c


def rect(slide, x, y, w, h, color):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()
    s.shadow.inherit = False
    return s


def picture(slide, name, x, y, w=None, h=None):
    pic = slide.shapes.add_picture(str(IMG / f"{name}.png"), Inches(x), Inches(y),
                                   Inches(w) if w else None, Inches(h) if h else None)
    pic.line.color.rgb = RULE
    pic.line.width = Pt(1)
    return pic


def table(slide, x, y, w, rows, col_w, size=12, head=True, row_h=0.36):
    shp = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(row_h * len(rows)))
    tbl = shp.table
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = PAPER if (head and i == 0) else WHITE
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            tf = cell.text_frame
            tf.word_wrap = True
            r = tf.paragraphs[0].add_run()
            r.text = str(val)
            bold = (head and i == 0) or j == 0
            _style(r, size, INK if bold else INK2, bold=bold, font=FONT_B if bold else FONT)
    tbl.first_row = head
    return shp


def new_slide(title, section=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = WHITE
    rect(s, 0, 0, 13.333, 0.07, INK)
    if section:
        text(s, 0.6, 0.32, 9, 0.35, section, size=12, color=INK3)
    text(s, 0.6, 0.6, 12.2, 0.8, title, size=28, bold=True, font=FONT_B)
    idx = len(prs.slides)
    text(s, 10.8, 7.02, 2.1, 0.3, f"AutoGrader+   {idx} / {TOTAL_SLIDES}", size=10, color=INK3, align=PP_ALIGN.RIGHT)
    return s


def highlight(slide, x, y, w, h):
    """A highlighter band behind a phrase (drawn before the text that sits on it)."""
    return rect(slide, x, y, w, h, MARK)


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


# ---------------------------------------------------------------------------- slides
def s_title():
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = WHITE
    rect(s, 0, 0, 13.333, 0.07, INK)
    box(s, 0.7, 0.9, 0.85, 0.85, "✓", fill=INK, line=INK, title_color=MARK, title_size=30, radius=0.2)
    text(s, 0.7, 2.0, 7.4, 2.2, ["AutoGrader+", ("Your repository, marked like a code review",
                                                 {"size": 26, "color": INK2, "bold": False, "font": FONT})],
         size=54, bold=True, font=FONT_B, spacing=1.05)
    highlight(s, 0.72, 4.45, 5.9, 0.42)
    text(s, 0.7, 4.38, 7.5, 0.55, "Multi-agent grading + a full-stack learning platform", size=18, font=FONT_B)
    text(s, 0.7, 5.25, 7.4, 1.2, [f"Live:  {LIVE_URL}", f"Code:  {REPO_URL}", ("CSL100 group project", {"color": INK3, "space_before": 8})],
         size=15, color=INK2, spacing=1.25)
    picture(s, "landing", 8.45, 0.95, w=4.3)
    picture(s, "instructor-overview", 8.45, 3.95, w=4.3)
    notes(s, "AutoGrader+ grades a student's whole full-stack project from its GitHub link and turns the result into feedback "
             "they can act on. Around the grader we built a learning platform with two different views: one for students and one "
             "for instructors. The site is live at the link on the slide, and everything I show today is running there.")


def s_problem():
    s = new_slide("Why we built it", "Motivation")
    box(s, 0.6, 1.6, 5.9, 4.9, None, fill=PAPER, line=PAPER)
    text(s, 0.85, 1.8, 5.5, 0.5, "Grading full-stack projects by hand", size=19, bold=True, font=FONT_B)
    bullets(s, 0.85, 2.45, 5.5, 4.0, [
        ("Slow.", "Every project has a frontend, an API, a database and a Dockerfile to read."),
        ("Inconsistent.", "Two graders give the same project different marks."),
        ("Late feedback.", "Students hear what was wrong after the deadline, when it no longer helps."),
        ("No overview.", "Instructors can't easily see who is struggling or who copied."),
    ], marker_color=RED)
    box(s, 6.85, 1.6, 5.9, 4.9, None, fill=WHITE, line=RULE)
    text(s, 7.1, 1.8, 5.5, 0.5, "What we wanted instead", size=19, bold=True, font=FONT_B)
    bullets(s, 7.1, 2.45, 5.5, 4.0, [
        ("Feedback in about a minute,", "with the file and the fix."),
        ("Reproducible scores:", "the total is computed in code from published weights."),
        ("Students improve and resubmit;", "their best attempt counts."),
        ("Instructors see the class:", "who needs help, the distribution, possible copying."),
    ], marker_color=GREEN)
    notes(s, "The problem: grading full-stack projects is slow and inconsistent, and feedback arrives too late to help. Our goals "
             "were feedback in about a minute, scores anyone can reproduce, a loop where students improve and resubmit, and "
             "a clear class picture for instructors.")


def s_overview():
    s = new_slide("What AutoGrader+ is", "Overview")
    box(s, 0.6, 1.65, 3.9, 2.4, "Grading engine", ["5 specialist reviewers run in parallel", "1 judge calibrates and explains",
                                                   "score, priorities, learning path"], line=INK, weight=1.75, title_size=18, body_size=13)
    box(s, 4.75, 1.65, 3.9, 2.4, "Student view", ["assignments with visible rubrics", "live progress, detailed feedback",
                                                 "dashboard, XP, labs"], line=PEN, weight=1.75, title_size=18, body_size=13)
    box(s, 8.9, 1.65, 3.9, 2.4, "Instructor view", ["what needs attention, gradebook", "assignment analytics, copy detection",
                                                    "grade adjustment, re-runs"], line=RED, weight=1.75, title_size=18, body_size=13)
    text(s, 0.6, 4.45, 12.2, 0.4, "Five reviewers, one area each", size=17, bold=True, font=FONT_B)
    areas = [("Code quality", "readable, well-structured code"), ("Architecture", "layers, coupling, API and DB design"),
             ("Security", "OWASP Top 10, secrets"), ("Testing", "unit, integration, CI"), ("Docker & DevOps", "images, compose, delivery")]
    for i, (t, d) in enumerate(areas):
        box(s, 0.6 + i * 2.47, 4.95, 2.3, 1.25, t, d, fill=PAPER, line=PAPER, title_size=14, body_size=11)
    text(s, 0.6, 6.4, 12.2, 0.5, "Runs on Claude models (LLM mode) or, with no API key, on rule-based scorers through the same pipeline "
                                 "(heuristic mode).", size=13, color=INK2)
    notes(s, "Three parts. The grading engine: five reviewers, each responsible for one area, and a judge on top. The student "
             "view and the instructor view are built around what each group needs. Without an API key the same pipeline runs "
             "with deterministic rule-based scorers, which is how the public demo runs.")


def s_architecture():
    s = new_slide("System architecture", "Architecture")
    box(s, 0.6, 2.45, 2.2, 1.2, "Browser / phone", "web app, PWA", line=INK, weight=1.5)
    arrow(s, 2.8, 3.05, 3.35, 3.05)
    text(s, 2.72, 2.68, 0.8, 0.3, "HTTPS", size=10, color=INK3, align=PP_ALIGN.CENTER)
    box(s, 3.35, 2.45, 2.5, 1.2, "Nginx load balancer", "round-robin, least-conn, sticky", line=INK, weight=1.5)
    for i in range(3):
        y = 1.55 + i * 1.05
        arrow(s, 5.85, 3.05, 6.45, y + 0.42)
        box(s, 6.45, y, 3.0, 0.85, f"API replica {i + 1}", "FastAPI: REST + SSE + grading", line=PEN, weight=1.5,
            title_size=13, body_size=10)
    deps = [("PostgreSQL", "accounts, grades, reports", INK, False), ("GitHub", "shallow clone", INK, False),
            ("Claude API", "5 reviewers + judge", INK, False), ("Docker sandbox", "optional build + run", INK3, True)]
    for i, (t, d, c, dash) in enumerate(deps):
        y = 1.3 + i * 0.95
        arrow(s, 9.45, 3.05, 10.05, y + 0.4)
        box(s, 10.05, y, 2.7, 0.82, t, d, line=c, weight=1.25, title_size=13, body_size=10, dashed=dash)
    box(s, 0.6, 5.15, 12.15, 1.45, None, fill=PAPER, line=PAPER)
    bullets(s, 0.8, 5.25, 11.8, 1.3, [
        ("Stateless replicas:", "all shared state (users, sessions, submissions, reports) lives in PostgreSQL, so any replica serves any page."),
        ("Durable event log:", "every progress event is also stored in PostgreSQL, so any replica can stream any job (no sticky routing needed)."),
        ("Deployed:", "one container on Render + Neon PostgreSQL; locally docker compose runs Nginx + 3 replicas + PostgreSQL."),
    ], size=13, gap=4)
    notes(s, "The browser talks to an Nginx load balancer, which spreads requests over three identical FastAPI replicas. Each "
             "replica serves the web app and the API and runs grading jobs. Everything shared lives in PostgreSQL, so replicas are "
             "stateless and can be scaled. Even the live progress of a job is written to the database as it happens, so any replica "
             "can stream it. The public deployment is a single container on Render with a Neon database; the code is identical.")


def s_pipeline():
    s = new_slide("What happens to one submission", "Grading pipeline")
    steps = [("Admission", "queue limit, single-flight de-duplication, submission recorded"),
             ("Resolve + clone", "git ls-remote and a shallow clone start in parallel"),
             ("Cache lookup", "same commit, Dockerfile, rubric and models: report back in 1.2 s"),
             ("Index", "one pass (~35 ms): languages, tests, CI, Dockerfiles, dependency graph, secret scan"),
             ("Docker", "20+ rule linter always; locked-down build and run optional"),
             ("5 reviewers in parallel", "ranked evidence, 3.6k–7.2k tokens each, forced JSON schema output"),
             ("Judge", "reads ~1k tokens of reports, may move each area ±1.5 with a reason"),
             ("Report", "score computed in code; HTML, Markdown, JSON saved to disk and PostgreSQL")]
    for i, (t, d) in enumerate(steps):
        col, row = divmod(i, 4)
        x, y = 0.6 + col * 6.15, 1.6 + row * 1.25
        box(s, x, y, 0.62, 0.62, str(i + 1), fill=INK, line=INK, title_color=WHITE, title_size=16, radius=0.5)
        text(s, x + 0.82, y - 0.04, 5.1, 0.4, t, size=16, bold=True, font=FONT_B)
        text(s, x + 0.82, y + 0.36, 5.1, 0.7, d, size=12.5, color=INK2)
    text(s, 0.6, 6.55, 12.2, 0.4, "The browser follows every stage live over Server-Sent Events; if the stream drops it falls back to "
                                  "polling.", size=13, color=INK2)
    notes(s, "Eight steps. Admission control limits concurrent jobs and attaches duplicate requests to the running job. Resolving the "
             "commit and cloning start together. If the same commit was graded before with the same rubric, the cached report comes "
             "back in about a second. Indexing reads the repository once. The Dockerfile is linted. Then the five reviewers run at "
             "the same time on evidence picked for them, the judge calibrates, and the report is written.")


def s_dag():
    s = new_slide("Stages overlap: the pipeline is a graph", "Grading pipeline")
    cols = [["resolve", "clone"], ["cache"], ["index", "docker"], ["code quality", "architecture", "security", "testing", "devops"],
            ["judge"], ["report"]]
    xs = [0.6, 2.45, 4.1, 6.0, 8.55, 10.4]
    for ci, (x, items) in enumerate(zip(xs, cols)):
        w = 2.1 if ci == 3 else 1.6
        top = 3.3 - (len(items) * 0.62) / 2
        for i, it in enumerate(items):
            box(s, x, top + i * 0.66, w, 0.52, it, fill=MARK if it == "judge" else WHITE, line=PEN if ci == 3 else INK,
                weight=1.5, title_size=12)
        if ci < len(cols) - 1:
            arrow(s, x + w + 0.05, 3.3, xs[ci + 1] - 0.05, 3.3)
    box(s, 0.6, 5.0, 12.15, 1.55, None, fill=PAPER, line=PAPER)
    text(s, 0.85, 5.12, 11.7, 1.4, [
        ("T_total ≈ max(T_resolve, T_clone) + max(T_index + max(T_reviewer 1–4), T_docker + T_devops) + T_judge",
         {"font": "Consolas", "size": 14, "bold": True, "color": INK}),
        ("Only the DevOps reviewer waits for Docker; the other four start right after indexing, so a slow build overlaps with model "
         "calls. Each report records its measured critical path and the speed-up over running the same stages in sequence.",
         {"size": 13, "color": INK2, "space_before": 8}),
    ])
    notes(s, "This is why it is fast. The pipeline is a dependency graph, not a list. The total time is the longest path through the "
             "graph, not the sum of all stages. The model phase costs the slowest reviewer, not five reviewers in a row, and the "
             "Docker build overlaps with four of them.")


def s_agents():
    s = new_slide("Multi-agent design", "Agents")
    rows = [["Agent", "Area", "Evidence it sees (picked from the shared index)"],
            ["Code Quality", "readability, size, duplication", "largest files, a diverse sample, duplication and comment metrics"],
            ["Architecture", "layers, coupling, API/DB design", "entrypoints, routes/services/models, dependency graph and cycles, compose"],
            ["Security", "OWASP Top 10", "secret-scanner and risky-pattern hits (redacted), auth files, .gitignore"],
            ["Testing", "unit, integration, e2e, CI", "test files, test-to-source ratio, CI workflows, test scripts"],
            ["DevOps & Docker", "containers and delivery", "Dockerfile, 20+ lint rules, build/run result, compose, CI"],
            ["Judge", "final verdict", "only the five compact structured reports, never raw code"]]
    table(s, 0.6, 1.55, 12.15, rows, [2.1, 3.0, 7.05], size=12.5, row_h=0.5)
    bullets(s, 0.6, 5.35, 12.2, 1.5, [
        ("Structured output:", "every call uses forced tool use with a JSON schema; scores are clamped and validated in code."),
        ("Bounded judge:", "can move each area by at most ±1.5 and must give a rationale; it calibrates, it does not re-grade."),
        ("Graceful degradation:", "a reviewer that errors or misses its deadline falls back to its rule-based scorer, and the report says so."),
    ], size=13, gap=4)
    notes(s, "Each reviewer sees only the evidence relevant to its area, chosen from one shared index of the repository. They must "
             "answer in a fixed JSON schema, so nothing is parsed from free text. The judge sees only their reports, which keeps it "
             "fast and cheap, and it is limited to small, explained adjustments.")


def s_scoring():
    s = new_slide("Scoring is computed in code", "Scoring")
    highlight(s, 0.6, 1.62, 8.75, 0.55)
    text(s, 0.7, 1.6, 9.2, 0.6, "final score = 10 × Σ (weight_area × score_area)", size=22, bold=True, font="Consolas")
    bullets(s, 0.6, 2.5, 6.4, 3.8, [
        ("Each area", "is scored 0–10 by its reviewer, then calibrated by the judge (±1.5 at most)."),
        ("Weights", "are set per assignment and shown to students before they submit (default: code 25%, architecture 25%, "
                    "testing 20%, security 15%, DevOps 15%)."),
        ("Best attempt counts:", "students can resubmit as often as they want."),
        ("Instructor adjustment:", "a score can be set by hand with a written reason; the original is kept and can be restored, "
                                   "and the student sees the reason."),
    ], size=14)
    rows = [["Grade", "A", "A-", "B", "B-", "C", "C-", "D", "F"], ["Score from", "85", "78", "70", "62", "55", "48", "40", "0"]]
    table(s, 7.3, 2.55, 5.45, rows, [1.25] + [0.525] * 8, size=13, row_h=0.45)
    box(s, 7.3, 3.7, 5.45, 2.4, "Why in code?", ["The same area scores always give the same total.",
                                                 "Every grade can be audited and explained.",
                                                 "Models judge quality; arithmetic stays deterministic."],
        fill=PAPER, line=PAPER, align=PP_ALIGN.LEFT, title_size=16, body_size=13, anchor=MSO_ANCHOR.TOP)
    notes(s, "The model never produces the final number. Each area gets a score from zero to ten, the judge can nudge it slightly, and "
             "the total is a weighted sum computed in code with the assignment's published weights. That makes grades reproducible. "
             "Instructors can still override a grade, but they must write a reason, the original is kept, and the student sees it.")


def s_latency():
    s = new_slide("Latency engineering", "Performance")
    rows = [["Technique", "Effect"],
            ["Fan-out of 5 reviewers", "model phase costs the slowest reviewer, not the sum"],
            ["Docker overlapped with reviewers", "build leaves the critical path"],
            ["Speculative clone ‖ ls-remote", "a cache miss pays nothing for resolution"],
            ["Content-addressed result cache", "unchanged code re-graded in 1.2 s"],
            ["Single-flight de-duplication", "identical in-flight requests share one job"],
            ["One-pass indexer", "35 ms for an 8-service repository"],
            ["Ranked evidence + char budgets", "3.6k–7.2k input tokens per reviewer"],
            ["Shared prompt prefix", "byte-identical across reviewers for prompt caching"],
            ["Capped output", "≤7 findings, short summaries (decoding dominates latency)"],
            ["Non-blocking I/O", "git, docker, indexing in worker threads; SSE keeps flowing"]]
    table(s, 0.6, 1.5, 12.15, rows, [4.6, 7.55], size=12.5, row_h=0.43)
    notes(s, "These are the techniques behind the speed, each with its effect. The biggest wins are running the reviewers in parallel, "
             "keeping Docker off the critical path, and caching results by commit so an unchanged project is re-graded in about a second.")


def s_results():
    s = new_slide("Measured results", "Performance")
    facts = [("27.5 s", "5 reviewers + judge, end to end"), ("75.5 s", "same stages in sequence"), ("2.74×", "speed-up from the graph"),
             ("1.2 s", "re-grade with a cache hit")]
    for i, (v, d) in enumerate(facts):
        box(s, 0.6 + i * 3.08, 1.55, 2.9, 1.5, v, d, line=PEN if i == 2 else INK, weight=1.5, title_size=30, body_size=12)
    text(s, 0.6, 3.25, 12.2, 0.5, "Benchmark: scripts/latency_benchmark.py on dockersamples/example-voting-app, real clone, index, lint and "
                                  "judge logic; model latency simulated (0.8 s to first token, 20k in / 70 out tokens per second).",
         size=12, color=INK3)
    rows = [["Stage", "Typical", "Hard limit"], ["Resolve + clone", "0.8–2.5 s", "120 s"], ["Index", "< 0.1 s", "5,000 files, 40 MB"],
            ["Each reviewer", "10–25 s", "120 s, then rule-based fallback"], ["Docker build + run", "20–300 s", "600 s + 8 s run"],
            ["Judge", "8–15 s", "150 s, then rule-based"]]
    table(s, 0.6, 3.9, 7.0, rows, [2.4, 1.7, 2.9], size=12.5, row_h=0.42)
    box(s, 7.9, 3.9, 4.85, 2.55, "Observed, not guessed", ["GET /api/metrics returns rolling p50 / p95 / max per stage.",
                                                          "Platform health and How it works show them live.",
                                                          "Critical path: clone → index → security → judge → report."],
        fill=PAPER, line=PAPER, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, title_size=15, body_size=12.5)
    notes(s, "On the benchmark repository the full grading takes 27.5 seconds instead of 75.5 if the stages ran one after another, "
             "a 2.74 times speed-up. A re-grade of unchanged code is answered from the cache in 1.2 seconds. Every stage has a hard "
             "limit, so the worst case is bounded, and the server reports its real p50 and p95 per stage.")


def s_reliability():
    s = new_slide("Reliability and scaling", "Engineering")
    bullets(s, 0.6, 1.55, 6.2, 5.0, [
        ("Timeouts everywhere:", "git, Docker, every model call and the judge."),
        ("Retries with backoff", "for 429 and 5xx; a global semaphore queues model calls instead of causing retry storms."),
        ("Admission control:", "a concurrency limit with a visible queue position."),
        ("Heartbeats every 20 s:", "a replica that stops is detected; its unfinished gradings are failed and its files cleaned."),
        ("Reports survive restarts:", "atomic writes plus a copy in PostgreSQL (free hosts wipe the disk)."),
        ("Replayable streams:", "events are stored in order; any replica serves them, and a dead replica's job ends with its saved outcome."),
    ], size=14)
    box(s, 7.1, 1.55, 5.65, 4.6, "Scaling path", ["Today: stateless replicas + durable event log: add replicas to scale.",
                                                  "1. PostgreSQL work queue: workers claim jobs with FOR UPDATE SKIP LOCKED; jobs survive restarts.",
                                                  "2. Separate web and worker roles (Autolab-style queue + worker pool).",
                                                  "3. Isolated Docker build workers, a fresh environment per submission.",
                                                  "4. Reports in object storage; retry one reviewer, not the whole job.",
                                                  "5. Courses: one deployment, many classes."],
        fill=PAPER, line=PAPER, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, title_size=16, body_size=13)
    notes(s, "Every external call has a deadline, failures degrade one area instead of the whole job, and replicas watch each other "
             "through heartbeats in the database so nothing hangs if one dies. Progress events are stored in the database, so adding "
             "replicas is enough to scale the web tier. The next step, following how Autolab scales, is a durable work queue in "
             "PostgreSQL using SKIP LOCKED, with separate worker processes that claim jobs.")


def s_security():
    s = new_slide("Security", "Engineering")
    rows = [["Threat", "Defence"],
            ["Malicious repository input", "only https://github.com/owner/repo; validated refs; no shell; git never prompts"],
            ["Secrets in student code", "9 scanner rules; values redacted before any prompt or report"],
            ["Untrusted Docker builds", "no network, 512 MB, 1 CPU, 256 pids, all caps dropped; opt-in only"],
            ["Stolen database", "scrypt password hashes; session tokens stored only as SHA-256"],
            ["Students reading others' data", "every instructor route checks the role on the server; reports only for their owner"],
            ["Password guessing", "throttled per client IP (Cloudflare header, never forgeable X-Forwarded-For) and per account"],
            ["Public demo misuse", "only a demo student login is public; sign-up closed; demo logins read-only"],
            ["Grade tampering", "adjusted grade pinned in every view until restored; no student endpoint writes a score"],
            ["Cross-site attacks", "SameSite + Secure cookies, cross-site request blocking, strict CSP, HSTS, no framing"],
            ["Spreadsheet injection", "CSV gradebook neutralises formulas"]]
    table(s, 0.6, 1.5, 12.15, rows, [3.6, 8.55], size=12.5, row_h=0.45)
    notes(s, "Security covers both the grader, which runs untrusted student code, and the platform. Repository input is restricted, "
             "secrets are redacted before anything reaches a model, and the Docker sandbox is locked down. On the platform side, "
             "roles are checked on the server for every instructor action, so a student cannot change any grade, sign-in is "
             "throttled against password guessing, and the public demo has only a student login. We verified these with "
             "an automated script of 44 checks.")


def s_student():
    s = new_slide("Student view: what to do next", "Students")
    picture(s, "student-dashboard", 0.6, 1.5, w=6.1)
    picture(s, "feedback", 6.95, 1.5, w=5.8)
    bullets(s, 0.6, 5.5, 12.2, 1.4, [
        ("Dashboard:", "the next assignment, the last result with the first three things to fix, progress, skills, deadlines."),
        ("Feedback:", "the score, marks by area with weights, numbered priorities with file names, topics to learn, every finding with its fix."),
    ], size=13, gap=4)
    notes(s, "The student view answers one question: what should I do next. The dashboard opens with the next assignment and the "
             "last result with the three most important fixes. The feedback page shows the score, marks by area with the rubric "
             "weights, the priorities with file names, and what to learn next.")


def s_instructor():
    s = new_slide("Instructor view: what needs attention", "Instructors")
    picture(s, "instructor-overview", 0.6, 1.5, w=7.2)
    bullets(s, 8.1, 1.55, 4.7, 5.2, [
        ("Needs your attention:", "shared repositories, failed gradings, students below 50, students who haven't started, low "
                                  "completion near a deadline, the weakest area."),
        ("Class numbers:", "active students, submissions, class average."),
        ("Assignments:", "completion, average and top score per assignment."),
        ("Latest submissions:", "filter by shared repo, failed, in progress."),
    ], size=13.5)
    notes(s, "The instructor view is built for a desk and dense information. The overview starts with a short list of things that "
             "need attention, so the instructor knows where to look first, followed by the class numbers and the assignment table.")


def s_insights():
    s = new_slide("Gradebook and assignment analytics", "Instructors")
    picture(s, "gradebook", 0.6, 1.5, w=6.0)
    picture(s, "assignment-analytics", 6.85, 1.5, w=5.9)
    bullets(s, 0.6, 5.4, 12.2, 1.5, [
        ("Gradebook:", "every student × assignment, late and adjusted marks, missing work after the deadline, class averages, CSV export."),
        ("Analytics:", "mean, median, spread, range, distribution, area averages, submissions per day, who hasn't submitted, possible copying."),
        ("Actions:", "adjust a grade with a reason, re-run one submission, or re-run the whole assignment after changing its rubric."),
    ], size=13, gap=4)
    notes(s, "Inspired by Gradescope and CodeGrade. The gradebook shows every student against every assignment. Each assignment has "
             "an analytics page with the statistics and the distribution, which students have not submitted, and possible copying, "
             "detected when two students submit the same repository or the same commit. From there the instructor can adjust a grade "
             "with a reason or re-run grading.")


def s_labs():
    s = new_slide("Hands-on labs", "Students")
    picture(s, "lab-sql", 0.6, 1.5, w=6.6)
    bullets(s, 7.5, 1.55, 5.3, 5.2, [
        ("Frontend:", "HTML, CSS and JS editor with a sandboxed live preview and DOM checks."),
        ("Databases:", "SQL on a real schema; the server checks answers; see an index change the query plan."),
        ("Load balancers:", "real requests through Nginx to the replicas: round-robin, least-connections, sticky."),
        ("Networks:", "round-trip time, jitter, proxy headers, Server-Timing breakdown."),
        ("Docker:", "fix a Dockerfile with the same 20+ rule linter the grader uses."),
        ("XP only for server-verified tasks,", "so the leaderboard can't be inflated from the browser."),
    ], size=13.5)
    notes(s, "The labs let students practise each layer. They are not simulations: the SQL lab runs real queries checked by the "
             "server, and the load-balancer lab sends real requests to the replicas.")


def s_data_stack():
    s = new_slide("Data model, stack and deployment", "Engineering")
    rows = [["Table", "Stores"], ["users", "students and instructors, scrypt hash, role"], ["sessions", "SHA-256 of session tokens, expiry"],
            ["assignments", "brief, track, rubric weights, checklist, deadline"],
            ["submissions", "each attempt: repo, status, score, area scores, priorities"],
            ["grade_overrides", "instructor adjustments: original, new, reason, who"],
            ["job_events", "progress events, so any replica can stream any job"],
            ["report_artifacts", "full HTML / Markdown / JSON reports"], ["lab_progress", "completed lab tasks"]]
    table(s, 0.6, 1.5, 6.4, rows, [2.1, 4.3], size=12, row_h=0.4)
    box(s, 7.3, 1.5, 5.45, 2.55, "Tech stack", ["Python 3.12, FastAPI, asyncio, Pydantic v2", "Claude API (forced tool use) or heuristics",
                                                "PostgreSQL (psycopg 3) or SQLite", "HTML/CSS/JS modules, SVG charts, SSE, PWA"],
        fill=PAPER, line=PAPER, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, title_size=16, body_size=13)
    box(s, 7.3, 4.25, 5.45, 2.4, "Deployment", ["Docker: multi-stage, non-root, healthcheck",
                                                "Render (free web service, auto-deploy from main)", "Neon PostgreSQL (free, Singapore)",
                                                "Local: docker compose = Nginx + 3 replicas + Postgres"],
        fill=PAPER, line=PAPER, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, title_size=16, body_size=13)
    notes(s, "Seven tables hold everything. The same SQL runs on SQLite for local use and PostgreSQL in production, without an ORM. "
             "The app ships as one Docker image that follows the same rules our DevOps reviewer checks.")


def s_limits():
    s = new_slide("Limitations and next steps", "Wrap-up")
    box(s, 0.6, 1.55, 5.9, 4.9, "Limitations today", None, fill=PAPER, line=PAPER, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
        title_size=17)
    bullets(s, 0.85, 2.15, 5.45, 4.2, [
        "A grading runs inside the server that accepted it; a restart fails it (the student resubmits).",
        "Docker builds run student RUN steps, so the sandbox is opt-in and meant for a dedicated VM.",
        "Copy detection compares repositories and commits, not code similarity.",
        "The free host sleeps after 15 minutes; the first visit takes about a minute.",
    ], size=14, marker_color=AMBER)
    box(s, 6.85, 1.55, 5.9, 4.9, "Next steps", None, line=RULE, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, title_size=17)
    bullets(s, 7.1, 2.15, 5.45, 4.2, [
        "PostgreSQL work queue (SKIP LOCKED) and worker roles: jobs survive restarts.",
        "Token-level similarity (JPlag-style) across submissions.",
        "Per-student containers so each student's backend runs on the platform.",
        "Regrade requests from students, deadline extensions per student.",
    ], size=14, marker_color=GREEN)
    notes(s, "Being honest about limits: a grading lives in the server that accepted it, the Docker sandbox is opt-in for safety, "
             "copy detection is by repository and commit, and the free host sleeps. The next steps address each of these.")


def s_demo():
    s = new_slide("Live demo", "Thank you")
    steps = [f"Open {LIVE_URL} (allow a minute if it was asleep)", "Sign in → Student view: dashboard, feedback, labs",
             "Submit a repository and watch the reviewers run", "Sign in with the instructor account",
             "Overview → Gradebook → an assignment's analytics", "How it works: architecture and live latency"]
    for i, st in enumerate(steps):
        y = 1.6 + i * 0.72
        box(s, 0.6, y, 0.55, 0.55, str(i + 1), fill=INK, line=INK, title_color=WHITE, title_size=15, radius=0.5)
        text(s, 1.35, y + 0.07, 6.6, 0.5, st, size=16)
    box(s, 8.2, 1.6, 4.55, 4.2, None, fill=PAPER, line=PAPER)
    text(s, 8.4, 1.8, 4.2, 4.0, [("Links", {"size": 18, "bold": True, "font": FONT_B}),
                                 (f"Live: {LIVE_URL}", {"size": 14, "space_before": 10}), (f"Code: {REPO_URL}", {"size": 14}),
                                 ("Design: docs/ARCHITECTURE.md", {"size": 13, "color": INK2, "space_before": 10}),
                                 ("Report: docs/AutoGrader-Report.pdf", {"size": 13, "color": INK2}),
                                 ("Demo logins are on the sign-in page", {"size": 13, "color": INK2, "space_before": 10})])
    text(s, 0.6, 6.2, 12.2, 0.6, "Questions?", size=30, bold=True, font=FONT_B, align=PP_ALIGN.CENTER)
    notes(s, "Demo plan: open the live site, look at the student side, submit a repository and watch the reviewers run in parallel, "
             "then the instructor side: overview, gradebook and an assignment's analytics, and finally the How it works page with the "
             "live latency numbers. Thank you; happy to take questions.")


for fn in (s_title, s_problem, s_overview, s_architecture, s_pipeline, s_dag, s_agents, s_scoring, s_latency, s_results,
           s_reliability, s_security, s_student, s_instructor, s_insights, s_labs, s_data_stack, s_limits, s_demo):
    fn()

assert len(prs.slides) == TOTAL_SLIDES, len(prs.slides)
prs.save(OUT)
print(f"wrote {OUT} ({len(prs.slides)} slides)")
