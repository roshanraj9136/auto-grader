// AutoGrader frontend: submit -> live SSE pipeline view -> embedded report.
const DIMENSIONS = {
  code_quality: ["Code quality", 0.25],
  architecture: ["Architecture", 0.25],
  security: ["Security", 0.15],
  testing: ["Testing", 0.2],
  devops: ["DevOps & Docker", 0.15],
};
// Columns mirror the backend DAG (app/pipeline.py).
const COLUMNS = [
  ["Ingest", ["resolve", "clone", "cache_lookup"]],
  ["Analyse", ["index", "docker"]],
  ["Specialists", ["agent:code_quality", "agent:architecture", "agent:security", "agent:testing"]],
  ["Container-aware", ["agent:devops"]],
  ["Verdict", ["judge", "report"]],
];
const LABELS = {
  resolve: "Resolve commit (ls-remote)", clone: "Shallow clone (speculative)", cache_lookup: "Result cache",
  index: "Index repo (1 pass)", docker: "Docker lint/build/run",
  "agent:code_quality": "Code Quality agent", "agent:architecture": "Architecture agent",
  "agent:security": "Security agent", "agent:testing": "Testing agent", "agent:devops": "DevOps agent",
  judge: "Judge agent", report: "Report",
};

const $ = (id) => document.getElementById(id);
const fmt = (ms) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

let health = null;
let stages = {};
let lastT = 0;
let ticker = null;
let source = null;

function renderWeights() {
  $("weights").innerHTML = Object.entries(DIMENSIONS)
    .map(([k, [label, w]]) => `<div><label for="w-${k}">${label}</label>
      <input id="w-${k}" type="number" min="0" max="1" step="0.05" value="${w}" /></div>`)
    .join("");
}

async function loadHealth() {
  try {
    health = await (await fetch("/api/health")).json();
    $("health").innerHTML =
      `<span class="b">${health.llm_mode ? "LLM: " + esc(health.agent_model) : "heuristic mode (no API key)"}</span>` +
      `<span class="b">Docker sandbox: ${health.docker_available ? "on" : "off"}</span>` +
      `<span class="b">v${esc(health.version)}</span>`;
    $("token-row").hidden = !health.auth_required;
  } catch {
    $("health").textContent = "API unreachable";
  }
}

$("dockerfile_file").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  if (f.size > 100_000) { $("form-error").textContent = "Dockerfile is larger than 100 KB."; return; }
  $("dockerfile_text").value = await f.text();
});

$("grade-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("form-error").textContent = "";
  const repo = $("repo_url").value.trim();
  if (!$("repo_url").checkValidity() || !repo) {
    $("form-error").textContent = "Enter a public GitHub URL like https://github.com/owner/repo";
    $("repo_url").focus();
    return;
  }
  const weights = {};
  for (const k of Object.keys(DIMENSIONS)) weights[k] = parseFloat($(`w-${k}`).value) || 0;
  const body = {
    repo_url: repo,
    ref: $("ref").value.trim() || null,
    dockerfile_text: $("dockerfile_text").value.trim() || null,
    weights,
    rubric_notes: $("rubric_notes").value,
    force: $("force").checked,
  };
  const headers = { "Content-Type": "application/json" };
  if ($("token").value) headers.Authorization = `Bearer ${$("token").value}`;
  $("submit").disabled = true;
  try {
    const res = await fetch("/api/grade", { method: "POST", headers, body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    follow(data.job_id, data.deduplicated);
  } catch (err) {
    $("form-error").textContent = `Submission failed: ${err.message}`;
    $("submit").disabled = false;
  }
});

function follow(jobId, deduped) {
  stages = {};
  lastT = 0;
  $("live").hidden = false;
  $("result").hidden = true;
  $("job-id").textContent = jobId;
  $("live-status").textContent = deduped ? "Identical job already running — attached to it." : "Queued…";
  renderDag();
  if (source) source.close();
  source = new EventSource(`/api/jobs/${jobId}/events`);
  clearInterval(ticker);
  ticker = setInterval(() => { lastT += 100; renderWaterfall(); }, 100);
  source.onmessage = (m) => onEvent(jobId, JSON.parse(m.data));
  source.onerror = () => { /* EventSource auto-reconnects; server replays history */ };
}

function onEvent(jobId, ev) {
  lastT = Math.max(lastT, ev.t_ms);
  switch (ev.type) {
    case "queued": $("live-status").textContent = `Queued (position ${ev.position})`; break;
    case "job_started": $("live-status").textContent = "Running…"; break;
    case "stage_start": stages[ev.stage] = { status: "running", start: ev.t_ms }; break;
    case "stage_end": {
      const s = stages[ev.stage] || { start: ev.t_ms - (ev.duration_ms || 0) };
      Object.assign(s, { status: ev.status, end: ev.t_ms, dur: ev.duration_ms, reason: ev.reason });
      stages[ev.stage] = s;
      break;
    }
    case "index_ready":
      $("live-status").textContent = `Indexed ${ev.code_files} code files / ${ev.source_lines} lines — agents running in parallel…`;
      break;
    case "agent_done": {
      const s = stages[`agent:${ev.dimension}`] || {};
      s.extra = `${ev.score}/10 · ${ev.mode}`;
      stages[`agent:${ev.dimension}`] = s;
      break;
    }
    case "judge_done": $("live-status").textContent = `Judge: ${ev.final_score}/100 (${ev.grade}) — writing report…`; break;
    case "job_done":
      finish(jobId, ev);
      break;
    case "job_failed":
      cleanup();
      $("live-status").textContent = `Failed: ${ev.error}`;
      break;
  }
  renderDag();
  renderWaterfall();
}

function cleanup() {
  clearInterval(ticker);
  if (source) source.close();
  $("submit").disabled = false;
  loadMetrics();
}

function finish(jobId, ev) {
  cleanup();
  $("live-status").textContent = `Done in ${fmt(ev.total_ms)}${ev.cache_hit ? " (result cache hit)" : ""}.`;
  $("result").hidden = false;
  const score = $("score");
  score.style.setProperty("--p", `${ev.final_score}%`);
  score.setAttribute("aria-label", `Score ${ev.final_score} of 100, grade ${ev.grade}`);
  score.innerHTML = `<span>${ev.final_score}<small>${esc(ev.grade)}</small></span>`;
  $("result-summary").textContent = `Final score ${ev.final_score}/100, grade ${ev.grade}.`;
  for (const [id, ext] of [["link-html", "html"], ["link-md", "md"], ["link-json", "json"]]) {
    $(id).href = `/api/jobs/${jobId}/report.${ext}`;
  }
  $("report-frame").src = `/api/jobs/${jobId}/report.html`;
  $("result").scrollIntoView({ behavior: "smooth" });
}

function renderDag() {
  $("dag").innerHTML = COLUMNS.map(([title, names]) => `<div class="col"><h4>${title}</h4>${names.map((n) => {
    const s = stages[n] || {};
    const status = s.status || "pending";
    const detail = s.dur != null ? fmt(s.dur) : status === "running" ? "running" : s.reason || status;
    return `<div class="stage ${status}"><div class="n">${LABELS[n]}</div><div class="d">${esc(detail)}${s.extra ? " · " + esc(s.extra) : ""}</div></div>`;
  }).join("")}</div>`).join("");
}

function renderWaterfall() {
  const entries = Object.entries(stages).filter(([, s]) => s.start != null && s.status !== "skipped");
  const total = Math.max(lastT, 1);
  $("waterfall").innerHTML = entries.sort((a, b) => a[1].start - b[1].start).map(([n, s]) => {
    const end = s.end ?? lastT;
    return `<div class="lane"><span>${LABELS[n] || n}</span><div class="track">
      <div class="seg ${s.status}" style="left:${(s.start / total) * 100}%;width:${Math.max(((end - s.start) / total) * 100, 0.5)}%"></div>
      </div><span class="dur">${fmt(end - s.start)}</span></div>`;
  }).join("");
}

async function loadMetrics() {
  try {
    const m = await (await fetch("/api/metrics")).json();
    const rows = Object.entries(m.stages).map(([n, s]) =>
      `<tr><td>${esc(n)}</td><td class="num">${s.count}</td><td class="num">${fmt(s.p50_ms)}</td><td class="num">${fmt(s.p95_ms)}</td><td class="num">${fmt(s.max_ms)}</td></tr>`).join("");
    $("metrics").innerHTML = rows
      ? `<table><thead><tr><th>Stage</th><th class="num">n</th><th class="num">p50</th><th class="num">p95</th><th class="num">max</th></tr></thead><tbody>${rows}</tbody></table>
         <p class="mono">counters: ${esc(JSON.stringify(m.counters))} · jobs: ${esc(JSON.stringify(m.jobs.by_status))}</p>`
      : "<p class='hint'>No jobs yet.</p>";
    const jobs = await (await fetch("/api/jobs")).json();
    $("jobs").innerHTML = jobs.length
      ? `<table><thead><tr><th>Repo</th><th>Status</th><th class="num">Score</th><th class="num">Time</th><th></th></tr></thead><tbody>${jobs.map((j) =>
          `<tr><td>${esc(j.repo_url)}</td><td>${esc(j.status)}${j.cache_hit ? " (cache)" : ""}</td><td class="num">${j.final_score ?? ""} ${esc(j.grade ?? "")}</td>
           <td class="num">${j.total_ms ? fmt(j.total_ms) : ""}</td><td>${j.status === "done" ? `<a href="/api/jobs/${j.job_id}/report.html" target="_blank" rel="noopener">report</a>` : ""}</td></tr>`).join("")}</tbody></table>`
      : "<p class='hint'>No jobs yet.</p>";
  } catch { /* metrics are best-effort */ }
}

$("refresh-metrics").addEventListener("click", loadMetrics);
renderWeights();
loadHealth();
loadMetrics();
