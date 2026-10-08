// Public "How it works" page: architecture, grading pipeline, scoring, latency (with this server's live numbers),
// reliability, security, data model and features. Written to be read top to bottom or presented section by section.
import { api, esc, fmtMs } from "../core.js";

const TOC = [["overview", "Overview"], ["architecture", "Architecture"], ["pipeline", "Grading pipeline"], ["scoring", "Scoring"],
  ["latency", "Latency"], ["reliability", "Reliability"], ["scaling", "Scaling"], ["security", "Security"], ["data", "Data model"],
  ["features", "Features"], ["stack", "Tech stack"]];

const STAGE_NAMES = {
  resolve: "Resolve commit (git ls-remote)", clone: "Shallow clone", cache_lookup: "Result-cache lookup", index: "Index the repository",
  docker: "Dockerfile lint / build", "agent:code_quality": "Reviewer: code quality", "agent:architecture": "Reviewer: architecture",
  "agent:security": "Reviewer: security", "agent:testing": "Reviewer: testing", "agent:devops": "Reviewer: Docker & DevOps",
  judge: "Judge", report: "Write the report", job_total: "Whole grading (end to end)",
};

function liveLatency(m) {
  const rows = Object.entries(m?.stages || {}).filter(([, s]) => s.count);
  if (!rows.length) {
    return `<p class="hint">No gradings have run on this server since it last started, so there are no live numbers yet.
      They appear here after the first submission.</p>`;
  }
  return `<div class="table-wrap"><table><thead><tr><th>Stage</th><th class="num">Runs</th><th class="num">Typical (p50)</th>
    <th class="num">Slow (p95)</th><th class="num">Slowest</th></tr></thead><tbody>
    ${rows.map(([n, s]) => `<tr><td>${esc(STAGE_NAMES[n] || n)}</td><td class="num">${s.count}</td><td class="num">${esc(fmtMs(s.p50_ms))}</td>
      <td class="num">${esc(fmtMs(s.p95_ms))}</td><td class="num">${esc(fmtMs(s.max_ms))}</td></tr>`).join("")}</tbody></table></div>`;
}

const node = (title, sub, cls = "") => `<div class="ar-node ${cls}"><b>${title}</b><span>${sub}</span></div>`;

export async function page(view) {
  const [health, metrics] = await Promise.all([api("/api/health").catch(() => null), api("/api/metrics").catch(() => null)]);
  const mode = health ? (health.llm_mode ? `LLM mode (${esc(health.agent_model)})` : "heuristic mode (no API key set)") : "unknown mode";
  view.innerHTML = `
  <div class="doc">
    <aside class="doc-toc" aria-label="On this page"><p>On this page</p>
      <nav>${TOC.map(([id, t]) => `<a href="#${id}" data-anchor="${id}">${t}</a>`).join("")}</nav></aside>
    <article class="doc-body">
      <header class="doc-head">
        <h1>How AutoGrader+ works</h1>
        <p class="sub">Everything that happens between pasting a GitHub link and reading the feedback, the design decisions behind it,
          and the numbers that show how fast it is.</p>
      </header>

      <section id="overview">
        <h2>Overview</h2>
        <p>AutoGrader+ grades a <b>whole full-stack project</b> from its GitHub URL. Five specialist reviewers each examine one area
          (code quality, architecture, security, testing, Docker &amp; DevOps) <b>at the same time</b>. A sixth agent, the <b>judge</b>,
          reads their five reports, calibrates the scores and writes the verdict, the top priorities and a learning path.</p>
        <p>Around the grader sits a <b>learning platform</b>. Students get assignments with visible rubrics, live grading progress,
          detailed feedback, a progress dashboard and hands-on labs. Instructors get class analytics, a gradebook, per-assignment
          statistics, copy detection, grade adjustments and re-grading.</p>
        <p>The reviewers run on Claude models (<b>LLM mode</b>) or, without an API key, on deterministic rule-based scorers that use the
          same pipeline and report format (<b>heuristic mode</b>). This server is running in <b>${mode}</b>${health ? `, with ${esc(health.database.engine)} as its database` : ""}.</p>
        <div class="doc-facts">
          <div><b>6</b><span>agents per grading: 5 reviewers and 1 judge</span></div>
          <div><b>2.74×</b><span>faster than running the same stages one after another</span></div>
          <div><b>1.2 s</b><span>to return a cached result for code that was already graded</span></div>
          <div><b>±1.5</b><span>the most the judge may move any area's score, always with a reason</span></div>
        </div>
      </section>

      <section id="architecture">
        <h2>Architecture</h2>
        <p>The system is a set of stateless API replicas behind a load balancer, sharing one PostgreSQL database. Each replica serves
          the web app, the REST API, live progress streams and runs grading jobs.</p>
        <div class="ar" role="img" aria-label="Browser or phone, over HTTPS, to the Nginx load balancer, to three API replicas, which use PostgreSQL, GitHub, the Claude API and an optional Docker sandbox">
          <div class="ar-row">${node("Browser / phone", "web app, installable (PWA)")}<i class="ar-arrow" aria-hidden="true">HTTPS</i>
            ${node("Nginx load balancer", "round-robin, least-connections or sticky")}<i class="ar-arrow" aria-hidden="true"></i>
            <div class="ar-stack">${node("API replica 1", "FastAPI: REST, SSE, grading engine", "main")}${node("API replica 2", "same code, no local state", "main")}${node("API replica 3", "scale with --scale api=N", "main")}</div></div>
          <div class="ar-row ar-deps"><span class="ar-label">Each replica uses</span>
            ${node("PostgreSQL", "accounts, grades, reports (private network)")}${node("GitHub", "shallow clone of the submitted repo")}
            ${node("Claude API", "5 reviewer calls + 1 judge call")}${node("Docker sandbox", "optional build and smoke run", "opt")}</div>
        </div>
        <p class="hint">Every progress event is also stored in PostgreSQL, so any replica can stream any job.
          Locally, <code>docker compose up</code> starts exactly this: Nginx, three API replicas and PostgreSQL on a private network.
          The public deployment runs one container on Render with a Neon PostgreSQL database; the code is the same.</p>
        <h3>Layers in the code</h3>
        <div class="table-wrap"><table><tbody>
          <tr><td><b>Web app</b></td><td>Single-page app in plain JavaScript (no build step): role-specific layouts, live progress, charts.</td><td class="mono">web/</td></tr>
          <tr><td><b>HTTP API</b></td><td>Validation, sessions, REST endpoints, Server-Sent Events, report downloads, security headers.</td><td class="mono">app/main.py</td></tr>
          <tr><td><b>Platform</b></td><td>Accounts, assignments, dashboards, instructor analytics, gradebook, labs.</td><td class="mono">app/platform/</td></tr>
          <tr><td><b>Grading engine</b></td><td>Job queue with admission control, the pipeline DAG, tracing and metrics.</td><td class="mono">app/jobs.py, app/pipeline.py</td></tr>
          <tr><td><b>Agents</b></td><td>Five specialists and the judge, structured output, heuristic fallbacks.</td><td class="mono">app/agents/</td></tr>
          <tr><td><b>Ingest and sandbox</b></td><td>Git operations, one-pass repository index, evidence selection, Dockerfile linter and sandbox.</td><td class="mono">app/ingest/, app/sandbox/</td></tr>
          <tr><td><b>Reports</b></td><td>HTML, Markdown and JSON reports; content-addressed result cache.</td><td class="mono">app/report/</td></tr>
        </tbody></table></div>
      </section>

      <section id="pipeline">
        <h2>Grading pipeline</h2>
        <p>A submission becomes a <b>job</b>. The job runs as a dependency graph (DAG), so independent stages overlap instead of waiting
          for each other. The browser watches each stage live over Server-Sent Events.</p>
        <ol class="doc-steps">
          <li><b>Admission.</b> The job manager limits how many gradings run at once, shows a queue position, and attaches identical
            in-flight requests to the running job instead of starting a second one (single-flight).</li>
          <li><b>Resolve and clone, in parallel.</b> <code>git ls-remote</code> finds the exact commit while a shallow, single-branch clone starts speculatively.</li>
          <li><b>Cache lookup.</b> Same commit, Dockerfile, rubric and models as an earlier grading: the stored report comes back in about 1.2 s and the clone is cancelled.</li>
          <li><b>Index.</b> One pass over the repository (about 35 ms): languages, file sizes, tests, CI, Dockerfiles, the module dependency graph, and a secret scan whose matches are redacted before anything reaches a model.</li>
          <li><b>Docker.</b> A 20+ rule Dockerfile linter always runs; a locked-down build and smoke run is optional.</li>
          <li><b>Five reviewers, at the same time.</b> Each receives only the evidence relevant to its area (about 3.6k to 7.2k tokens) and must answer in a fixed JSON schema: a 0 to 10 score, strengths, and findings with severity, file and fix.</li>
          <li><b>Judge.</b> Reads the five compact reports (about 1k tokens, never the raw code), may move each area by at most ±1.5 with a written reason, and writes the summary, top priorities and learning path.</li>
          <li><b>Report.</b> The final score is computed in code from the rubric weights. The HTML, Markdown and JSON reports are saved to disk and to PostgreSQL, and the browser is told the job is done.</li>
        </ol>
        <div class="dag" role="img" aria-label="Pipeline graph: resolve and clone run in parallel; cache lookup; index and Docker; five reviewers in parallel; judge; report">
          <div class="dag-col"><span>resolve</span><span>clone</span></div><i aria-hidden="true"></i>
          <div class="dag-col"><span>cache</span></div><i aria-hidden="true"></i>
          <div class="dag-col"><span>index</span><span>docker</span></div><i aria-hidden="true"></i>
          <div class="dag-col five"><span>code quality</span><span>architecture</span><span>security</span><span>testing</span><span>devops</span></div><i aria-hidden="true"></i>
          <div class="dag-col"><span class="judge">judge</span></div><i aria-hidden="true"></i>
          <div class="dag-col"><span>report</span></div>
        </div>
        <p class="hint">Only the DevOps reviewer waits for Docker; the other four start as soon as indexing finishes, so a slow build overlaps with model calls.</p>
      </section>

      <section id="scoring">
        <h2>Scoring</h2>
        <p>Each area is scored from 0 to 10. Every assignment sets its own weights (they add up to 100%), and the overall score is</p>
        <p class="formula">final score = 10 × Σ (weight<sub>area</sub> × score<sub>area</sub>)</p>
        <p>The formula runs in code, not in a model, so the same area scores always give the same total and every grade can be audited.
          Letter grades come from fixed bands:</p>
        <div class="table-wrap"><table class="bands"><thead><tr><th>Grade</th><th>A</th><th>A-</th><th>B</th><th>B-</th><th>C</th><th>C-</th><th>D</th><th>F</th></tr></thead>
          <tbody><tr><td>Score from</td><td>85</td><td>78</td><td>70</td><td>62</td><td>55</td><td>48</td><td>40</td><td>0</td></tr></tbody></table></div>
        <p>Default weights are code quality 25%, architecture 25%, testing 20%, security 15% and Docker &amp; DevOps 15%. A student may
          submit as often as they like; their <b>best</b> attempt counts. Instructors can adjust a grade by hand: the adjusted score becomes
          the assignment grade (even over later attempts), the original score and the written reason are stored and shown to the
          student, and the original can be restored.</p>
      </section>

      <section id="latency">
        <h2>Latency</h2>
        <p>The total time is set by the slowest path through the graph, not by the sum of all stages:</p>
        <p class="formula">T<sub>total</sub> ≈ max(T<sub>resolve</sub>, T<sub>clone</sub>) + max(T<sub>index</sub> + max(T<sub>reviewers 1–4</sub>), T<sub>docker</sub> + T<sub>devops</sub>) + T<sub>judge</sub></p>
        <h3>Benchmark</h3>
        <p class="hint">Measured by <code>scripts/latency_benchmark.py</code> on <code>dockersamples/example-voting-app</code> with real clone, index,
          lint and judge logic; model latency simulated as 0.8 s to first token, 20k input tokens/s and 70 output tokens/s.</p>
        <div class="table-wrap"><table><tbody>
          <tr><td>Wall-clock time, 5 reviewers + judge</td><td class="num"><b>27.5 s</b></td></tr>
          <tr><td>The same stages run one after another</td><td class="num">75.5 s</td></tr>
          <tr><td>Speed-up from the graph</td><td class="num"><b>2.74×</b></td></tr>
          <tr><td>Critical path</td><td class="num">clone → index → security → judge → report</td></tr>
          <tr><td>Re-grade of unchanged code (cache hit)</td><td class="num">1.2 s</td></tr>
          <tr><td>Indexing an 8-service repository</td><td class="num">34–38 ms</td></tr>
        </tbody></table></div>
        <h3>What makes it fast</h3>
        <div class="table-wrap"><table><tbody>
          <tr><td><b>Fan-out of the reviewers</b></td><td>The model phase costs the slowest reviewer, not the sum of five.</td></tr>
          <tr><td><b>Docker off the critical path</b></td><td>The build overlaps with four reviewers.</td></tr>
          <tr><td><b>Speculative clone</b></td><td>Cloning starts before the commit is resolved; on a cache hit it is cancelled.</td></tr>
          <tr><td><b>Content-addressed cache</b></td><td>Same commit + Dockerfile + rubric + models returns the stored report.</td></tr>
          <tr><td><b>Small, ranked prompts</b></td><td>Each reviewer gets only its evidence within a character budget; the judge reads about 1k tokens.</td></tr>
          <tr><td><b>Shared prompt prefix</b></td><td>The five reviewer prompts start with an identical block, so the provider's prompt cache can reuse it.</td></tr>
          <tr><td><b>Capped output</b></td><td>At most 7 findings and short summaries, because generating tokens dominates model latency.</td></tr>
          <tr><td><b>Non-blocking I/O</b></td><td>Git, Docker and indexing run in worker threads, so live progress keeps streaming.</td></tr>
        </tbody></table></div>
        <h3>Hard limits</h3>
        <div class="table-wrap"><table><thead><tr><th>Stage</th><th>Typical</th><th>Hard limit</th></tr></thead><tbody>
          <tr><td>Resolve and clone</td><td>0.8–2.5 s</td><td>120 s</td></tr>
          <tr><td>Index</td><td>under 0.1 s</td><td>5,000 files, 40 MB read</td></tr>
          <tr><td>Each reviewer</td><td>10–25 s</td><td>120 s, then its rule-based scorer takes over</td></tr>
          <tr><td>Docker build and smoke run</td><td>20–300 s</td><td>600 s + 8 s run</td></tr>
          <tr><td>Judge</td><td>8–15 s</td><td>150 s, then rule-based calibration</td></tr>
        </tbody></table></div>
        <h3>Live numbers from this server</h3>
        ${liveLatency(metrics)}
      </section>

      <section id="reliability">
        <h2>Reliability</h2>
        <ul class="doc-list">
          <li><b>Timeouts everywhere.</b> Git, Docker, every model call and the judge have deadlines; a reviewer that misses its deadline falls back to its rule-based scorer and the report says so.</li>
          <li><b>Retries with backoff</b> for rate limits and server errors from the model API, and a global limit on concurrent model calls so bursts queue instead of failing.</li>
          <li><b>Heartbeats.</b> Every replica records a heartbeat every 20 s. If one stops (crash, scale-down), another marks its unfinished gradings as failed and cleans up its files, so nothing hangs forever.</li>
          <li><b>Reports survive restarts.</b> Files are written atomically and also copied into PostgreSQL, which matters on hosts whose disk is wiped on restart.</li>
          <li><b>Live progress never hangs.</b> Every progress event is also written, in order, to the database, so any server can
            replay a job's stream; if the server running a job dies, the stream ends with the saved outcome.</li>
        </ul>
      </section>

      <section id="scaling">
        <h2>Scaling</h2>
        <p><b>Today.</b> The web tier scales out by adding replicas: they hold no local state, PostgreSQL holds everything shared, and the
          durable event log means any replica can stream any job, so requests no longer have to stick to one server. Each replica grades
          up to a configured number of submissions at once, so grading capacity grows with the number of replicas.</p>
        <p><b>Next steps</b>, following how large course autograders such as Autolab are built (a job queue plus a pool of grading workers):</p>
        <ol class="doc-steps">
          <li><b>A durable work queue in PostgreSQL.</b> Workers claim jobs with <code>FOR UPDATE SKIP LOCKED</code>, so many workers drain one
            table without blocking each other and jobs survive restarts, with no new infrastructure.</li>
          <li><b>Separate web and worker roles</b> from the same image, scaled independently.</li>
          <li><b>Isolated build workers</b> for student Dockerfiles: one fresh environment per submission.</li>
          <li><b>Object storage for reports</b> once the report table grows large.</li>
          <li><b>Retrying one reviewer</b> instead of the whole job.</li>
          <li><b>Courses</b>, so one deployment serves many classes, and <b>shared rate limits</b> across replicas.</li>
        </ol>
      </section>

      <section id="security">
        <h2>Security</h2>
        <div class="table-wrap"><table><tbody>
          <tr><td><b>Untrusted repositories</b></td><td>Only <code>https://github.com/owner/repo</code> URLs are accepted; refs are validated; every subprocess runs without a shell; git never prompts for credentials.</td></tr>
          <tr><td><b>Secrets in student code</b></td><td>Nine scanner rules find keys and passwords during indexing and the values are redacted before any prompt or report.</td></tr>
          <tr><td><b>Docker sandbox</b></td><td>No network, 512 MB memory, 1 CPU, 256 processes, all capabilities dropped, no privilege escalation; opt-in only.</td></tr>
          <tr><td><b>Passwords and sessions</b></td><td>scrypt password hashes; random 256-bit session tokens stored only as SHA-256; cookies are HttpOnly, SameSite=Lax and Secure over HTTPS.</td></tr>
          <tr><td><b>Who can do what</b></td><td>Every instructor endpoint checks the role on the server. Students can only read their own submissions and reports, and no student endpoint can change a score.</td></tr>
          <tr><td><b>Brute force</b></td><td>Sign-in is throttled per IP address and per account; wrong class join codes are throttled per IP address and in total; unknown emails take as long to reject as wrong passwords. The address comes from the edge proxy (Cloudflare on Render), never from a header the client can write.</td></tr>
          <tr><td><b>Public demo</b></td><td>Sign-up is closed in demo mode, so real students never share a server with a published instructor login. The demo instructor is read-only on the server: it cannot change grades or assignments. Demo logins cannot change their password or name.</td></tr>
          <tr><td><b>Grade integrity</b></td><td>An adjusted grade is pinned as the assignment grade in every view, even over later or higher attempts, until the instructor restores it.</td></tr>
          <tr><td><b>Browser protections</b></td><td>Strict Content-Security-Policy, cross-site request blocking on every state-changing call, HSTS, no framing by other sites; the frontend lab runs student code in a sandboxed iframe.</td></tr>
          <tr><td><b>Exports</b></td><td>The CSV gradebook neutralises spreadsheet formula injection.</td></tr>
        </tbody></table></div>
      </section>

      <section id="data">
        <h2>Data model</h2>
        <div class="table-wrap"><table><thead><tr><th>Table</th><th>What it stores</th></tr></thead><tbody>
          <tr><td class="mono">users</td><td>Students and instructors: name, entry number, email, scrypt hash, role.</td></tr>
          <tr><td class="mono">sessions</td><td>SHA-256 of each session token and its expiry.</td></tr>
          <tr><td class="mono">assignments</td><td>Title, brief, track, rubric weights, checklist, deadline.</td></tr>
          <tr><td class="mono">submissions</td><td>One row per attempt: repository, status, final score, grade, area scores, summary, priorities, learning path, timing.</td></tr>
          <tr><td class="mono">grade_overrides</td><td>Instructor adjustments: original score, new score, reason, who and when.</td></tr>
          <tr><td class="mono">report_artifacts</td><td>The full HTML, Markdown and JSON report of every finished grading.</td></tr>
          <tr><td class="mono">job_events</td><td>Every progress event of recent gradings, so any server can replay a live stream.</td></tr>
          <tr><td class="mono">lab_progress</td><td>Lab tasks each student has completed.</td></tr>
          <tr><td class="mono">instances, meta</td><td>Replica heartbeats and one-time setup markers.</td></tr>
        </tbody></table></div>
        <p class="hint">SQLite by default for local use, PostgreSQL in production; the same SQL runs on both with no ORM.</p>
      </section>

      <section id="features">
        <h2>Features</h2>
        <div class="doc-two">
          <div><h3>For students</h3><ul class="doc-list">
            <li>Dashboard with the next assignment, the last result and the first three things to fix.</li>
            <li>Assignments that show the brief, the checklist and how each area is weighted.</li>
            <li>Live grading progress, then feedback with marks by area, priorities with file names, and topics to learn.</li>
            <li>Score history, skill profile, XP, levels and a class leaderboard.</li>
            <li>Practice runs on any repository, and five labs: frontend, SQL and indexes, load balancers, networks, Dockerfiles.</li>
            <li>Works on phones and installs like an app.</li></ul></div>
          <div><h3>For instructors</h3><ul class="doc-list">
            <li>Class overview that starts with what needs attention: shared repositories, failed gradings, students below 50, students who have not started, low completion near a deadline, the weakest area.</li>
            <li>Gradebook of every student and assignment, with late and adjusted marks, and CSV export.</li>
            <li>Per-assignment analytics: average, median, spread, distribution, area averages, submissions over time, who has not submitted, and possible copying by repository or commit.</li>
            <li>Student profiles with score history, skills, every attempt and lab work.</li>
            <li>Grade adjustment with a reason, re-running one submission, or re-running a whole assignment after changing its rubric.</li>
            <li>Assignments with custom rubric weights, checklist and deadline; platform health with per-stage latency.</li></ul></div>
        </div>
      </section>

      <section id="stack">
        <h2>Tech stack</h2>
        <div class="table-wrap"><table><tbody>
          <tr><td><b>Backend</b></td><td>Python 3.12, FastAPI, asyncio, Pydantic v2, Uvicorn</td></tr>
          <tr><td><b>Agents</b></td><td>Anthropic Claude API with forced tool use (structured JSON), deterministic heuristic scorers</td></tr>
          <tr><td><b>Database</b></td><td>PostgreSQL (psycopg 3, connection pool) or SQLite</td></tr>
          <tr><td><b>Frontend</b></td><td>HTML, CSS and JavaScript modules, SVG charts, Server-Sent Events, PWA service worker</td></tr>
          <tr><td><b>Infrastructure</b></td><td>Docker (multi-stage, non-root image), Docker Compose, Nginx load balancer, Render, Neon</td></tr>
        </tbody></table></div>
        <p class="doc-end">Source code and full design notes: <a href="https://github.com/roshanraj9136/auto-grader" target="_blank" rel="noopener">github.com/roshanraj9136/auto-grader</a>.
          Interactive API reference: <a href="/docs" target="_blank" rel="noopener">/docs</a>.</p>
      </section>
    </article>
  </div>`;
  // In-page links: scroll smoothly without changing the SPA route.
  view.querySelectorAll("[data-anchor]").forEach((a) => a.addEventListener("click", (e) => {
    e.preventDefault();
    view.querySelector(`#${a.dataset.anchor}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  return null;
}

