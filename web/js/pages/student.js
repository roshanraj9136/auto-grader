import {
  $, DIM_HELP, DIM_ICON, DIMENSIONS, TRACKS, api, emptyState, esc, fmtDate, gradeBadge, icon, lineChart, pageHeader,
  progressBar, radarChart, relTime, scoreRing, state, statusPill, toast,
} from "../core.js";
import { bindDockerfileUpload, liveJob, readRepoFields, repoFields } from "./grader.js";

const TRACK_ICON = { frontend: "code", backend: "layers", database: "database", networking: "network", devops: "box", security: "shield", fullstack: "sparkles" };

function stat(label, value, sub, ico, cls = "") {
  return `<div class="stat ${cls}"><div class="stat-top"><span class="stat-l">${esc(label)}</span><span class="stat-ico">${icon(ico)}</span></div>
    <b class="stat-v">${value}</b>${sub ? `<span class="stat-s">${sub}</span>` : ""}</div>`;
}

function dueChip(iso) {
  if (!iso) return `<span class="chip">${icon("calendar")} No deadline</span>`;
  const left = new Date(iso).getTime() - Date.now();
  const cls = left < 0 ? "bad" : left < 3 * 86400e3 ? "warn" : "";
  return `<span class="chip ${cls}" title="${esc(fmtDate(iso, true))}">${icon("clock")} ${left < 0 ? "Closed" : "Due"} ${esc(relTime(iso))}</span>`;
}

function repoShort(url) { return String(url || "").replace("https://github.com/", ""); }

function feedbackLink(s) {
  if (s.status === "done") return `<a class="ghost sm" href="/jobs/${esc(s.job_id)}">View feedback</a>`;
  if (s.status === "failed") return `<span class="hint" title="${esc(s.error)}">Didn't finish</span>`;
  return `<a class="ghost sm" href="/jobs/${esc(s.job_id)}">Follow</a>`;
}

function subRow(s, { showAssignment = true } = {}) {
  return `<tr>
    ${showAssignment ? `<td>${s.assignment_id ? `<a href="/student/assignment/${s.assignment_id}"><b>${esc(s.assignment_title || "Assignment")}</b></a>` : `<span class="muted">Practice</span>`}</td>` : ""}
    <td class="repo hide-sm"><a href="${esc(s.repo_url)}" target="_blank" rel="noopener">${icon("git")} ${esc(repoShort(s.repo_url))}</a></td>
    <td class="${showAssignment ? "hide-sm" : ""}">${esc(fmtDate(s.created_at, true))}</td>
    <td class="hide-sm">${statusPill(s.status)}</td>
    <td class="num">${gradeBadge(s.final_score, s.grade)}</td>
    <td class="actions">${feedbackLink(s)}</td>
  </tr>`;
}

export function subsTable(rows, opts) {
  if (!rows.length) return emptyState("No submissions yet", "Pick an assignment and submit your GitHub repository to get your first feedback.",
    `<a class="btn" href="/student/assignments">Browse assignments</a>`, "book");
  const showA = opts?.showAssignment !== false;
  return `<div class="table-wrap"><table><thead><tr>${showA ? "<th>Assignment</th>" : ""}<th class="hide-sm">Repository</th><th class="${showA ? "hide-sm" : ""}">Submitted</th><th class="hide-sm">Status</th>
    <th class="num">Score</th><th></th></tr></thead><tbody>${rows.map((s) => subRow(s, opts)).join("")}</tbody></table></div>`;
}

export async function dashboard(view) {
  const d = await api("/api/student/dashboard");
  const s = d.stats;
  const first = d.user.name.split(" ")[0];
  const open = d.assignments.filter((a) => !a.mine && (!a.due_at || new Date(a.due_at) > new Date()));
  const next = open.sort((a, b) => (a.due_at || "9") < (b.due_at || "9") ? -1 : 1)[0];
  const hour = new Date().getHours();
  const hello = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const grading = d.recent.some((r) => r.status === "queued" || r.status === "running");
  view.innerHTML = `
  <section class="welcome">
    <div style="position:relative;z-index:1"><h1>${hello}, ${esc(first)}!</h1>
      <p>${open.length ? `You have ${open.length} assignment${open.length > 1 ? "s" : ""} waiting for a submission.` : "You're all caught up on assignments. Nice work!"}</p></div>
    <div class="level" title="Earn XP from your best score on each assignment and from lab tasks">
      <div class="lvl-n"><small>LEVEL</small>${s.level}</div>
      <div class="grow"><div class="lvl-t"><span>${s.xp} XP</span><span>${s.level_size - s.into_level} XP to level ${s.level + 1}</span></div>
        ${progressBar(s.into_level, s.level_size, "Progress to next level")}</div>
    </div>
  </section>
  ${grading ? `<div class="banner"><span class="spinner"></span><span>One of your submissions is being reviewed. This page updates when it's done.</span></div>` : ""}
  ${next ? `<section class="panel"><div class="next-up"><span class="ico-lg">${icon(TRACK_ICON[next.track] || "book")}</span>
      <div class="grow"><p class="kicker" style="margin:0">Up next</p><b style="font-size:1.05rem">${esc(next.title)}</b>
      <div class="chips">${dueChip(next.due_at)}<span class="chip track">${esc(TRACKS[next.track] || next.track)}</span></div></div>
      <a class="btn" href="/student/assignment/${next.id}">Start ${icon("arrowRight")}</a></div></section>` : ""}
  <section class="stats">
    ${stat("Average score", s.avg_score ?? "–", s.avg_score != null ? "your best try on each assignment" : "submit to get your first score", "target")}
    ${stat("Assignments", `${s.assignments_done}<small>/${s.assignments_total}</small>`, progressBar(s.assignments_done, s.assignments_total, "Assignments completed"), "book", "sky")}
    ${stat("Lab tasks", `${s.labs_done}<small>/${s.labs_total}</small>`, progressBar(s.labs_done, s.labs_total, "Lab tasks completed"), "flask", "violet")}
    ${stat("Class rank", s.rank ? `#${s.rank}` : "–", s.rank ? `<a href="/student/leaderboard">See leaderboard</a>` : "earn XP to get ranked", "trophy", "amber")}
  </section>
  <section class="grid-2-1">
    <div class="panel"><div class="panel-h"><h2>${icon("chart")} Your progress</h2><span class="hint">${d.timeline.length} graded</span></div>${lineChart(d.timeline)}</div>
    <div class="panel"><div class="panel-h"><h2>${icon("target")} Your skills</h2><span class="hint">out of 10</span></div>
      ${Object.values(d.skills).some((v) => v != null) ? radarChart(d.skills) : emptyState("No skills yet", "Your skill profile appears after your first feedback.", "", "target")}</div>
  </section>
  <section class="grid-1-1">
    <div class="panel"><div class="panel-h"><h2>${icon("calendar")} Deadlines</h2><a href="/student/assignments">All assignments</a></div>
      ${d.upcoming.length ? `<ul class="list">${d.upcoming.map((a) => `<li><span class="list-ico">${icon(TRACK_ICON[a.track] || "book")}</span>
        <div class="li-main"><a href="/student/assignment/${a.id}"><b>${esc(a.title)}</b></a><span>${esc(fmtDate(a.due_at, true))} · ${esc(relTime(a.due_at))}</span></div>
        ${a.mine?.best != null ? gradeBadge(a.mine.best, "") : '<span class="chip warn">To do</span>'}</li>`).join("")}</ul>`
        : emptyState("No upcoming deadlines", "Enjoy the break!", "", "calendar")}
    </div>
    <div class="panel"><div class="panel-h"><h2>${icon("bulb")} What to learn next</h2><a href="/labs">Labs</a></div>
      ${d.learning_path.length ? `<ul class="learn-list">${d.learning_path.slice(0, 4).map((x) => `<li>${icon("book")}<p>${esc(x)}</p></li>`).join("")}</ul>`
        : emptyState("Nothing here yet", "After your first feedback, you'll get a personal list of topics to learn.", `<a class="ghost sm" href="/labs">Explore the labs</a>`, "bulb")}
    </div>
  </section>
  <section class="panel"><div class="panel-h"><h2>${icon("list")} Recent submissions</h2><a href="/student/submissions">See all</a></div>${subsTable(d.recent.slice(0, 5))}</section>`;
  if (grading) {
    const t = setTimeout(() => window.__refresh(), 5000);
    return () => clearTimeout(t);
  }
  return null;
}

export async function assignments(view) {
  const rows = await api("/api/assignments");
  const isInstructor = state.user?.role === "instructor";
  view.innerHTML = `${pageHeader("Coursework", "Assignments", "Each assignment tells you exactly what will be checked. Submit as many times as you like; your best score counts.",
      isInstructor ? `<a class="btn" href="/instructor/assignments">${icon("edit")} Manage</a>` : "")}
    ${rows.length ? `<section class="cards">${rows.map((a) => `<article class="card a-card">
      <div class="card-top"><span class="chip track">${icon(TRACK_ICON[a.track] || "book")} ${esc(TRACKS[a.track] || a.track)}</span>${dueChip(a.due_at)}</div>
      <h2><a href="/student/assignment/${a.id}">${esc(a.title)}</a></h2>
      <p>${esc(a.description)}</p>
      <div class="card-foot">
        ${a.mine ? `<span class="hint">Best ${gradeBadge(a.mine.best, "")} · ${a.mine.attempts} ${a.mine.attempts > 1 ? "tries" : "try"}</span>` : `<span class="hint">Not submitted yet</span>`}
        <a class="btn sm" href="/student/assignment/${a.id}">${a.mine ? "Improve" : "Start"} ${icon("arrowRight")}</a></div>
    </article>`).join("")}</section>` : `<section class="panel">${emptyState("No assignments yet", "Your instructor hasn't published any assignments. Try the labs meanwhile!", `<a class="btn" href="/labs">Open labs</a>`, "book")}</section>`}`;
}

export async function assignment(view, { id }) {
  const a = await api(`/api/assignments/${encodeURIComponent(id)}`);
  const subs = a.submissions || [];
  const best = subs.filter((s) => s.final_score != null).sort((x, y) => y.final_score - x.final_score)[0];
  const closed = a.due_at && new Date(a.due_at) < new Date();
  const checks = (a.rubric_notes || "").split(/;|\n|\.\s/).map((x) => x.trim().replace(/\.$/, "")).filter((x) => x.length > 3);
  const weights = Object.entries(a.weights).sort((x, y) => y[1] - x[1]);
  view.innerHTML = `
  ${pageHeader(`<a href="/student/assignments">Assignments</a> / ${esc(TRACKS[a.track] || a.track)}`, esc(a.title),
    `${dueChip(a.due_at)} ${a.due_at ? `<span class="hint">${esc(fmtDate(a.due_at, true))}</span>` : ""}`,
    best ? `<div class="best-badge">${scoreRing(best.final_score, best.grade, 64)}<div><span>Your best</span><b>${esc(best.final_score)}/100</b></div></div>` : "")}
  <section class="grid-2-1">
    <div>
      <div class="panel"><h2>${icon("book")} The brief</h2><p>${esc(a.description)}</p>
        ${checks.length ? `<h3>What we'll check</h3><ul class="checklist">${checks.map((c) => `<li>${icon("checkCircle")}<span>${esc(c.charAt(0).toUpperCase() + c.slice(1))}</span></li>`).join("")}</ul>` : ""}
      </div>
      <div class="submit-card" id="submit-card">
        <h2>${icon("upload")} ${best ? "Submit an improved version" : "Submit your project"}</h2>
        ${closed ? `<div class="banner warn">${icon("alert")}<span>The deadline has passed. You can still submit; late work is marked with its date.</span></div>` : ""}
        <form id="submit-form" class="form" novalidate>
          ${repoFields("s-")}
          <p id="err" class="error" role="alert"></p>
          <button class="btn lg" id="go" type="submit">${icon("sparkles")} Submit for feedback</button>
        </form>
      </div>
    </div>
    <div class="panel"><h2>${icon("target")} How it's scored</h2>
      ${weights.map(([k, w]) => `<div class="weight-row"><span class="wr-ico">${icon(DIM_ICON[k] || "star")}</span>
        <div class="wr-main"><b>${esc(DIMENSIONS[k] || k)}</b><span>${esc(DIM_HELP[k] || "")}</span></div>
        <span class="wr-pct">${Math.round(w * 100)}%</span></div>`).join("")}
      ${best?.dims ? `<h3>Your best try</h3>${weights.map(([k]) => best.dims[k] == null ? "" : `<div class="hb"><span class="hb-l">${esc(DIMENSIONS[k])}</span>
        <div class="hb-t"><span class="${best.dims[k] >= 7.8 ? "g-a" : best.dims[k] >= 6.2 ? "g-b" : best.dims[k] >= 4.8 ? "g-c" : "g-f"}" style="width:${best.dims[k] * 10}%"></span></div>
        <span class="hb-v">${best.dims[k].toFixed(1)}</span></div>`).join("")}` : ""}
    </div>
  </section>
  <div id="live-host"></div>
  <section class="panel"><div class="panel-h"><h2>${icon("list")} Your attempts</h2></div><div id="attempts">${subsTable(subs, { showAssignment: false })}</div></section>`;
  bindDockerfileUpload("s-");
  let stop = null;
  const reloadAttempts = async () => {
    try {
      const fresh = await api(`/api/assignments/${encodeURIComponent(id)}`);
      $("#attempts").innerHTML = subsTable(fresh.submissions || [], { showAssignment: false });
    } catch { /* keep the old list */ }
  };
  $("#submit-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    try {
      const body = readRepoFields("s-");
      $("#go").disabled = true;
      const res = await api(`/api/assignments/${a.id}/submit`, { method: "POST", body });
      toast("Submitted! Reviewing your project now…", "ok");
      if (stop) stop();
      reloadAttempts();
      stop = liveJob($("#live-host"), res.job_id, { onFinish: () => { $("#go").disabled = false; reloadAttempts(); } });
      $("#live-host").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      $("#err").textContent = err.message;
      $("#go").disabled = false;
    }
  });
  return () => stop && stop();
}

export async function submissions(view) {
  const rows = await api("/api/student/submissions?limit=200");
  const graded = rows.filter((r) => r.status === "done");
  view.innerHTML = `${pageHeader("History", "My submissions", `${rows.length} submission${rows.length === 1 ? "" : "s"}, ${graded.length} with feedback. Open any one to see the full review.`,
      `<a class="ghost" href="/grader">${icon("zap")} Practice</a>`)}
    <section class="panel">${subsTable(rows)}</section>`;
}

export async function leaderboard(view) {
  const d = await api("/api/leaderboard");
  const podium = d.rows.slice(0, 3);
  view.innerHTML = `${pageHeader("Class", "Leaderboard", "Earn XP from your best score on each assignment, plus 20 XP for every lab task checked by the server.",
      d.me ? `<div class="best-badge"><span class="stat-ico" style="width:44px;height:44px">${icon("trophy")}</span><div><span>Your rank</span><b>#${d.me.rank} · ${d.me.xp} XP</b></div></div>` : "")}
    ${podium.length ? `<section class="podium">${podium.map((r, i) => `<div class="pod p${i + 1}"><span class="medal" aria-hidden="true">${["🥇", "🥈", "🥉"][i]}</span>
      <b>${esc(r.name)}</b><span>${r.xp} XP</span></div>`).join("")}</section>` : ""}
    <section class="panel">${d.rows.length ? `<div class="table-wrap"><table><thead><tr><th>Rank</th><th>Student</th><th class="num">XP</th>
      <th class="num">Assignments</th><th class="num">Avg best</th><th class="num">Lab tasks</th></tr></thead><tbody>
      ${d.rows.map((r) => `<tr class="${d.me && r.user_id === d.me.user_id ? "me" : ""}"><td><b>#${r.rank}</b></td><td>${esc(r.name)}${d.me && r.user_id === d.me.user_id ? ' <span class="chip track">You</span>' : ""}</td>
        <td class="num"><b>${r.xp}</b></td><td class="num">${r.assignments_done}</td><td class="num">${r.avg_best ?? "–"}</td><td class="num">${r.labs_done}</td></tr>`).join("")}
      </tbody></table></div>` : emptyState("The leaderboard is empty", "Finish an assignment or a lab task to be the first one here!", "", "trophy")}</section>`;
}

export async function profile(view) {
  const u = state.user;
  view.innerHTML = `${pageHeader("Account", "Profile", `Member since ${esc(fmtDate(u.created_at))}`)}
  <section class="grid-1-1">
    <form class="panel form" id="profile-form" novalidate>
      <h2>${icon("user")} Your details</h2>
      <label for="p-name">Full name</label><input id="p-name" value="${esc(u.name)}" required minlength="2" autocomplete="name" />
      <label for="p-entry">Entry number</label><input id="p-entry" value="${esc(u.entry_no || "")}" autocomplete="off" />
      <label for="p-email">Email</label><input id="p-email" value="${esc(u.email)}" disabled />
      <div class="row-btns" style="margin-top:18px"><button class="btn" type="submit">Save changes</button></div>
    </form>
    <form class="panel form" id="pw-form" novalidate>
      <h2>${icon("shield")} Password</h2>
      <label for="pw-cur">Current password</label><input id="pw-cur" type="password" autocomplete="current-password" required />
      <label for="pw-new">New password</label><input id="pw-new" type="password" autocomplete="new-password" required minlength="8" placeholder="At least 8 characters" />
      <p class="hint" style="margin-top:10px">Changing your password signs you out on your other devices.</p>
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
      toast("Saved", "ok");
    } catch (err) { toast(err.message, "error"); }
  });
  $("#pw-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#pw-err").textContent = "";
    try {
      await api("/api/me/password", { method: "POST", body: { current: $("#pw-cur").value, new: $("#pw-new").value } });
      e.target.reset();
      toast("Password updated", "ok");
    } catch (err) { $("#pw-err").textContent = err.status === 403 ? "Your current password isn't right." : err.message; }
  });
}
