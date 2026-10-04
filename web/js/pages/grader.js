// Practice grader + live pipeline view (SSE) + result card. `liveJob` is reused by assignment pages.
import { $, DEFAULT_WEIGHTS, DIMENSIONS, api, esc, fmtMs, hbars, scoreRing, toast } from "../core.js";

const COLUMNS = [
  ["Ingest", ["resolve", "clone", "cache_lookup"]],
  ["Analyse", ["index", "docker"]],
  ["Specialists", ["agent:code_quality", "agent:architecture", "agent:security", "agent:testing"]],
  ["Container-aware", ["agent:devops"]],
  ["Verdict", ["judge", "report"]],
];
const LABELS = {
  resolve: "Resolve commit", clone: "Shallow clone", cache_lookup: "Result cache", index: "Index repo",
  docker: "Docker lint/build/run", "agent:code_quality": "Code Quality agent", "agent:architecture": "Architecture agent",
  "agent:security": "Security agent", "agent:testing": "Testing agent", "agent:devops": "DevOps agent",
  judge: "Judge agent", report: "Report",
};

export function repoFields(prefix = "") {
  return `
    <div class="field">
      <label for="${prefix}repo">GitHub repository URL <span aria-hidden="true">*</span></label>
      <input id="${prefix}repo" type="url" required placeholder="https://github.com/owner/repo" autocomplete="url"
             pattern="https://github\\.com/[A-Za-z0-9\\-]+/[A-Za-z0-9._\\-]+/?" />
    </div>
    <div class="grid2">
      <div class="field"><label for="${prefix}ref">Branch / tag / commit <span class="hint">(optional)</span></label>
        <input id="${prefix}ref" placeholder="main" autocomplete="off" /></div>
      <div class="field"><label for="${prefix}dfile">Dockerfile <span class="hint">(optional, else the repo's own)</span></label>
        <input id="${prefix}dfile" type="file" /></div>
    </div>
    <details class="more"><summary>Paste a Dockerfile instead</summary>
      <textarea id="${prefix}dtext" rows="5" spellcheck="false" placeholder="FROM node:20-alpine&#10;WORKDIR /app&#10;…"></textarea>
    </details>`;
}

export function bindDockerfileUpload(prefix = "") {
  $(`#${prefix}dfile`)?.addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    if (f.size > 100_000) { toast("Dockerfile is larger than 100 KB", "error"); return; }
    $(`#${prefix}dtext`).value = await f.text();
    $(`#${prefix}dtext`).closest("details").open = true;
  });
}

export function readRepoFields(prefix = "") {
  const repo = $(`#${prefix}repo`);
  const url = repo.value.trim();
  if (!url || !repo.checkValidity()) {
    repo.focus();
    throw new Error("Enter a public GitHub URL like https://github.com/owner/repo");
  }
  return { repo_url: url, ref: $(`#${prefix}ref`).value.trim() || null, dockerfile_text: $(`#${prefix}dtext`).value.trim() || null };
}

export async function page(view) {
  view.innerHTML = `
  <header class="page-h"><div><p class="kicker">Practice</p><h1>Grade any repository</h1>
    <p class="hint">Free-form grading with your own rubric. Results appear in <a href="/student/submissions">your submissions</a>.</p></div></header>
  <section class="panel">
    <form id="grade-form" class="form" novalidate>
      ${repoFields()}
      <fieldset><legend>Rubric weights <span class="hint">(normalised automatically; 0 disables an agent)</span></legend>
        <div class="weights">${Object.entries(DIMENSIONS).map(([k, label]) => `<div><label for="w-${k}">${label}</label>
          <input id="w-${k}" type="number" min="0" max="1" step="0.05" value="${DEFAULT_WEIGHTS[k]}" /></div>`).join("")}</div>
      </fieldset>
      <div class="field"><label for="notes">Assignment brief / rubric notes <span class="hint">(shared with every agent and the judge)</span></label>
        <textarea id="notes" rows="3" placeholder="e.g. Must expose a REST API backed by PostgreSQL, React frontend, docker-compose with nginx."></textarea></div>
      <label class="check"><input id="force" type="checkbox" /> Force re-grade (bypass the result cache)</label>
      <p id="err" class="error" role="alert"></p>
      <div class="row-btns"><button class="btn" id="go" type="submit">Start grading</button>
        <button class="ghost" type="button" id="sample">Use a sample repo</button></div>
    </form>
  </section>
  <div id="live-host"></div>`;
  bindDockerfileUpload();
  $("#sample").addEventListener("click", () => { $("#repo").value = "https://github.com/dockersamples/example-voting-app"; });
  let stop = null;
  $("#grade-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    try {
      const body = readRepoFields();
      body.weights = Object.fromEntries(Object.keys(DIMENSIONS).map((k) => [k, parseFloat($(`#w-${k}`).value) || 0]));
      body.rubric_notes = $("#notes").value;
      body.force = $("#force").checked;
      $("#go").disabled = true;
      const res = await api("/api/grade", { method: "POST", body });
      history.replaceState({}, "", location.pathname);
      if (stop) stop();
      stop = liveJob($("#live-host"), res.job_id, { deduped: res.deduplicated, onFinish: () => { $("#go").disabled = false; } });
    } catch (err) {
      $("#err").textContent = err.message;
      $("#go").disabled = false;
    }
  });
  return () => stop && stop();
}

export async function job(view, { id }) {
  view.innerHTML = `<header class="page-h"><div><p class="kicker">Grading job</p><h1 class="mono-h">${esc(id.slice(0, 12))}…</h1></div></header><div id="live-host"></div>`;
  let live = true;
  try { await api(`/api/jobs/${encodeURIComponent(id)}`); } catch (e) { if (e.status === 404) live = false; else throw e; }
  if (live) return liveJob($("#live-host"), id, {});
  const sub = await api(`/api/submissions/by-job/${encodeURIComponent(id)}`);
  if (sub.status === "queued" || sub.status === "running") return liveJob($("#live-host"), id, { pollOnly: true });
  $("#live-host").innerHTML = sub.status === "failed"
    ? `<section class="panel"><h2>Grading failed</h2><p class="error">${esc(sub.error || "unknown error")}</p></section>`
    : resultCard(id, sub.final_score, sub.grade, sub);
  return null;
}

export function resultCard(jobId, score, grade, sub = null) {
  const dims = sub?.dims || {};
  const d = sub?.details || {};
  return `<section class="panel result">
    <div class="result-head">${scoreRing(score, grade, 120)}
      <div class="grow"><h2>${score == null ? "Not graded" : `Final score ${esc(score)}/100 · grade ${esc(grade)}`}</h2>
        ${d.summary ? `<p>${esc(d.summary)}</p>` : ""}
        <p class="links"><a href="/api/jobs/${jobId}/report.html" target="_blank" rel="noopener">Open full report ↗</a> ·
          <a href="/api/jobs/${jobId}/report.md" download>Markdown</a> ·
          <a href="/api/jobs/${jobId}/report.json" target="_blank" rel="noopener">JSON</a></p></div>
      ${Object.keys(dims).length ? `<div class="dims-mini">${hbars(Object.entries(dims).map(([k, v]) => [DIMENSIONS[k] || k, v]), { max: 10, fmt: (v) => v.toFixed(1) })}</div>` : ""}
    </div>
    ${d.learning_path?.length ? `<div class="lp"><h3>Your learning path</h3><ol>${d.learning_path.map((x) => `<li>${esc(x)}</li>`).join("")}</ol></div>` : ""}
    <iframe class="report-frame" src="/api/jobs/${esc(jobId)}/report.html" title="Full grading report" loading="lazy"
      sandbox="allow-popups allow-popups-to-escape-sandbox"></iframe>
  </section>`;
}

/** Follow a job over SSE, rendering the live DAG + waterfall; returns a stop() function.
 *  Falls back to polling the persisted submission when the stream is unavailable (the job runs on
 *  another replica, or that replica restarted), so the page never hangs on "Queued…". */
export function liveJob(host, jobId, { deduped = false, onFinish, pollOnly = false } = {}) {
  host.innerHTML = `<section class="panel live" aria-labelledby="live-h">
    <div class="live-top"><h2 id="live-h">Live pipeline</h2><span class="mono">${esc(jobId)}</span></div>
    <p id="live-status" role="status" aria-live="polite">${deduped ? "Identical job already running: attached to it." : "Queued…"}</p>
    <div class="dag" id="dag" aria-label="Pipeline stages"></div>
    <h3>Waterfall</h3><div id="waterfall" class="waterfall" role="img" aria-label="Live stage timeline"></div>
  </section><div id="result-host"></div>`;
  const stages = {};
  let lastT = 0;
  let done = false;
  const statusEl = host.querySelector("#live-status");
  const renderDag = () => {
    host.querySelector("#dag").innerHTML = COLUMNS.map(([title, names]) => `<div class="col"><h4>${title}</h4>${names.map((n) => {
      const s = stages[n] || {};
      const st = s.status || "pending";
      const detail = s.dur != null ? fmtMs(s.dur) : st === "running" ? "running" : s.reason || st;
      return `<div class="stage ${st}"><div class="n">${LABELS[n]}</div><div class="d">${esc(detail)}${s.extra ? " · " + esc(s.extra) : ""}</div></div>`;
    }).join("")}</div>`).join("");
  };
  const renderWaterfall = () => {
    const entries = Object.entries(stages).filter(([, s]) => s.start != null && s.status !== "skipped");
    const total = Math.max(lastT, 1);
    host.querySelector("#waterfall").innerHTML = entries.sort((a, b) => a[1].start - b[1].start).map(([n, s]) => {
      const end = s.end ?? lastT;
      return `<div class="lane"><span>${LABELS[n] || n}</span><div class="track">
        <div class="seg ${s.status}" style="left:${(s.start / total) * 100}%;width:${Math.max(((end - s.start) / total) * 100, 0.5)}%"></div>
        </div><span class="dur">${fmtMs(end - s.start)}</span></div>`;
    }).join("");
  };
  renderDag();
  let source = null;
  let stopped = false;
  const ticker = setInterval(() => { if (!done) { lastT += 100; renderWaterfall(); } }, 100);
  const stop = () => { done = true; stopped = true; clearInterval(ticker); source?.close(); };
  const showResult = async (score, grade, totalMs, cacheHit, sub = null) => {
    // Stages that never ran (cache hit / disabled dimension) should not look stuck in "pending".
    for (const [, names] of COLUMNS) for (const n of names) {
      if (!stages[n]) stages[n] = { status: "skipped", reason: cacheHit ? "reused from cache" : "not run" };
    }
    renderDag();
    statusEl.textContent = `Done${totalMs ? ` in ${fmtMs(totalMs)}` : ""}${cacheHit ? " (result cache hit)" : ""}.`;
    if (!sub) { try { sub = await api(`/api/submissions/by-job/${jobId}`); } catch { /* API-token jobs have no submission */ } }
    host.querySelector("#result-host").innerHTML = resultCard(jobId, score, grade, sub);
    toast(`Graded: ${score}/100 (${grade})`, "ok");
    host.querySelector("#result-host").scrollIntoView({ behavior: "smooth", block: "start" });
    onFinish?.({ final_score: score, grade });
  };
  const showFailure = (error) => {
    statusEl.innerHTML = `<span class="error">Failed: ${esc(error)}</span>`;
    toast("Grading failed", "error");
    onFinish?.({ error });
  };
  const pollDb = async () => {
    done = true;
    clearInterval(ticker);
    statusEl.textContent = "Following this grading from the database (live stream not available on this replica)…";
    while (!stopped) {
      try {
        const sub = await api(`/api/submissions/by-job/${jobId}`);
        if (stopped) return;
        if (sub.status === "done") { stopped = true; return showResult(sub.final_score, sub.grade, sub.total_ms, sub.cache_hit, sub); }
        if (sub.status === "failed") { stopped = true; return showFailure(sub.error || "unknown error"); }
        statusEl.textContent = `Grading ${sub.status} on another server replica… this page updates automatically.`;
      } catch (e) {
        if (e.status === 404) { statusEl.innerHTML = `<span class="error">This job is no longer available.</span>`; onFinish?.({}); return; }
      }
      await new Promise((r) => setTimeout(r, 3000));
    }
  };
  if (pollOnly) { pollDb(); return stop; }
  source = new EventSource(`/api/jobs/${jobId}/events`);
  source.onmessage = async (m) => {
    const ev = JSON.parse(m.data);
    lastT = Math.max(lastT, ev.t_ms);
    switch (ev.type) {
      case "queued": statusEl.textContent = `Queued (position ${ev.position})`; break;
      case "job_started": statusEl.textContent = "Running…"; break;
      case "stage_start": stages[ev.stage] = { status: "running", start: ev.t_ms }; break;
      case "stage_end": {
        const s = stages[ev.stage] || { start: ev.t_ms - (ev.duration_ms || 0) };
        Object.assign(s, { status: ev.status, end: ev.t_ms, dur: ev.duration_ms, reason: ev.reason });
        stages[ev.stage] = s;
        break;
      }
      case "index_ready":
        statusEl.textContent = `Indexed ${ev.code_files} code files / ${ev.source_lines} lines (${(ev.stack || []).slice(0, 4).join(", ") || "stack detected"}): agents running in parallel…`;
        break;
      case "agent_done": {
        const s = stages[`agent:${ev.dimension}`] || {};
        s.extra = `${ev.score}/10 · ${ev.mode}`;
        stages[`agent:${ev.dimension}`] = s;
        break;
      }
      case "judge_done": statusEl.textContent = `Judge: ${ev.final_score}/100 (${ev.grade}). Writing report…`; break;
      case "job_done": {
        done = true;
        clearInterval(ticker);
        source.close();
        await showResult(ev.final_score, ev.grade, ev.total_ms, ev.cache_hit);
        break;
      }
      case "job_failed":
        done = true;
        clearInterval(ticker);
        source.close();
        showFailure(ev.error);
        break;
    }
    renderDag();
    renderWaterfall();
  };
  source.onerror = () => {
    // CONNECTING = transient network error: EventSource reconnects and the server replays history.
    // CLOSED = the server refused the stream (e.g. 404: job lives on another replica): poll the DB instead.
    if (source.readyState === EventSource.CLOSED && !done && !stopped) pollDb();
  };
  return stop;
}
