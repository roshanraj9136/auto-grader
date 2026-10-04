import {
  $, DIMENSIONS, TRACKS, api, emptyState, esc, fmtDate, fmtMs, gradeBadge, hbars, lineChart, progressBar,
  radarChart, relTime, scoreRing, state, statusPill, toast,
} from "../core.js";
import { bindDockerfileUpload, liveJob, readRepoFields, repoFields } from "./grader.js";

function stat(label, value, sub = "", cls = "") {
  return `<div class="stat ${cls}"><span class="stat-l">${esc(label)}</span><b class="stat-v">${value}</b>${sub ? `<span class="stat-s">${sub}</span>` : ""}</div>`;
}

function dueChip(iso) {
  if (!iso) return `<span class="chip">no deadline</span>`;
  const left = new Date(iso).getTime() - Date.now();
  const cls = left < 0 ? "bad" : left < 3 * 86400e3 ? "warn" : "ok";
  return `<span class="chip ${cls}" title="${esc(fmtDate(iso, true))}">${left < 0 ? "closed " : "due "}${esc(relTime(iso))}</span>`;
}

function subRow(s, { showAssignment = true } = {}) {
  return `<tr>
    <td>${fmtDate(s.created_at, true)}</td>
    ${showAssignment ? `<td>${s.assignment_id ? `<a href="/student/assignment/${s.assignment_id}">${esc(s.assignment_title || "Assignment")}</a>` : `<span class="hint">Practice</span>`}</td>` : ""}
    <td class="repo"><a href="${esc(s.repo_url)}" target="_blank" rel="noopener">${esc(s.repo_url.replace("https://github.com/", ""))}</a>${s.ref ? ` <span class="chip">${esc(s.ref)}</span>` : ""}</td>
    <td>${statusPill(s.status)}${s.cache_hit ? ' <span class="chip" title="result cache hit">cache</span>' : ""}</td>
    <td class="num">${gradeBadge(s.final_score, s.grade)}</td>
    <td class="num">${s.total_ms ? fmtMs(s.total_ms) : ""}</td>
    <td>${s.status === "done" ? `<a href="/api/jobs/${s.job_id}/report.html" target="_blank" rel="noopener">report ↗</a>`
      : s.status === "failed" ? `<span class="hint" title="${esc(s.error)}">failed</span>` : `<a href="/jobs/${s.job_id}">live</a>`}</td>
  </tr>`;
}

export function subsTable(rows, opts) {
  if (!rows.length) return emptyState("No submissions yet", "Pick an assignment and submit your GitHub repository.",
    `<a class="btn" href="/student/assignments">Browse assignments</a>`);
  const showA = opts?.showAssignment !== false;
  return `<div class="table-wrap"><table><thead><tr><th>When</th>${showA ? "<th>Assignment</th>" : ""}<th>Repository</th><th>Status</th>
    <th class="num">Score</th><th class="num">Time</th><th></th></tr></thead><tbody>${rows.map((s) => subRow(s, opts)).join("")}</tbody></table></div>`;
}

export async function dashboard(view) {
  const d = await api("/api/student/dashboard");
  const s = d.stats;
  const first = d.user.name.split(" ")[0];
  const pending = d.assignments.filter((a) => !a.mine && (!a.due_at || new Date(a.due_at) > new Date()));
  view.innerHTML = `
  <header class="page-h"><div><p class="kicker">Student dashboard</p><h1>Hi ${esc(first)} 👋</h1>
    <p class="hint">${pending.length ? `You have ${pending.length} open assignment${pending.length > 1 ? "s" : ""} without a submission.` : "You're up to date on assignments."}</p></div>
    <div class="level-card" title="XP = best score per assignment + 20 per server-verified lab task">
      <div class="lvl">Lv <b>${s.level}</b></div>
      <div class="grow"><div class="lvl-t"><span>${s.xp} XP</span><span class="hint">${s.into_level}/${s.level_size} to next</span></div>
      ${progressBar(s.into_level, s.level_size, "Progress to next level")}</div>
      ${s.rank ? `<a class="rank" href="/student/leaderboard">#${s.rank}</a>` : ""}
    </div>
  </header>
  <section class="stats">
    ${stat("Average (best per assignment)", s.avg_score ?? "–", s.avg_score != null ? "out of 100" : "no grades yet", "acc")}
    ${stat("Best score", s.best_score ?? "–", "", "green")}
    ${stat("Assignments done", `${s.assignments_done}<small>/${s.assignments_total}</small>`, progressBar(s.assignments_done, s.assignments_total, "Assignments completed"), "cyan")}
    ${stat("Lab tasks", `${s.labs_done}<small>/${s.labs_total}</small>`, progressBar(s.labs_done, s.labs_total, "Lab tasks completed"), "amber")}
    ${stat("Submissions", s.submissions, `${s.graded} graded`)}
  </section>
  <section class="grid-2-1">
    <div class="panel"><div class="panel-h"><h2>Score history</h2><span class="hint">last ${d.timeline.length} graded</span></div>${lineChart(d.timeline)}</div>
    <div class="panel"><div class="panel-h"><h2>Skill profile</h2><span class="hint">avg of last 10, /10</span></div>
      ${Object.values(d.skills).some((v) => v != null) ? radarChart(d.skills) : emptyState("No skills measured yet", "Your five-dimension profile appears after your first graded submission.")}</div>
  </section>
  <section class="grid-1-1">
    <div class="panel"><div class="panel-h"><h2>Upcoming deadlines</h2><a href="/student/assignments">all assignments →</a></div>
      ${d.upcoming.length ? `<ul class="list">${d.upcoming.map((a) => `<li><a href="/student/assignment/${a.id}"><b>${esc(a.title)}</b></a>
        <span class="chip track">${esc(TRACKS[a.track] || a.track)}</span> ${dueChip(a.due_at)}
        <span class="right">${a.mine ? gradeBadge(a.mine.best, a.mine.best != null ? "best" : "") : '<span class="chip warn">not submitted</span>'}</span></li>`).join("")}</ul>`
        : emptyState("No upcoming deadlines", "")}
    </div>
    <div class="panel"><div class="panel-h"><h2>What to learn next</h2><span class="hint">from your latest report</span></div>
      ${d.learning_path.length ? `<ol class="lp-list">${d.learning_path.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : emptyState("Nothing yet", "After grading, the judge writes a personal learning path here.")}
      ${d.top_priorities.length ? `<h3>Top priorities</h3><ul class="prio">${d.top_priorities.slice(0, 3).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      <a class="btn ghost sm" href="/labs">Practise in the labs →</a>
    </div>
  </section>
  <section class="panel"><div class="panel-h"><h2>Recent submissions</h2><a href="/student/submissions">all →</a></div>${subsTable(d.recent)}</section>`;
  // Refresh quietly (no scroll jump, no flash) while something is still being graded.
  if (d.recent.some((r) => r.status === "queued" || r.status === "running")) {
    const t = setTimeout(() => window.__refresh(), 5000);
    return () => clearTimeout(t);
  }
  return null;
}

export async function assignments(view) {
  const rows = await api("/api/assignments");
  const isInstructor = state.user?.role === "instructor";
  view.innerHTML = `<header class="page-h"><div><p class="kicker">Coursework</p><h1>Assignments</h1>
    <p class="hint">Each assignment has its own rubric: the agents weight their dimensions accordingly.</p></div>
    ${isInstructor ? `<a class="btn" href="/instructor/assignments">Manage assignments</a>` : ""}</header>
    ${rows.length ? `<section class="cards">${rows.map((a) => `<article class="card a-card">
      <div class="card-top"><span class="chip track">${esc(TRACKS[a.track] || a.track)}</span>${dueChip(a.due_at)}</div>
      <h2><a href="/student/assignment/${a.id}">${esc(a.title)}</a></h2>
      <p>${esc(a.description)}</p>
      <div class="weights-mini" aria-label="Rubric weights">${Object.entries(a.weights).map(([k, w]) =>
        `<span title="${esc(DIMENSIONS[k] || k)}"><i style="width:${Math.round(w * 100)}%"></i>${esc((DIMENSIONS[k] || k).split(" ")[0])} ${Math.round(w * 100)}%</span>`).join("")}</div>
      <div class="card-foot">
        ${a.mine ? `<span>${a.mine.attempts} attempt${a.mine.attempts > 1 ? "s" : ""} · best ${gradeBadge(a.mine.best, "")}</span>` : `<span class="hint">${a.class_stats.students} student(s) submitted</span>`}
        <a class="btn sm" href="/student/assignment/${a.id}">${a.mine ? "Resubmit" : "Open"}</a></div>
    </article>`).join("")}</section>` : emptyState("No assignments yet", "Your instructor hasn't published any assignments.")}`;
}

export async function assignment(view, { id }) {
  const a = await api(`/api/assignments/${encodeURIComponent(id)}`);
  const subs = a.submissions || [];
  const best = subs.filter((s) => s.final_score != null).sort((x, y) => y.final_score - x.final_score)[0];
  const closed = a.due_at && new Date(a.due_at) < new Date();
  view.innerHTML = `
  <header class="page-h"><div><p class="kicker"><a href="/student/assignments">Assignments</a> / ${esc(TRACKS[a.track] || a.track)}</p>
    <h1>${esc(a.title)}</h1><p class="hint">${dueChip(a.due_at)} ${a.due_at ? esc(fmtDate(a.due_at, true)) : ""}</p></div>
    ${best ? `<div class="best">${scoreRing(best.final_score, best.grade, 92)}<span class="hint">your best</span></div>` : ""}</header>
  <section class="grid-2-1">
    <div class="panel">
      <h2>Brief</h2><p>${esc(a.description)}</p>
      ${a.rubric_notes ? `<h3>What the agents will check</h3><p class="rubric">${esc(a.rubric_notes)}</p>` : ""}
      <h3>Submit your repository</h3>
      ${closed ? `<p class="chip warn">The deadline has passed: late submissions are still graded and marked by date.</p>` : ""}
      <form id="submit-form" class="form" novalidate>
        ${repoFields("s-")}
        <label class="check"><input id="s-force" type="checkbox" /> Force re-grade (bypass the result cache)</label>
        <p id="err" class="error" role="alert"></p>
        <button class="btn" id="go" type="submit">Submit for grading</button>
      </form>
    </div>
    <div class="panel"><h2>Rubric weights</h2>
      ${hbars(Object.entries(a.weights).map(([k, w]) => [DIMENSIONS[k] || k, w * 100]), { max: 100, fmt: (v) => `${Math.round(v)}%` })}
      ${best?.dims ? `<h3>Your best attempt</h3>${hbars(Object.entries(best.dims).map(([k, v]) => [DIMENSIONS[k] || k, v]), { max: 10, fmt: (v) => v.toFixed(1) })}` : ""}
    </div>
  </section>
  <div id="live-host"></div>
  <section class="panel"><h2>Your attempts</h2>${subsTable(subs, { showAssignment: false })}</section>`;
  bindDockerfileUpload("s-");
  let stop = null;
  $("#submit-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    try {
      const body = { ...readRepoFields("s-"), force: $("#s-force").checked };
      $("#go").disabled = true;
      const res = await api(`/api/assignments/${a.id}/submit`, { method: "POST", body });
      toast("Submitted: grading started", "ok");
      if (stop) stop();
      stop = liveJob($("#live-host"), res.job_id, {
        deduped: res.deduplicated,
        onFinish: () => { $("#go").disabled = false; },
      });
      $("#live-host").scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      $("#err").textContent = err.message;
      $("#go").disabled = false;
    }
  });
  return () => stop && stop();
}

export async function submissions(view) {
  const rows = await api("/api/student/submissions?limit=200");
  view.innerHTML = `<header class="page-h"><div><p class="kicker">History</p><h1>My submissions</h1>
    <p class="hint">${rows.length} submission(s). Reports are stored permanently and can be downloaded as HTML, Markdown or JSON.</p></div>
    <a class="btn" href="/grader">Practice grader</a></header>
    <section class="panel">${subsTable(rows)}</section>`;
}

export async function leaderboard(view) {
  const d = await api("/api/leaderboard");
  const podium = d.rows.slice(0, 3);
  view.innerHTML = `<header class="page-h"><div><p class="kicker">Class</p><h1>Leaderboard</h1>
    <p class="hint">XP = sum of your best score per assignment + 20 XP per server-verified lab task.</p></div>
    ${d.me ? `<div class="stat acc"><span class="stat-l">Your rank</span><b class="stat-v">#${d.me.rank}</b><span class="stat-s">${d.me.xp} XP</span></div>` : ""}</header>
    ${podium.length ? `<section class="podium">${podium.map((r, i) => `<div class="pod p${i + 1}"><span class="medal" aria-hidden="true">${["🥇", "🥈", "🥉"][i]}</span>
      <b>${esc(r.name)}</b><span>${r.xp} XP</span></div>`).join("")}</section>` : ""}
    <section class="panel">${d.rows.length ? `<div class="table-wrap"><table><thead><tr><th>#</th><th>Student</th><th class="num">XP</th>
      <th class="num">Assignments</th><th class="num">Avg best</th><th class="num">Lab tasks</th></tr></thead><tbody>
      ${d.rows.map((r) => `<tr class="${d.me && r.user_id === d.me.user_id ? "me" : ""}"><td>${r.rank}</td><td>${esc(r.name)}${r.entry_no ? ` <span class="hint">${esc(r.entry_no)}</span>` : ""}</td>
        <td class="num"><b>${r.xp}</b></td><td class="num">${r.assignments_done}</td><td class="num">${r.avg_best ?? "–"}</td><td class="num">${r.labs_done}</td></tr>`).join("")}
      </tbody></table></div>` : emptyState("The leaderboard is empty", "Complete an assignment or a lab task to appear here.")}</section>`;
}

export async function profile(view) {
  const u = state.user;
  view.innerHTML = `<header class="page-h"><div><p class="kicker">Account</p><h1>Profile</h1></div></header>
  <section class="grid-1-1">
    <form class="panel form" id="profile-form" novalidate>
      <h2>Details</h2>
      <label for="p-name">Full name</label><input id="p-name" value="${esc(u.name)}" required minlength="2" autocomplete="name" />
      <label for="p-entry">Entry number</label><input id="p-entry" value="${esc(u.entry_no || "")}" autocomplete="off" />
      <label for="p-email">Email</label><input id="p-email" value="${esc(u.email)}" disabled />
      <p class="hint">Role: ${esc(u.role)} · member since ${esc(fmtDate(u.created_at))}</p>
      <button class="btn" type="submit">Save</button>
    </form>
    <form class="panel form" id="pw-form" novalidate>
      <h2>Change password</h2>
      <label for="pw-cur">Current password</label><input id="pw-cur" type="password" autocomplete="current-password" required />
      <label for="pw-new">New password <span class="hint">(min 8)</span></label><input id="pw-new" type="password" autocomplete="new-password" required minlength="8" />
      <p class="hint">Changing your password signs out every other device.</p>
      <p id="pw-err" class="error" role="alert"></p>
      <button class="btn" type="submit">Update password</button>
    </form>
  </section>`;
  $("#profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const res = await api("/api/me", { method: "PUT", body: { name: $("#p-name").value.trim(), entry_no: $("#p-entry").value.trim() || null } });
      state.user = res.user;
      window.dispatchEvent(new Event("auth-changed"));
      toast("Profile saved", "ok");
    } catch (err) { toast(err.message, "error"); }
  });
  $("#pw-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#pw-err").textContent = "";
    try {
      await api("/api/me/password", { method: "POST", body: { current: $("#pw-cur").value, new: $("#pw-new").value } });
      e.target.reset();
      toast("Password updated", "ok");
    } catch (err) { $("#pw-err").textContent = err.message; }
  });
}
