// Practice grading, the friendly live progress view (SSE) and the feedback page.
import {
  $, DEFAULT_WEIGHTS, DIM_HELP, DIM_ICON, DIMENSIONS, api, emptyState, esc, gradeClass, icon, learnLine, pageHeader, state, toast,
} from "../core.js";

// Four student-facing steps; each groups some backend pipeline stages.
const STEPS = [
  ["Getting your code", "Cloning it from GitHub", ["resolve", "clone", "cache_lookup"]],
  ["Reading your project", "Languages, tests and Dockerfiles", ["index", "docker"]],
  ["Reviewing", "Five reviewers, in parallel", ["agent:code_quality", "agent:architecture", "agent:security", "agent:testing", "agent:devops"]],
  ["Writing your feedback", "The score and your next steps", ["judge", "report"]],
];
const REVIEWERS = ["code_quality", "architecture", "security", "testing", "devops"];
const TOTAL_UNITS = 2 + 2 + REVIEWERS.length + 2;

export function repoFields(prefix = "") {
  return `
    <div class="field">
      <label for="${prefix}repo">GitHub repository link</label>
      <div class="input-icon">${icon("git")}
        <input id="${prefix}repo" type="url" required placeholder="https://github.com/your-name/your-project" autocomplete="url"
               pattern="https://github\\.com/[A-Za-z0-9\\-]+/[A-Za-z0-9._\\-]+/?" /></div>
      <p class="hint" style="margin:6px 0 0">The repository must be public.</p>
    </div>
    <details class="more"><summary>${icon("chevronDown")} More options <span class="muted">(branch, Dockerfile)</span></summary>
      <div class="grid2">
        <div class="field"><label for="${prefix}ref">Branch, tag or commit</label><input id="${prefix}ref" placeholder="main" autocomplete="off" /></div>
        <div class="field"><label for="${prefix}dfile">Upload a Dockerfile</label><input id="${prefix}dfile" type="file" /></div>
      </div>
      <div class="field"><label for="${prefix}dtext">…or paste a Dockerfile</label>
        <textarea id="${prefix}dtext" rows="5" spellcheck="false" placeholder="FROM node:20-alpine&#10;WORKDIR /app&#10;…"></textarea></div>
      <label class="check"><input id="${prefix}force" type="checkbox" /> Grade again from scratch (ignore any earlier result for this exact code)</label>
    </details>`;
}

export function bindDockerfileUpload(prefix = "") {
  $(`#${prefix}dfile`)?.addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    if (f.size > 100_000) { toast("That Dockerfile is larger than 100 KB", "error"); return; }
    $(`#${prefix}dtext`).value = await f.text();
  });
}

export function readRepoFields(prefix = "") {
  const repo = $(`#${prefix}repo`);
  const url = repo.value.trim();
  if (!url || !repo.checkValidity()) {
    repo.focus();
    throw new Error("Paste a public GitHub link, like https://github.com/your-name/your-project");
  }
  return { repo_url: url, ref: $(`#${prefix}ref`).value.trim() || null, dockerfile_text: $(`#${prefix}dtext`).value.trim() || null,
    force: !!$(`#${prefix}force`)?.checked };
}

export async function page(view) {
  const teach = state.user?.role === "instructor";
  view.innerHTML = `
  ${teach ? pageHeader("", "Practice grading", "Run any public repository through the grader with your own rubric, for example to try a new assignment before you publish it.")
    : pageHeader("", "Practice", "Check any repository without submitting it for an assignment. Good for a test run before the real thing.")}
  <section class="panel">
    <form id="grade-form" class="form" novalidate>
      ${repoFields()}
      <details class="more"><summary>${icon("chevronDown")} Customise what matters <span class="muted">(optional)</span></summary>
        <p class="hint">Give each area a weight. Set one to 0 to skip it.</p>
        <div class="weights">${Object.entries(DIMENSIONS).map(([k, label]) => `<div><label for="w-${k}">${label}</label>
          <input id="w-${k}" type="number" min="0" max="1" step="0.05" value="${DEFAULT_WEIGHTS[k]}" /></div>`).join("")}</div>
        <div class="field"><label for="notes">What should the reviewers look for?</label>
          <textarea id="notes" rows="3" placeholder="e.g. A REST API with PostgreSQL and a React frontend, deployed with docker-compose."></textarea></div>
      </details>
      <p id="err" class="error" role="alert"></p>
      <div class="row-btns"><button class="btn lg" id="go" type="submit">Get feedback</button>
        <button class="ghost" type="button" id="sample">Try a sample project</button></div>
    </form>
  </section>
  <div id="live-host"></div>`;
  bindDockerfileUpload();
  $("#sample").addEventListener("click", () => { $("#repo").value = "https://github.com/dockersamples/example-voting-app"; $("#repo").focus(); });
  let stop = null;
  $("#grade-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    try {
      const body = readRepoFields();
      body.weights = Object.fromEntries(Object.keys(DIMENSIONS).map((k) => [k, parseFloat($(`#w-${k}`).value) || 0]));
      body.rubric_notes = $("#notes").value;
      $("#go").disabled = true;
      const res = await api("/api/grade", { method: "POST", body });
      if (stop) stop();
      stop = liveJob($("#live-host"), res.job_id, { onFinish: () => { $("#go").disabled = false; } });
      $("#live-host").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      $("#err").textContent = err.message;
      $("#go").disabled = false;
    }
  });
  return () => stop && stop();
}

export async function job(view, { id }) {
  const back = state.user?.role === "instructor" ? `<a href="/instructor/dashboard">Overview</a>` : `<a href="/student/submissions">My submissions</a>`;
  view.innerHTML = `${pageHeader(back, "Feedback")}<div id="live-host"></div>`;
  let live = true;
  try { await api(`/api/jobs/${encodeURIComponent(id)}`); } catch (e) { if (e.status === 404) live = false; else throw e; }
  if (live) return liveJob($("#live-host"), id, {});
  const sub = await api(`/api/submissions/by-job/${encodeURIComponent(id)}`);
  // Running on another server, or this one restarted: the stream is replayed from the database.
  if (sub.status === "queued" || sub.status === "running") return liveJob($("#live-host"), id, {});
  if (sub.status === "failed") {
    $("#live-host").innerHTML = failedCard(sub.error);
    return null;
  }
  await renderFeedback($("#live-host"), id, sub);
  return null;
}

function failedCard(error) {
  return `<section class="panel gp"><div class="gp-top"><div class="done-ico fail-ico">${icon("alert")}</div>
    <div><h2>We couldn't grade this one</h2><p>${esc(friendlyError(error))}</p></div></div></section>`;
}

function friendlyError(err) {
  const e = String(err || "");
  if (/not found|repository|clone|128|Could not read/i.test(e)) return "We couldn't download that repository. Check the link is right and the repo is public.";
  if (/stopped|restart|lost/i.test(e)) return "The server restarted while grading. Please submit again.";
  if (/timeout/i.test(e)) return "Grading took too long. Try again in a moment.";
  return e || "Something went wrong. Please try again.";
}

// ------------------------------------------------------------------------------------ live progress
/** Follow a job: friendly step-by-step progress over SSE, then the feedback page.
 *  Falls back to polling the saved submission when the live stream isn't available. Returns stop(). */
export function liveJob(host, jobId, { onFinish, pollOnly = false } = {}) {
  host.innerHTML = `<section class="panel gp" aria-live="polite">
      <div class="gp-top"><span class="spinner"></span><div><h2 id="gp-title">Reviewing your project…</h2>
        <p id="gp-sub">This usually takes under a minute. You can leave this page, results are saved.</p></div></div>
      <div class="bar"><span id="gp-bar" style="width:4%"></span></div>
      <ol class="gp-steps" id="gp-steps"></ol>
      <div class="reviewers" id="gp-reviewers"></div>
    </section><div id="result-host"></div>`;
  const stages = {};
  let finished = false;
  let source = null;
  const stepState = (names) => {
    const sts = names.map((n) => stages[n]);
    if (sts.length && sts.every((s) => s && ["done", "skipped", "failed"].includes(s))) return "done";
    if (sts.some((s) => s)) return "active";
    return "";
  };
  const paint = () => {
    const states = STEPS.map(([, , names]) => stepState(names));
    // A step is only "active" if every earlier step is done (stages overlap in the backend).
    let firstOpen = states.findIndex((s) => s !== "done");
    host.querySelector("#gp-steps").innerHTML = STEPS.map(([t, d], i) => {
      const st = states[i] === "done" ? "done" : i === firstOpen ? "active" : "";
      return `<li class="gp-step ${st}"><span class="n">${st === "done" ? icon("check") : i + 1}</span><div><b>${esc(t)}</b><span>${esc(d)}</span></div></li>`;
    }).join("");
    host.querySelector("#gp-reviewers").innerHTML = REVIEWERS.map((k) => {
      const s = stages[`agent:${k}`];
      const cls = s === "running" ? "running" : s ? "done" : "";
      return `<span class="reviewer ${cls}">${icon(s && s !== "running" ? "checkCircle" : DIM_ICON[k])}${esc(DIMENSIONS[k])}</span>`;
    }).join("");
    const doneUnits = Object.values(stages).filter((s) => s !== "running").length;
    host.querySelector("#gp-bar").style.width = `${Math.min(96, 4 + (doneUnits / TOTAL_UNITS) * 92)}%`;
    if (firstOpen === -1) firstOpen = STEPS.length - 1;
    if (!finished) host.querySelector("#gp-title").textContent = `${STEPS[firstOpen][0]}…`;
  };
  paint();
  const stop = () => { finished = true; source?.close(); };
  const showDone = async (sub) => {
    finished = true;
    host.querySelector(".gp").remove();
    await renderFeedback(host.querySelector("#result-host"), jobId, sub);
    onFinish?.({});
  };
  const showFailure = (error) => {
    finished = true;
    host.querySelector(".gp").outerHTML = failedCard(error);
    toast("Grading didn't finish", "error");
    onFinish?.({ error });
  };
  const pollDb = async () => {
    host.querySelector("#gp-sub").textContent = "Still working on it. This page updates by itself.";
    while (!finished) {
      try {
        const sub = await api(`/api/submissions/by-job/${jobId}`);
        if (finished) return;
        if (sub.status === "done") return showDone(sub);
        if (sub.status === "failed") return showFailure(sub.error);
      } catch (e) {
        if (e.status === 404) { showFailure("This grading is no longer available. Please submit again."); return; }
      }
      await new Promise((r) => setTimeout(r, 3000));
    }
  };
  if (pollOnly) { pollDb(); return stop; }
  source = new EventSource(`/api/jobs/${jobId}/events`);
  source.onmessage = async (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === "stage_start") stages[ev.stage] = "running";
    else if (ev.type === "stage_end") stages[ev.stage] = ev.status;
    else if (ev.type === "job_done") {
      source.close();
      for (const [, , names] of STEPS) for (const n of names) if (!stages[n] || stages[n] === "running") stages[n] = "done";
      paint();
      host.querySelector("#gp-bar").style.width = "100%";
      let sub = null;
      try { sub = await api(`/api/submissions/by-job/${jobId}`); } catch { /* token-only jobs have no submission */ }
      await showDone(sub || { final_score: ev.final_score, grade: ev.grade });
      toast(`Your feedback is ready: ${ev.final_score}/100`, "ok");
      return;
    } else if (ev.type === "job_failed") {
      source.close();
      showFailure(ev.error);
      return;
    }
    paint();
  };
  source.onerror = () => {
    // CLOSED = the server refused the stream (e.g. the job lives on another server): follow the saved result instead.
    if (source.readyState === EventSource.CLOSED && !finished) pollDb();
  };
  return stop;
}

// ------------------------------------------------------------------------------------ feedback page
const VERDICT = [[85, "Excellent work"], [70, "Strong submission"], [55, "Good progress"], [40, "Getting there"], [0, "Needs more work"]];
const verdictFor = (s) => VERDICT.find(([c]) => s >= c)[1];
const SEV_RANK = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

function parsePriority(p) {
  const m = String(p).match(/^\[(\w+)\]\s*(.*?)(?:\s+[—-]\s+(.*))?$/);
  return m ? { sev: m[1].toLowerCase(), title: m[2], fix: m[3] || "" } : { sev: "", title: String(p), fix: "" };
}

// "Container runs as root [vote/Dockerfile]" -> base title + where. Repeats of the same issue are merged.
const splitWhere = (t) => { const m = String(t).match(/^(.*?)\s*\[([^\]]+)\]\s*$/); return m ? [m[1], m[2]] : [String(t), null]; };

/** Unique, readable titles of a report's top priorities (used on the student dashboard). */
export function priorityTitles(list, n = 3) {
  return groupPriorities((list || []).map(parsePriority)).slice(0, n).map((p) => p.title);
}

// The one orchestrated moment: the score counts up when feedback appears.
function countUp(el, to) {
  if (!el || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const t0 = performance.now(), dur = 700, target = Math.round(to);
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur);
    el.textContent = String(Math.round(target * (1 - Math.pow(1 - k, 3))));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function groupPriorities(list) {
  const out = new Map();
  for (const p of list) {
    const [base, where] = splitWhere(p.title);
    const g = out.get(base) || { ...p, title: base, where: [] };
    if (where) g.where.push(where);
    out.set(base, g);
  }
  return [...out.values()];
}

function groupFindings(findings) {
  const out = new Map();
  for (const f of findings) {
    const [base, where] = splitWhere(f.title);
    const key = `${f.severity}|${base}`;
    const g = out.get(key) || { ...f, title: base, files: [] };
    const file = where || f.file;
    if (file && !g.files.includes(file)) g.files.push(file);
    out.set(key, g);
  }
  return [...out.values()];
}

const filesLine = (files) => !files?.length ? "" : files.length === 1
  ? `<p>${icon("file")} <code>${esc(files[0])}</code></p>`
  : `<p>${icon("file")} In ${files.length} places: ${files.map((x) => `<code>${esc(x)}</code>`).join(" ")}</p>`;

/** Render the full feedback for a graded job from its report JSON. */
export async function renderFeedback(host, jobId, sub = null) {
  host.innerHTML = `<div class="loading"><span class="spinner"></span> Loading your feedback…</div>`;
  let r;
  try {
    r = await api(`/api/jobs/${encodeURIComponent(jobId)}/report.json`);
  } catch {
    host.innerHTML = sub?.final_score != null
      ? `<section class="panel verdict"><div class="score-mark ${gradeClass(sub.final_score)}"><div class="score-line"><b>${esc(Math.round(sub.final_score))}</b>
          <span class="of">/100</span></div><span class="letter">Grade<strong>${esc(sub.grade || "")}</strong></span></div>
          <div class="grow"><p class="verdict-word">${esc(verdictFor(sub.final_score))}</p>
          <p>The detailed feedback can't be loaded right now. Reload the page in a moment to try again.</p></div></section>`
      : emptyState("Feedback not available", "Try again in a moment.", "", "alert");
    return;
  }
  const v = r.verdict;
  const adj = sub?.override && sub.final_score != null ? sub.override : null; // instructor-adjusted grade wins
  const score = adj ? sub.final_score : v.final_score;
  const gradeLetter = adj ? sub.grade : v.grade;
  const dims = v.dimensions;
  const agents = Object.fromEntries((r.agents || []).map((a) => [a.dimension, a]));
  const priorities = groupPriorities((v.top_priorities || []).map(parsePriority)).slice(0, 5);
  const learn = v.learning_path || [];
  const s = r.repo_stats || {};
  const langs = Object.entries(s.languages || {}).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([k]) => k);
  const repoName = r.repo_url.replace("https://github.com/", "");
  const strongest = [...dims].sort((a, b) => b.final_score - a.final_score)[0];

  const marks = [...dims].sort((a, b) => (b.weight || 0) - (a.weight || 0)).map((d) => {
    const cls = gradeClass(d.final_score * 10);
    return `<tr class="${cls}"><td><div class="m-area">${icon(DIM_ICON[d.dimension] || "star")}<div><b>${esc(DIMENSIONS[d.dimension] || d.dimension)}</b>
        <span>${esc(DIM_HELP[d.dimension] || "")}</span></div></div></td>
      <td class="m-w">${d.weight ? `counts ${Math.round(d.weight * 100)}%` : "not counted"}</td>
      <td class="m-bar"><div class="bar"><span style="width:${d.final_score * 10}%"></span></div></td>
      <td class="num m-score">${esc(d.final_score.toFixed(1))}<small> /10</small></td></tr>`;
  }).join("");

  const detail = dims.map((d) => {
    const a = agents[d.dimension];
    if (!a) return "";
    const findings = groupFindings([...(a.findings || [])].sort((x, y) => (SEV_RANK[x.severity] ?? 9) - (SEV_RANK[y.severity] ?? 9)));
    const cls = gradeClass(d.final_score * 10);
    const showSummary = a.mode === "llm" && a.summary;
    return `<details class="fb ${cls}"${d === [...dims].sort((x, y) => x.final_score - y.final_score)[0] ? " open" : ""}>
      <summary><span class="fb-ico">${icon(DIM_ICON[d.dimension] || "star")}</span>
        <span>${esc(DIMENSIONS[d.dimension] || d.dimension)}</span><span class="grade ${cls}">${esc(d.final_score.toFixed(1))}</span>
        <span class="muted" style="font-weight:500;font-size:.9em">${findings.length ? `${findings.length} thing${findings.length > 1 ? "s" : ""} to improve` : "Nothing to fix"}</span>
        <span class="chev">${icon("chevronDown")}</span></summary>
      <div class="fb-body">
        ${showSummary ? `<p>${esc(a.summary)}</p>` : ""}
        ${a.strengths?.length ? `<h4>What you did well</h4><ul>${a.strengths.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
        ${findings.length ? `<h4>What to improve</h4>${findings.map((f) => `<div class="finding">
          <b><span class="sev-tag sev-${esc(f.severity)}">${esc(f.severity)}</span>${esc(f.title)}</b>
          ${f.detail ? `<p>${esc(f.detail)}</p>` : ""}${filesLine(f.files)}
          ${f.recommendation ? `<div class="fix">${icon("bulb")}<span>${esc(f.recommendation)}</span></div>` : ""}</div>`).join("")}` : ""}
      </div></details>`;
  }).join("");

  const mine = state.user?.role !== "instructor";
  host.innerHTML = `
  <section class="panel verdict">
    <div class="score-mark ${gradeClass(score)}">
      <div class="score-line"><b id="score-n">${esc(Math.round(score))}</b><span class="of">/100</span></div>
      <span class="letter">Grade<strong>${esc(gradeLetter)}</strong></span>
    </div>
    <div class="grow">
      <p class="verdict-word">${esc(verdictFor(score))}</p>
      ${adj ? `<div class="banner adj-note">${icon("edit")}<span><b>Adjusted by ${esc(adj.by_name || "your instructor")}</b> from ${esc(adj.original_score)}
        to ${esc(score)}: ${esc(adj.reason)}</span></div>` : ""}
      <h2><a href="${esc(r.repo_url)}" target="_blank" rel="noopener">${esc(repoName)}</a></h2>
      <p>${esc(v.summary || `The strongest area is ${DIMENSIONS[strongest?.dimension] || ""}.`)}</p>
      <div class="row-btns">
        ${mine && sub?.assignment_id ? `<a class="btn sm" href="/student/assignment/${esc(sub.assignment_id)}">Improve and resubmit</a>` : ""}
        <a class="ghost sm" href="/api/jobs/${esc(jobId)}/report.html" target="_blank" rel="noopener">${icon("file")} Printable report</a>
        <a class="ghost sm" href="/api/jobs/${esc(jobId)}/report.md" download>${icon("download")} Download as Markdown</a>
      </div>
    </div>
  </section>
  <section class="panel"><div class="panel-h"><h2>Marks by area</h2><span class="hint">out of 10, weighted by the rubric</span></div>
    <div class="table-wrap"><table class="marks"><tbody>${marks}</tbody></table></div></section>
  <section class="grid-1-1">
    <div class="panel"><div class="panel-h"><h2>Fix these first</h2><span class="hint">most important first</span></div>
      ${priorities.length ? `<ol class="prio-list">${priorities.map((p) => `<li><div>
        <b>${p.sev ? `<span class="sev-tag sev-${esc(p.sev)}">${esc(p.sev)}</span>` : ""}${esc(p.title)}</b>${p.fix ? `<p>${esc(p.fix)}</p>` : ""}
        ${p.where?.length ? `<p class="muted">${p.where.length > 1 ? `In ${p.where.length} places: ` : "In "}${p.where.map((x) => `<code>${esc(x)}</code>`).join(" ")}</p>` : ""}</div></li>`).join("")}</ol>`
        : emptyState("Nothing urgent", "No serious issues were found in this submission.", "", "checkCircle")}</div>
    <div class="panel"><div class="panel-h"><h2>What to learn next</h2><a href="/labs">Open the labs</a></div>
      ${learn.length ? `<ul class="learn-list">${learn.map((x) => `<li>${icon("book")}<p>${learnLine(x)}</p></li>`).join("")}</ul>`
        : emptyState("Nothing to add", "The reviewers had no extra topics to suggest.", "", "book")}</div>
  </section>
  <section class="panel"><div class="panel-h"><h2>Detailed feedback</h2><span class="hint">Open an area to see each finding and its fix</span></div>${detail}</section>
  <section class="panel flat"><div class="snapshot">
    <span>${icon("code")} <b>${esc(s.code_files ?? 0)}</b> code files</span>
    <span>${icon("layers")} <b>${esc((s.source_lines ?? 0).toLocaleString())}</b> lines</span>
    <span>${icon("testCheck")} <b>${esc(s.test_files ?? 0)}</b> test files</span>
    ${langs.length ? `<span>${icon("globe")} ${esc(langs.join(", "))}</span>` : ""}
    <span>${icon("box")} ${r.docker?.dockerfile_source && r.docker.dockerfile_source !== "none" ? "Dockerfile checked" : "No Dockerfile found"}</span>
    <span class="muted">Commit ${esc((r.commit_sha || "").slice(0, 7))}</span></div></section>`;
  countUp(host.querySelector("#score-n"), score);
}
