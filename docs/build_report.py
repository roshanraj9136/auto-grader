"""Generates docs/AutoGrader-Report.pdf: the written project report (A4), with screenshots from docs/img/.

    pip install playwright && python -m playwright install chromium   (or use an installed Chrome)
    python docs/build_report.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE / "AutoGrader-Report.pdf"
FONT = (HERE.parent / "web" / "fonts" / "mona-sans-latin.woff2").as_uri()
IMG = HERE / "img"
LIVE = "https://autograder-plus.onrender.com"
REPO = "https://github.com/roshanraj9136/auto-grader"


def img(name: str, caption: str) -> str:
    return f'<figure><img src="{(IMG / f"{name}.png").as_uri()}" alt=""><figcaption>{caption}</figcaption></figure>'


def table(head: list[str], rows: list[list[str]], cls: str = "") -> str:
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


CSS = f"""
@font-face {{ font-family: "Mona Sans"; src: url("{FONT}") format("woff2"); font-weight: 200 900; font-stretch: 75% 125%; }}
@page {{ size: A4; margin: 18mm 17mm 20mm; }}
* {{ box-sizing: border-box; }}
body {{ font: 10.2pt/1.55 "Mona Sans", "Segoe UI", sans-serif; color: #141c2e; margin: 0; }}
h1, h2, h3 {{ font-stretch: 112%; color: #141c2e; }}
h2 {{ font-size: 17pt; margin: 0 0 8pt; padding-top: 4pt; break-after: avoid; }}
h2 .n {{ color: #7f899b; margin-right: 8pt; }}
h3 {{ font-size: 11.5pt; margin: 14pt 0 5pt; break-after: avoid; }}
p {{ margin: 0 0 7pt; color: #2b3447; }}
section {{ break-before: page; }}
section.flow {{ break-before: auto; margin-top: 22pt; }}
ul, ol {{ margin: 0 0 8pt; padding-left: 16pt; color: #2b3447; }} li {{ margin: 0 0 3.5pt; }}
b {{ color: #141c2e; }}
code, .mono {{ font-family: Consolas, "Cascadia Code", monospace; font-size: 9pt; }}
table {{ width: 100%; border-collapse: collapse; margin: 6pt 0 10pt; font-size: 9.2pt; break-inside: avoid; }}
th {{ text-align: left; font-weight: 640; color: #4a5468; border-bottom: 1.2pt solid #141c2e; padding: 4pt 6pt; }}
td {{ border-bottom: .6pt solid #d5dbe3; padding: 4pt 6pt; vertical-align: top; color: #2b3447; }}
td:first-child {{ font-weight: 600; color: #141c2e; }}
table.plain td:first-child {{ font-weight: 400; }}
figure {{ margin: 8pt 0 12pt; break-inside: avoid; }}
figure img {{ width: 100%; border: .6pt solid #d5dbe3; border-radius: 4pt; display: block; }}
figcaption {{ font-size: 8.6pt; color: #7f899b; margin-top: 4pt; }}
.two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12pt; }}
.formula {{ font-family: Consolas, monospace; font-size: 10pt; background: #f1f3f6; border-left: 3pt solid #ffe14a; padding: 7pt 10pt; margin: 6pt 0 10pt; }}
.facts {{ display: grid; grid-template-columns: repeat(4, 1fr); border: .8pt solid #d5dbe3; border-radius: 6pt; margin: 10pt 0 12pt; }}
.facts div {{ padding: 8pt 10pt; }} .facts div + div {{ border-left: .8pt solid #d5dbe3; }}
.facts b {{ display: block; font-size: 17pt; font-stretch: 120%; }} .facts span {{ font-size: 8.4pt; color: #4a5468; }}
.cover {{ height: 255mm; display: flex; flex-direction: column; justify-content: space-between; }}
.cover .mark {{ width: 46pt; height: 46pt; border-radius: 10pt; background: #141c2e; color: #ffe14a; display: grid; place-items: center; font-size: 26pt; font-weight: 800; }}
.cover h1 {{ font-size: 44pt; line-height: 1; margin: 26pt 0 10pt; font-stretch: 122%; letter-spacing: -.02em; }}
.cover .sub {{ font-size: 16pt; color: #4a5468; margin: 0 0 18pt; }}
.cover .hl {{ background: linear-gradient(transparent 40%, #ffe14a 40%, #ffe14a 90%, transparent 90%); font-weight: 650; font-size: 12pt; }}
.cover .meta {{ font-size: 10.5pt; color: #4a5468; line-height: 1.8; }}
.toc {{ columns: 2; column-gap: 24pt; font-size: 10pt; padding-left: 16pt; }}
.arch {{ border: .8pt solid #d5dbe3; border-radius: 6pt; padding: 10pt; margin: 8pt 0 12pt; break-inside: avoid; }}
.arch .row {{ display: flex; align-items: center; gap: 6pt; flex-wrap: wrap; }}
.arch .node {{ border: 1.1pt solid #141c2e; border-radius: 4pt; padding: 4pt 7pt; font-size: 8.6pt; }}
.arch .node b {{ display: block; font-size: 9.2pt; }} .arch .node.pen {{ border-color: #2140d9; }} .arch .node.opt {{ border-style: dashed; color: #7f899b; }}
.arch .arrow {{ color: #7f899b; font-size: 12pt; }}
.arch .stack {{ display: flex; flex-direction: column; gap: 4pt; }}
.arch .deps {{ border-top: .8pt dashed #c9d0da; margin-top: 8pt; padding-top: 8pt; }}
.note {{ font-size: 9pt; color: #7f899b; }}
"""


def build_html() -> str:
    today = date.today().strftime("%B %Y")
    parts = [f"""
<div class="cover">
  <div>
    <div class="mark">&#10003;</div>
    <h1>AutoGrader+</h1>
    <p class="sub">Your repository, marked like a code review</p>
    <span class="hl">Multi-agent grading of full-stack projects, and a learning platform around it</span>
  </div>
  <div class="meta">
    <b>Project report</b><br>
    Live application: {LIVE}<br>
    Source code: {REPO}<br>
    CSL100 group project, {today}
  </div>
</div>
<section><h2>Contents</h2>
<ol class="toc">
<li>Summary</li><li>Problem and goals</li><li>System overview</li><li>Architecture</li><li>Grading pipeline</li>
<li>Multi-agent design</li><li>Scoring</li><li>Latency</li><li>Reliability and scaling</li><li>Security</li>
<li>Student experience</li><li>Instructor experience</li><li>Labs</li><li>Data model</li><li>Deployment and operations</li>
<li>API</li><li>Limitations and future work</li></ol>

<section class="flow"><h2><span class="n">1</span>Summary</h2>
<p>AutoGrader+ grades a <b>whole full-stack project</b> from its GitHub URL and returns an explainable report in about a minute.
Five specialist reviewers (code quality, architecture, security, testing, Docker &amp; DevOps) examine the repository <b>in parallel</b>;
a judge agent reads their five reports, calibrates the scores within a fixed bound and writes the verdict, the top priorities and a
learning path. The overall score is computed <b>in code</b> from the assignment's published rubric weights, so grades are reproducible.</p>
<p>Around the grader we built a learning platform with two role-specific views. Students get assignments with visible rubrics, live
grading progress, detailed feedback, a progress dashboard and hands-on labs. Instructors get a class overview that starts with what needs
attention, a gradebook, per-assignment analytics with copy detection, student profiles, grade adjustments with written reasons, and
re-grading. The system runs as stateless API replicas behind a load balancer with PostgreSQL, and is deployed on Render with Neon.</p>
<div class="facts"><div><b>6</b><span>agents per grading: 5 reviewers, 1 judge</span></div><div><b>2.74&times;</b><span>faster than the same stages in sequence</span></div>
<div><b>1.2 s</b><span>re-grade of unchanged code (cache hit)</span></div><div><b>47</b><span>automated security and access checks, all passing</span></div></div>
</section></section>

<section><h2><span class="n">2</span>Problem and goals</h2>
<p>Grading full-stack projects by hand is slow, because each submission combines a frontend, an API, a database and container
configuration; it is inconsistent, because different graders weigh issues differently; and feedback usually arrives after the deadline,
when it no longer helps. Instructors also lack an overview of who is struggling and whether students copied each other's work.</p>
{table(["Goal", "How the design meets it"], [
    ["Fast feedback", "Parallel pipeline (DAG), speculative clone, result cache, small ranked prompts, live progress over Server-Sent Events."],
    ["Bounded worst case", "A deadline on every stage; a reviewer that misses its deadline falls back to a deterministic scorer."],
    ["Reproducible, explainable grades", "Total computed in code from published weights; the judge may move each area by at most ±1.5 and must explain why."],
    ["Safe on untrusted code", "GitHub-only URL allow-list, no shell, secrets redacted before prompts, locked-down optional sandbox."],
    ["Useful to students", "Priorities with file names, fixes, a learning path, resubmission with the best attempt counting."],
    ["Useful to instructors", "Attention list, gradebook, assignment statistics, copy detection, grade adjustment, re-grading."],
    ["Works without an API key", "Every reviewer has a rule-based scorer; the same pipeline and report format are used (heuristic mode)."],
])}
</section>

<section class="flow"><h2><span class="n">3</span>System overview</h2>
<p>The system has three parts. The <b>grading engine</b> turns a repository into a report. The <b>student view</b> is built around one
question, "what should I do next?". The <b>instructor view</b> is built for a desk: dense tables, and the problems that need attention first.</p>
{table(["Area", "Reviewer checks"], [
    ["Code quality", "readability, file size, duplication, comments, linting"],
    ["Architecture", "layering, coupling, module dependency graph and cycles, API and database design, scalability"],
    ["Security", "OWASP Top 10 issues, hard-coded secrets, risky patterns, authentication and authorisation code"],
    ["Testing", "unit, integration and end-to-end tests, test-to-source ratio, CI that runs the tests"],
    ["Docker &amp; DevOps", "Dockerfile quality (20+ lint rules), multi-stage builds, non-root users, compose files, CI/CD"],
])}
</section>

<section><h2><span class="n">4</span>Architecture</h2>
<p>The application is a set of <b>stateless API replicas</b> behind an Nginx load balancer, sharing one PostgreSQL database. Each replica
serves the web app, the REST API and the live progress streams, and runs grading jobs.</p>
<div class="arch"><div class="row">
  <div class="node"><b>Browser / phone</b>web app, installable PWA</div><span class="arrow">&rarr;</span>
  <div class="node"><b>Nginx load balancer</b>round-robin, least-conn, sticky</div><span class="arrow">&rarr;</span>
  <div class="stack"><div class="node pen"><b>API replica 1</b>FastAPI: REST, SSE, grading engine</div><div class="node pen"><b>API replica 2</b>identical, no local state</div>
  <div class="node pen"><b>API replica 3</b>scale with --scale api=N</div></div></div>
  <div class="row deps"><span class="note">Each replica uses:</span>
  <div class="node"><b>PostgreSQL</b>accounts, grades, reports</div><div class="node"><b>GitHub</b>shallow clone</div>
  <div class="node"><b>Claude API</b>5 reviewer calls + 1 judge call</div><div class="node opt"><b>Docker sandbox</b>optional build and run</div></div></div>
<ul>
<li><b>Shared state lives in PostgreSQL</b>: users, sessions, assignments, submissions, grade adjustments, reports, lab progress, replica heartbeats. Any replica can serve any page.</li>
<li><b>Live progress is durable</b>: a job runs in the replica that accepted it and fans out its events in memory, and one writer task per replica also appends every event, in order, to the <code>job_events</code> table. A replica that does not hold the job streams it from that table, so any replica can serve any job's progress and sticky routing is no longer required.</li>
<li><b>Locally</b>, <code>docker compose up</code> starts Nginx, three API replicas and PostgreSQL on a private network. <b>In production</b> one container runs on Render with a Neon PostgreSQL database; the code is the same.</li>
</ul>
<h3>Layers in the code</h3>
{table(["Layer", "Responsibility", "Code"], [
    ["Web app", "Single-page app in plain JavaScript modules: role-specific layouts, live progress, SVG charts, PWA", "<span class='mono'>web/</span>"],
    ["HTTP API", "Validation, sessions, REST, Server-Sent Events, report downloads, security headers", "<span class='mono'>app/main.py</span>"],
    ["Platform", "Accounts, assignments, dashboards, instructor analytics, gradebook, labs, demo class", "<span class='mono'>app/platform/</span>"],
    ["Grading engine", "Job queue with admission control and de-duplication, the pipeline DAG, tracing, metrics", "<span class='mono'>app/jobs.py, app/pipeline.py</span>"],
    ["Agents", "Five specialists and the judge, structured output, heuristic fallbacks", "<span class='mono'>app/agents/</span>"],
    ["Ingest, sandbox", "Git, one-pass repository index, evidence selection, Dockerfile linter, sandbox", "<span class='mono'>app/ingest/, app/sandbox/</span>"],
    ["Reports", "HTML / Markdown / JSON reports, content-addressed result cache", "<span class='mono'>app/report/</span>"],
])}
</section>

<section><h2><span class="n">5</span>Grading pipeline</h2>
<p>A submission becomes a <b>job</b>, which runs as a dependency graph so that independent stages overlap.</p>
<ol>
<li><b>Admission.</b> A semaphore limits concurrent jobs and reports a queue position. An identical in-flight request attaches to the running job (single-flight).</li>
<li><b>Resolve and clone in parallel.</b> <code>git ls-remote</code> finds the exact commit while a shallow, single-branch, tag-less clone starts speculatively.</li>
<li><b>Cache lookup.</b> The same commit, Dockerfile, rubric and models return the stored report (about 1.2 s); the clone is cancelled and its process tree killed.</li>
<li><b>Index.</b> One pass over the repository (about 35 ms for an 8-service repository) builds a read-only index: languages, file sizes, tests, CI, Dockerfiles, the module dependency graph, and a secret scan whose matches are redacted.</li>
<li><b>Docker.</b> A static linter with 20+ rules always runs. A locked-down build and smoke run is optional.</li>
<li><b>Five reviewers in parallel.</b> Each receives the evidence relevant to its area within a character budget (about 3.6k to 7.2k tokens) and must answer through forced tool use with a JSON schema.</li>
<li><b>Judge.</b> Reads only the five compact reports (about 1k tokens), may move each area by at most ±1.5 with a rationale, and writes the summary, priorities and learning path.</li>
<li><b>Report.</b> The final score is computed in code; HTML, Markdown and JSON reports are written atomically to disk and copied into PostgreSQL; the browser receives the final event.</li>
</ol>
<h3>Critical path</h3>
<div class="formula">T_total &asymp; max(T_resolve, T_clone) + max(T_index + max(T_reviewer 1&ndash;4), T_docker + T_devops) + T_judge</div>
<p>Only the DevOps reviewer waits for Docker; the other four start as soon as indexing finishes, so a slow build overlaps with model
calls. Every report records its measured critical path (found by walking back from the report along the dependency that finished last)
and the speed-up <code>T_sequential / T_total</code>.</p>
</section>

<section class="flow"><h2><span class="n">6</span>Multi-agent design</h2>
{table(["Agent", "Evidence it receives (selected from the shared index)"], [
    ["Code Quality", "largest files and a diverse sample across modules, duplication and comment metrics"],
    ["Architecture", "entrypoints, routes / services / models, module dependency graph and cycles, compose, nginx, k8s files"],
    ["Security", "secret-scanner and risky-pattern hits (as leads to verify), authentication files, .gitignore"],
    ["Testing", "test files, test-to-source ratio, CI workflows, test scripts"],
    ["DevOps &amp; Docker", "Dockerfile, lint findings, build and run result and logs, compose, CI"],
    ["Judge", "only the five structured reports, never raw code"],
])}
<ul>
<li><b>Structured output.</b> Every call uses forced tool use with a JSON schema; nothing is parsed from free text. Scores are clamped and validated in code. Findings are capped at seven per reviewer.</li>
<li><b>Bounded judge.</b> The judge calibrates rather than re-grades: each area can move by at most ±1.5 and every change needs a rationale.</li>
<li><b>Graceful degradation.</b> If a model call fails or misses its deadline, only that reviewer falls back to its rule-based scorer, and the report marks it.</li>
<li><b>Prompt layout.</b> The tool definitions and the shared repository context are byte-identical across the five reviewer prompts, so the provider's prompt cache can reuse them on re-grades.</li>
</ul>
</section>

<section><h2><span class="n">7</span>Scoring</h2>
<div class="formula">final score = 10 &times; &Sigma; (weight_area &times; score_area), with weights summing to 1 and area scores from 0 to 10</div>
<p>The formula runs in code, so the same area scores always give the same total and every grade can be audited. Weights are set per
assignment and shown to students before they submit; the defaults are code quality 25%, architecture 25%, testing 20%, security 15% and
Docker &amp; DevOps 15%. A student may resubmit as often as they like and the <b>best</b> attempt counts.</p>
{table(["Grade", "A", "A-", "B", "B-", "C", "C-", "D", "F"], [["Score from", "85", "78", "70", "62", "55", "48", "40", "0"]])}
<h3>Instructor adjustments</h3>
<p>An instructor can set a graded submission's score by hand. A reason is mandatory; the original score, the new score, the reason, the
instructor and the time are stored in <code>grade_overrides</code>. The student sees the adjusted score and the reason on their feedback
page, and the instructor can restore the original at any time. Adjusted rows are protected from being overwritten if the job's state
is ever replayed.</p>
</section>

<section class="flow"><h2><span class="n">8</span>Latency</h2>
{table(["Technique", "Effect"], [
    ["Fan-out of 5 reviewers", "the model phase costs the slowest reviewer, not the sum of five"],
    ["Docker overlapped with reviewers", "the build leaves the critical path unless it is the longest branch"],
    ["Speculative clone &#8214; ls-remote", "a cache miss pays nothing for resolution; on a hit the clone is cancelled"],
    ["Content-addressed result cache", "unchanged code with an unchanged rubric is answered in about 1.2 s"],
    ["Single-flight de-duplication", "identical in-flight requests share one job"],
    ["Shallow, single-branch, tag-less clone", "minimum objects transferred"],
    ["One-pass indexer", "35 ms for an 8-service repository; no reviewer re-reads the disk"],
    ["Ranked evidence with budgets", "3.6k&ndash;7.2k input tokens per reviewer keeps prefill short"],
    ["Capped output, concise schema", "decoding dominates model latency, so output is kept short"],
    ["Small judge input", "the only sequential model call reads about 1k tokens"],
    ["Global model-call semaphore", "bursts queue locally instead of causing rate-limit retry storms"],
    ["Non-blocking I/O", "git, Docker and indexing run in worker threads; live streams keep flowing"],
])}
<h3>Benchmark</h3>
<p class="note">scripts/latency_benchmark.py on dockersamples/example-voting-app: real clone, index, lint, evidence and judge logic; model latency
simulated as 0.8 s to first token, 20k input and 70 output tokens per second, so the figures isolate the architecture's effect.</p>
{table(["Metric", "Value"], [["Wall-clock, 5 reviewers + judge", "27.5 s"], ["Same stages run sequentially", "75.5 s"],
    ["Speed-up from the DAG", "2.74&times;"], ["Measured critical path", "clone &rarr; index &rarr; security &rarr; judge &rarr; report"],
    ["Cache-hit re-grade (real)", "1.2 s"], ["Index (real)", "34&ndash;38 ms"]])}
{table(["Stage", "Typical", "Hard limit"], [["Resolve and clone", "0.8&ndash;2.5 s", "120 s"], ["Index", "&lt; 0.1 s", "5,000 files, 40 MB read"],
    ["Each reviewer", "10&ndash;25 s", "120 s, then rule-based fallback"], ["Docker build and smoke run", "20&ndash;300 s", "600 s + 8 s run"],
    ["Judge", "8&ndash;15 s", "150 s, then rule-based calibration"]])}
<p><code>GET /api/metrics</code> returns rolling p50, p95 and maximum latency per stage, shown live on the Platform health and How it works pages,
so tail latency is observed rather than guessed.</p>
</section>

<section><h2><span class="n">9</span>Reliability and scaling</h2>
<ul>
<li><b>Deadlines</b> on git, Docker, every model call and the judge; the SDK retries 429 and 5xx responses with exponential backoff.</li>
<li><b>Admission control</b> with a FIFO queue and a visible position; failed or cancelled jobs cancel their background work and always delete their workspace.</li>
<li><b>Heartbeats.</b> Every replica writes a heartbeat every 20 s. Any replica fails the unfinished submissions of a replica that stopped (crash, scale-down, recreated container), removes its orphaned clone directories, and repairs its own rows if a state update was lost.</li>
<li><b>Durable reports.</b> Artifacts are written atomically and copied into PostgreSQL, so they survive free hosts whose disk is wiped on restart, and replicas without a shared volume.</li>
<li><b>Database pool</b> of at most 10 connections per replica, pinged before reuse; schema creation and seeding are serialised with a PostgreSQL advisory lock so replicas can start together.</li>
<li><b>Replayable streams.</b> Because events are stored, a stream continues on any replica; if the replica running a job dies, the stream ends with the saved outcome once peers mark the submission failed. A two-replica test on one database confirmed that the second replica replays exactly the same 33-event sequence.</li>
</ul>
<h3>Scaling path</h3>
<p>Today the web tier scales by adding replicas. The next steps follow how large course autograders are built; Autolab's grader (Tango)
splits a job queue from a job manager that hands jobs to free workers, and runs 2,000+ daily submissions across six grading servers at the
University at Buffalo.</p>
<ol><li><b>A durable work queue in PostgreSQL.</b> Workers claim jobs with <code>UPDATE &hellip; WHERE id = (SELECT id &hellip; FOR UPDATE SKIP LOCKED LIMIT 1)</code>: many workers drain one table without blocking each other, jobs survive restarts, and no new infrastructure is needed (sound up to a few thousand jobs per second).</li>
<li><b>Separate web and worker roles</b> from the same image, scaled independently.</li>
<li><b>Isolated build workers</b> (BuildKit, or Kubernetes Jobs with gVisor or Kata), one fresh environment per submission.</li>
<li><b>Object storage</b> (S3 or MinIO) for reports; <b>per-area retries</b> instead of re-running a whole job.</li>
<li><b>Courses</b>, so one deployment serves many classes, and <b>shared rate limits</b> in Redis across replicas.</li></ol>
</section>

<section class="flow"><h2><span class="n">10</span>Security</h2>
{table(["Threat", "Defence"], [
    ["Malicious repository input", "Only https://github.com/owner/repo is accepted (blocks file://, ext::, SSH and SSRF); refs are validated and cannot start with '-'; every subprocess runs with an argument list, never a shell; git never prompts for credentials."],
    ["Secrets in student code", "Nine scanner rules run during indexing; matched values are redacted before any prompt or report."],
    ["Untrusted Docker builds", "Containers run with --network none, 512 MB, 1 CPU, 256 processes, all capabilities dropped and no-new-privileges; the sandbox is opt-in."],
    ["Stolen database", "scrypt password hashes with per-user salts; 256-bit session tokens stored only as SHA-256, so a leaked database cannot be replayed as sessions."],
    ["Students changing grades", "Every instructor endpoint checks the role on the server. No student endpoint writes a score. Students can read only their own submissions and reports."],
    ["Password and join-code guessing", "Sign-in is throttled per IP (10 failures / 15 min) and per account (20 / 15 min); wrong join codes are throttled per IP; comparisons are constant-time; unknown emails take as long to reject as wrong passwords."],
    ["Public demo misuse", "The demo instructor is read-only on the server (no grade, assignment or re-grade changes); real students' emails are hidden from it; demo logins cannot change their password or name; nobody can sign up under the demo domains."],
    ["Cross-site attacks", "HttpOnly, SameSite=Lax, Secure cookies; state-changing API calls from other sites are rejected (Fetch Metadata and Origin checks); strict Content-Security-Policy; HSTS; framing by other sites is blocked; the frontend lab runs student code in a sandboxed iframe."],
    ["Spreadsheet injection", "The CSV gradebook neutralises cells that start with =, +, - or @."],
])}
<h3>Verification</h3>
<p>An automated script (<code>scripts/security_check.py</code>) signs in as an anonymous visitor, a student, the public demo instructor and the
real instructor and runs 47 checks, including: students and visitors are refused every instructor endpoint; students cannot adjust, re-grade,
create or delete; the demo instructor cannot change anything; adjustments are validated (0&ndash;100, reason required) and reversible;
students cannot read other students' reports; reserved emails cannot be registered; brute-force sign-in is throttled; cross-site requests are
blocked; security headers are present. All 47 pass.</p>
</section>

<section><h2><span class="n">11</span>Student experience</h2>
<p>The student dashboard opens with <b>Up next</b> (the nearest unsubmitted assignment, or the one with most room to improve) and the
<b>last result</b> with the first three things to fix, followed by the average score, assignments and lab tasks done, class rank, score
history, a five-area skill profile, deadlines and the learning path.</p>
{img("student-dashboard", "Student dashboard")}
<p>Each assignment shows its brief, the checklist that will be checked and the weight of each area. After submitting, the student watches
the four stages and the five reviewers live. The feedback page shows the score and grade, marks by area with their weights, the numbered
priorities with file names, topics to learn, and every finding with its fix; an instructor's adjustment and reason appear at the top.</p>
{img("feedback", "Feedback for one submission")}
</section>

<section><h2><span class="n">12</span>Instructor experience</h2>
<p>The instructor workspace uses top tabs and dense, condensed tables. The <b>overview</b> starts with <b>Needs your attention</b>:
repositories submitted by more than one student, gradings that failed, students averaging below 50, students who have not submitted
anything, deadlines within a week with low completion, and the class's weakest area. Below are the class numbers, the grade distribution,
the assignment table and the latest submissions with filters.</p>
{img("instructor-overview", "Instructor overview")}
<div class="two">{img("gradebook", "Gradebook: every student and assignment, with late, adjusted and missing marks")}
{img("student-profile", "Student profile: history, skills, attempts and labs")}</div>
<h3>Assignment analytics</h3>
<p>Each assignment has its own page: submitted count, mean, median, standard deviation, range, students below 50 and late attempts; the
score distribution in bands of ten; averages per area; submissions per day; the list of students who have not submitted; and
<b>possible copying</b>, detected when two students submit the same repository, or the same commit in different repositories (an unchanged fork).
From the student table the instructor opens feedback, <b>adjusts a grade</b> with a reason, or <b>re-runs</b> a submission; "Re-run all"
grades every student's latest submission again after a rubric change.</p>
{img("assignment-analytics", "Assignment analytics")}
{img("adjust-grade", "Adjusting a grade: a reason is required and the original can be restored")}
</section>

<section><h2><span class="n">13</span>Labs</h2>
{table(["Lab", "What students practise", "How it is checked"], [
    ["Frontend", "HTML, CSS and JS editor with a live preview in an opaque-origin sandboxed iframe", "DOM checks in the sandbox"],
    ["Databases", "SQL joins, GROUP BY, and an index that turns a table scan into a search", "server runs the query on a fresh read-only in-memory copy and compares with a reference (XP)"],
    ["Load balancers", "round-robin, least-connections and sticky routing across real replicas", "real requests through Nginx; replica identity in X-Served-By"],
    ["Networks", "round-trip time and jitter, proxy headers, Server-Timing breakdown", "Resource Timing API and the backend's Server-Timing header"],
    ["Docker", "fix a Dockerfile until the linter is clean, multi-stage, non-root with a healthcheck", "the grader's own 20+ rule linter on the server (XP)"],
])}
<p>Only tasks verified by the server earn XP, so the leaderboard cannot be inflated with forged browser calls.</p>
{img("lab-sql", "SQL lab")}
</section>

<section><h2><span class="n">14</span>Data model</h2>
{table(["Table", "Contents"], [
    ["users", "students and instructors: name, entry number, email, scrypt hash, role"],
    ["sessions", "SHA-256 of each session token, expiry"],
    ["assignments", "title, brief, track, rubric weights, checklist, deadline, author"],
    ["submissions", "one row per attempt: repository, ref, status, final score, grade, area scores, summary, priorities, learning path, commit, timing"],
    ["grade_overrides", "instructor adjustments: original score and grade, new score and grade, reason, instructor, time"],
    ["report_artifacts", "full HTML, Markdown and JSON report of every finished grading"],
    ["job_events", "every progress event of recent gradings (pruned after 3 days), so any replica can replay a live stream"],
    ["lab_progress", "completed lab tasks per student"],
    ["instances, meta", "replica heartbeats; one-time setup markers"],
])}
<p>The same SQL runs on SQLite (local default) and PostgreSQL (production) through a thin DB-API layer, without an ORM.</p>

<section class="flow"><h2><span class="n">15</span>Deployment and operations</h2>
<ul>
<li><b>Image:</b> multi-stage Docker build, pinned base images, dependencies installed before source for layer caching, non-root user, health check, exec-form command.</li>
<li><b>Production:</b> Render web service (free plan, Singapore, auto-deploys every push to main) with a Neon PostgreSQL database (free, Singapore). Reports are stored in the database because the free plan's disk is wiped on restart; the service sleeps after 15 idle minutes and wakes in about a minute.</li>
<li><b>Public demo mode</b> (<code>AUTOGRADER_DEMO_SEED=1</code>): demo student and read-only demo instructor logins, and a sample class whose public repositories are graded by the real pipeline on start-up. Turn it off for a real class.</li>
<li><b>Local:</b> <code>docker compose up</code> runs Nginx, three replicas and PostgreSQL; <code>scripts/start.ps1</code> runs a single process with SQLite.</li>
<li><b>Configuration:</b> database URL, instructor account, class join code, demo mode, Docker sandbox, concurrency, model names and timeouts are environment variables.</li>
</ul>
</section></section>

<section><h2><span class="n">16</span>API</h2>
{table(["Method and path", "Purpose", "Who"], [
    ["POST /api/auth/signup, /login, /logout", "accounts; HttpOnly session cookie", "anyone"],
    ["GET /api/student/dashboard", "everything the student dashboard shows", "student"],
    ["GET /api/assignments, /api/assignments/{{id}}", "assignments with rubric and the caller's attempts", "signed in"],
    ["POST /api/assignments/{{id}}/submit", "grade a repository with the assignment's rubric (202 + job id)", "signed in"],
    ["GET /api/jobs/{{id}}/events", "Server-Sent Events: stage and agent progress, verdict", "owner, instructor"],
    ["GET /api/jobs/{{id}}/report[.html|.md|.json]", "the report", "owner, instructor"],
    ["GET /api/instructor/overview, /students", "class analytics and student list", "instructor"],
    ["GET /api/instructor/gradebook[.csv]", "gradebook matrix (JSON) or CSV export", "instructor"],
    ["GET /api/instructor/assignments/{{id}}", "assignment statistics, distribution, copying, per-student rows", "instructor"],
    ["GET /api/instructor/students/{{id}}", "one student's profile", "instructor"],
    ["POST/DELETE /api/instructor/submissions/{{id}}/override", "adjust a grade with a reason / restore the original", "real instructor"],
    ["POST /api/instructor/submissions/{{id}}/regrade", "grade a submission again", "real instructor"],
    ["POST /api/instructor/assignments/{{id}}/regrade", "re-run every student's latest submission", "real instructor"],
    ["POST /api/lab/sql, /api/lab/dockerfile", "server-verified lab tasks", "anyone (XP when signed in)"],
    ["GET /api/health, /api/metrics", "health and per-stage latency", "anyone"],
], "plain")}
<p class="note">Interactive OpenAPI documentation is served at /docs on every instance.</p>

<section class="flow"><h2><span class="n">17</span>Limitations and future work</h2>
<ul>
<li>A grading runs inside the replica that accepted it, so a restart fails it and the student resubmits; the PostgreSQL work queue above would make jobs survive restarts.</li>
<li><code>docker build</code> executes the student's RUN steps with network access, so the sandbox is opt-in and intended for a dedicated VM or rootless Docker.</li>
<li>Copy detection compares repositories and commits; token-level similarity (as in JPlag) across submissions is the natural next step.</li>
<li>The free host sleeps when idle, so the first visit after a quiet period takes about a minute.</li>
<li>Further features: regrade requests from students, per-student deadline extensions, and per-student containers so each student's backend runs on the platform itself.</li>
</ul>
</section></section>
"""]
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(parts)}</body></html>"


def main() -> None:
    html_path = HERE / "_report.html"
    html_path.write_text(build_html(), encoding="utf-8")
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="chrome")
            except Exception:  # noqa: BLE001 - fall back to Playwright's bundled Chromium
                browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(html_path.as_uri())
            page.wait_for_timeout(500)
            page.pdf(path=str(OUT), format="A4", print_background=True, display_header_footer=True,
                     header_template="<span></span>",
                     footer_template="<div style='width:100%;font:8px Segoe UI,sans-serif;color:#7f899b;padding:0 17mm;"
                                     "display:flex;justify-content:space-between'><span>AutoGrader+ project report</span>"
                                     "<span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>",
                     margin={"top": "18mm", "bottom": "20mm", "left": "17mm", "right": "17mm"})
            browser.close()
    finally:
        html_path.unlink(missing_ok=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
