import {
  $, DIM_HELP, DIM_ICON, DIMENSIONS, TRACKS, api, daysLeft, emptyState, esc, fmtDate, gradeBadge, gradeClass, icon, learnLine, lineChart,
  pageHeader, progressBar, radarChart, relTime, scoreRing, state, statusPill, toast,
} from "../core.js";
import { bindDockerfileUpload, liveJob, priorityTitles, readRepoFields, repoFields } from "./grader.js";

const TRACK_ICON = { frontend: "code", backend: "layers", database: "database", networking: "network", devops: "box", security: "shield", fullstack: "sparkles" };

function dueChip(iso) {
  if (!iso) return `<span class="chip">${icon("calendar")} No deadline</span>`;
  const left = daysLeft(iso);
  const cls = left < 0 ? "bad" : left < 3 ? "warn" : "";
  return `<span class="chip ${cls}" title="${esc(fmtDate(iso, true))}">${icon("clock")} ${left < 0 ? "Closed" : "Due"} ${esc(relTime(iso))}</span>`;
}

/** "Due Wed 15 Oct, in 7 days" with urgency colour, for the Up next card. */
function dueMeta(iso) {
  if (!iso) return `<span>${icon("calendar")} No deadline</span>`;
  const left = daysLeft(iso);
  const cls = left < 0 ? "late" : left < 3 ? "soon" : "";
  return `<span class="${cls}">${icon("clock")} ${left < 0 ? "Closed" : "Due"} ${esc(fmtDate(iso, true))}, ${esc(relTime(iso))}</span>`;
}

const byDue = (a, b) => (a.due_at || "9") < (b.due_at || "9") ? -1 : 1;

function repoShort(url) { return String(url || "").replace("https://github.com/", ""); }

function feedbackLink(s) {
  if (s.status === "done") return `<a class="ghost sm" href="/jobs/${esc(s.job_id)}">Feedback</a>`;
  if (s.status === "failed") return `<span class="hint" title="${esc(s.error)}">Didn't finish</span>`;
  return `<a class="ghost sm" href="/jobs/${esc(s.job_id)}">Follow</a>`;
}

function subRow(s, { showAssignment = true } = {}) {
  return `<tr>
    ${showAssignment ? `<td>${s.assignment_id ? `<a href="/student/assignment/${s.assignment_id}"><b>${esc(s.assignment_title || "Assignment")}</b></a>` : `<span class="muted">Practice</span>`}</td>` : ""}
    <td class="repo hide-sm"><a href="${esc(s.repo_url)}" target="_blank" rel="noopener">${esc(repoShort(s.repo_url))}</a></td>
    <td class="${showAssignment ? "hide-sm" : ""}">${esc(fmtDate(s.created_at, true))}</td>
    <td class="hide-sm">${statusPill(s.status)}</td>
    <td class="num">${gradeBadge(s.final_score, s.grade)}${s.override ? ` <span class="adj" title="${esc(s.override.reason)}">adjusted</span>` : ""}</td>
    <td class="actions">${feedbackLink(s)}</td>
  </tr>`;
}

export function subsTable(rows, opts) {
  if (!rows.length) return emptyState("No submissions yet", "Pick an assignment and submit your GitHub repository to get your first feedback.",
    `<a class="btn" href="/student/assignments">See assignments</a>`, "book");
  const showA = opts?.showAssignment !== false;
  return `<div class="table-wrap"><table><thead><tr>${showA ? "<th>Assignment</th>" : ""}<th class="hide-sm">Repository</th><th class="${showA ? "hide-sm" : ""}">Submitted</th><th class="hide-sm">Status</th>
    <th class="num">Score</th><th></th></tr></thead><tbody>${rows.map((s) => subRow(s, opts)).join("")}</tbody></table></div>`;
}

// ------------------------------------------------------------------------------------ dashboard
function nextCard(next, improve) {
  if (next) {
    return `<article class="next"><h2>Up next</h2>
      <h3 class="focus-title"><a href="/student/assignment/${next.id}"><span class="hl">${esc(next.title)}</span></a></h3>
      <div class="focus-meta">${dueMeta(next.due_at)}<span>${icon(TRACK_ICON[next.track] || "book")} ${esc(TRACKS[next.track] || next.track)}</span></div>
      ${next.description ? `<p class="focus-desc">${esc(next.description)}</p>` : ""}
      <div class="row-btns"><a class="btn lg" href="/student/assignment/${next.id}">Start this assignment</a></div></article>`;
  }
  if (improve) {
    return `<article class="next"><h2>Raise a score</h2>
      <h3 class="focus-title"><a href="/student/assignment/${improve.id}"><span class="hl">${esc(improve.title)}</span></a></h3>
      <div class="focus-meta">${dueMeta(improve.due_at)}<span>${icon("target")} Your best so far is ${esc(Math.round(improve.mine.best ?? 0))}</span></div>
      <p class="focus-desc">Every assignment has a submission. This one has the most room to grow, and your best score is the one that counts.</p>
      <div class="row-btns"><a class="btn lg" href="/student/assignment/${improve.id}">Improve and resubmit</a></div></article>`;
  }
  return `<article class="next"><h2>Up next</h2>
    <h3 class="focus-title">You're all caught up</h3>
    <p class="focus-desc">No assignment is waiting for you. The labs are a good way to keep practising until the next one is published.</p>
    <div class="row-btns"><a class="btn lg" href="/labs">Open the labs</a></div></article>`;
}

function lastCard(latest, priorities) {
  if (!latest) {
    return `<article><h2>Your last result</h2>
      <p class="last-for">No feedback yet. Submit a repository for any assignment and your score, with the first things to fix, shows up here.</p>
      <div class="row-btns"><a class="ghost" href="/grader">Try a practice run</a></div></article>`;
  }
  const fixes = priorityTitles(priorities, 3);
  return `<article><h2>Your last result</h2>
    <div class="last-score ${gradeClass(latest.final_score)}"><b>${esc(Math.round(latest.final_score))}</b><small>/100</small><span class="lg-g">${esc(latest.grade || "")}</span></div>
    <p class="last-for">${esc(latest.assignment_title || "Practice run")}, ${esc(relTime(latest.created_at))}</p>
    ${fixes.length ? `<ol class="fix-mini" aria-label="Fix these first">${fixes.map((t) => `<li>${esc(t)}</li>`).join("")}</ol>` : ""}
    <div class="row-btns"><a class="ghost" href="/jobs/${esc(latest.job_id)}">Read the full feedback</a></div></article>`;
}

export async function dashboard(view) {
  const d = await api("/api/student/dashboard");
  const s = d.stats;
  const first = d.user.name.split(" ")[0];
  const isOpen = (a) => !a.due_at || new Date(a.due_at) > new Date();
  const open = d.assignments.filter((a) => !a.mine && isOpen(a));
  const next = [...open].sort(byDue)[0];
  const improve = next ? null : d.assignments.filter((a) => a.mine && a.mine.best != null && isOpen(a))
    .sort((a, b) => a.mine.best - b.mine.best)[0];
  const latest = d.recent.find((r) => r.status === "done" && r.final_score != null);
  const hour = new Date().getHours();
  const hello = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const grading = d.recent.some((r) => r.status === "queued" || r.status === "running");
  const toLevel = s.level_size - s.into_level;
  view.innerHTML = `
  <header class="s-head">
    <div><h1>${hello}, ${esc(first)}</h1>
      <p class="sub">${open.length ? `${open.length} assignment${open.length > 1 ? "s are" : " is"} waiting for a first submission.` : "Every open assignment has a submission from you."}</p></div>
    <div class="xp" title="You earn XP from your best score on each assignment and from lab tasks the server checks">
      <div class="xp-t"><span>Level <b>${s.level}</b></span><span>${s.xp} XP, ${toLevel} more to level ${s.level + 1}</span></div>
      ${progressBar(s.into_level, s.level_size, "Progress to the next level")}
    </div>
  </header>
  ${grading ? `<div class="banner"><span class="spinner"></span><span>One of your submissions is being reviewed. This page updates by itself when it's done.</span></div>` : ""}
  <section class="focus">${nextCard(next, improve)}${lastCard(latest, d.top_priorities)}</section>
  <section class="report-row" aria-label="Your numbers">
    <div><span>Average score</span><b>${s.avg_score ?? "–"}</b><em>${s.avg_score != null ? "best try on each assignment" : "appears after your first grade"}</em></div>
    <div><span>Assignments done</span><b>${s.assignments_done}<small>of ${s.assignments_total}</small></b>${progressBar(s.assignments_done, s.assignments_total, "Assignments completed")}</div>
    <div><span>Lab tasks</span><b>${s.labs_done}<small>of ${s.labs_total}</small></b>${progressBar(s.labs_done, s.labs_total, "Lab tasks completed")}</div>
    <div><span>Class rank</span><b>${s.rank ? `#${s.rank}` : "–"}</b><em>${s.rank ? `<a href="/student/leaderboard">See the leaderboard</a>` : "earn XP to get a rank"}</em></div>
  </section>
  <section class="grid-2-1">
    <div class="panel"><div class="panel-h"><h2>Score history</h2><span class="hint">${d.timeline.length} graded</span></div>${lineChart(d.timeline)}</div>
    <div class="panel"><div class="panel-h"><h2>Skills</h2><span class="hint">out of 10</span></div>
      ${Object.values(d.skills).some((v) => v != null) ? radarChart(d.skills) : emptyState("No skills yet", "Your skill profile appears after your first feedback.", "", "target")}</div>
  </section>
  <section class="grid-1-1">
    <div class="panel"><div class="panel-h"><h2>Deadlines</h2><a href="/student/assignments">All assignments</a></div>
      ${d.upcoming.length ? `<ul class="list due-list">${d.upcoming.map((a) => {
        const soon = daysLeft(a.due_at) < 3;
        return `<li><span class="list-ico">${icon(TRACK_ICON[a.track] || "book")}</span>
        <div class="li-main"><a href="/student/assignment/${a.id}"><b>${esc(a.title)}</b></a><span>${esc(fmtDate(a.due_at, true))}</span></div>
        ${a.mine?.best != null ? gradeBadge(a.mine.best, "") : `<span class="when${soon ? " soon" : ""}">${esc(relTime(a.due_at))}</span>`}</li>`;
      }).join("")}</ul>`
        : emptyState("No upcoming deadlines", "Nothing is due right now.", "", "calendar")}
    </div>
    <div class="panel"><div class="panel-h"><h2>What to learn next</h2><a href="/labs">Labs</a></div>
      ${d.learning_path.length ? `<ul class="learn-list">${d.learning_path.slice(0, 4).map((x) => `<li>${icon("book")}<p>${learnLine(x)}</p></li>`).join("")}</ul>`
        : emptyState("Nothing here yet", "After your first feedback you get a short list of topics to study, picked from your own code.", `<a class="ghost sm" href="/labs">Explore the labs</a>`, "bulb")}
    </div>
  </section>
  <section class="panel"><div class="panel-h"><h2>Recent submissions</h2><a href="/student/submissions">See all</a></div>${subsTable(d.recent.slice(0, 5))}</section>`;
  if (grading) {
    const t = setTimeout(() => window.__refresh(), 5000);
    return () => clearTimeout(t);
  }
  return null;
}

// ------------------------------------------------------------------------------------ assignments
export async function assignments(view) {
  const rows = await api("/api/assignments");
  const isInstructor = state.user?.role === "instructor";
  const isOpen = (a) => !a.due_at || new Date(a.due_at) > new Date();
  // To do first (soonest deadline first), then the ones you've submitted, then closed ones.
  const rank = (a) => (isOpen(a) ? (a.mine ? 1 : 0) : 2);
  const sorted = [...rows].sort((a, b) => rank(a) - rank(b) || byDue(a, b));
  view.innerHTML = `${pageHeader("", "Assignments", "Each one lists exactly what will be checked. Submit as many times as you like: your best score counts.",
      isInstructor ? `<a class="btn" href="/instructor/assignments">${icon("edit")} Manage assignments</a>` : "")}
    ${rows.length ? `<section class="cards">${sorted.map((a) => `<article class="card a-card${!a.mine && isOpen(a) ? " todo" : ""}">
      <div class="card-top"><span class="chip track">${icon(TRACK_ICON[a.track] || "book")} ${esc(TRACKS[a.track] || a.track)}</span>${dueChip(a.due_at)}</div>
      <h2><a href="/student/assignment/${a.id}">${esc(a.title)}</a></h2>
      <p>${esc(a.description)}</p>
      <div class="card-foot">
        ${a.mine ? `<span class="a-best">Best ${gradeBadge(a.mine.best, "")} after ${a.mine.attempts} ${a.mine.attempts > 1 ? "tries" : "try"}</span>`
          : `<span class="hint">${isOpen(a) ? "Not submitted yet" : "You didn't submit this one"}</span>`}
        <a class="${a.mine ? "ghost" : "btn"} sm" href="/student/assignment/${a.id}">${a.mine ? "Improve" : "Start"}</a></div>
    </article>`).join("")}</section>`
      : `<section class="panel">${emptyState("No assignments yet", "Your instructor hasn't published any assignments. The labs are open in the meantime.", `<a class="btn" href="/labs">Open the labs</a>`, "book")}</section>`}`;
}

function rubricPanel(a, best) {
  const weights = Object.entries(a.weights).sort((x, y) => y[1] - x[1]);
  return `<div class="panel"><h2>${icon("target")} How it's scored</h2>
    ${weights.map(([k, w]) => `<div class="weight-row"><span class="wr-ico">${icon(DIM_ICON[k] || "star")}</span>
      <div class="wr-main"><b>${esc(DIMENSIONS[k] || k)}</b><span>${esc(DIM_HELP[k] || "")}</span></div>
      <span class="wr-pct">${Math.round(w * 100)}%</span></div>`).join("")}
    ${best?.dims ? `<h3>Your best try</h3><div class="hbars">${weights.map(([k]) => best.dims[k] == null ? "" : `<div class="hb"><span class="hb-l">${esc(DIMENSIONS[k])}</span>
      <div class="hb-t"><span class="${gradeClass(best.dims[k] * 10)}" style="width:${best.dims[k] * 10}%"></span></div>
      <span class="hb-v">${best.dims[k].toFixed(1)}</span></div>`).join("")}</div>` : ""}
  </div>`;
}

export async function assignment(view, { id }) {
  // Instructors get the assignment's analytics page instead of a submit form.
  if (state.user?.role === "instructor") { window.__nav(`/instructor/assignment/${encodeURIComponent(id)}`, { replace: true }); return null; }
  const a = await api(`/api/assignments/${encodeURIComponent(id)}`);
  const checks = (a.rubric_notes || "").split(/;|\n|\.\s/).map((x) => x.trim().replace(/\.$/, "")).filter((x) => x.length > 3)
    .map((c) => c.charAt(0).toUpperCase() + c.slice(1));
  const subs = a.submissions || [];
  // An instructor-adjusted grade is the grade for this assignment, even if a later attempt scored higher.
  const best = subs.find((s) => s.override && s.status === "done")
    || subs.filter((s) => s.final_score != null).sort((x, y) => y.final_score - x.final_score)[0];
  const closed = a.due_at && new Date(a.due_at) < new Date();
  view.innerHTML = `
  ${pageHeader(`<a href="/student/assignments">Assignments</a> / ${esc(TRACKS[a.track] || a.track)}`, esc(a.title),
    `${dueChip(a.due_at)} ${a.due_at ? `<span class="hint">${esc(fmtDate(a.due_at, true))}</span>` : ""}`,
    best ? `<div class="best-badge">${scoreRing(best.final_score, "", 56)}<div><span>Your best so far</span><b>${esc(best.final_score)} out of 100, grade ${esc(best.grade || "")}</b></div></div>` : "")}
  <section class="grid-2-1">
    <div>
      <div class="panel"><h2>${icon("book")} The brief</h2><p>${esc(a.description)}</p>
        ${checks.length ? `<h3>What will be checked</h3><ul class="checklist">${checks.map((c) => `<li>${icon("checkCircle")}<span>${esc(c)}</span></li>`).join("")}</ul>` : ""}
      </div>
      <div class="submit-card" id="submit-card">
        <h2>${icon("upload")} ${best ? "Submit an improved version" : "Submit your project"}</h2>
        ${closed ? `<div class="banner warn">${icon("alert")}<span>The deadline has passed. You can still submit, and late work is marked with its date.</span></div>` : ""}
        <form id="submit-form" class="form" novalidate>
          ${repoFields("s-")}
          <p id="err" class="error" role="alert"></p>
          <button class="btn lg" id="go" type="submit">Submit for feedback</button>
        </form>
      </div>
    </div>
    ${rubricPanel(a, best)}
  </section>
  <div id="live-host"></div>
  <section class="panel"><div class="panel-h"><h2>Your attempts</h2><span class="hint">${subs.length ? `${subs.length} so far, best one counts` : ""}</span></div><div id="attempts">${subsTable(subs, { showAssignment: false })}</div></section>`;
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
      toast("Submitted. Reviewing your project now.", "ok");
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
  view.innerHTML = `${pageHeader("", "My submissions", `${rows.length} submission${rows.length === 1 ? "" : "s"}, ${graded.length} with feedback. Open any one to read the full review.`,
      `<a class="ghost" href="/grader">${icon("zap")} Practice run</a>`)}
    <section class="panel">${subsTable(rows)}</section>`;
}

export async function leaderboard(view) {
  const d = await api("/api/leaderboard");
  const podium = d.rows.slice(0, 3);
  const place = ["1st", "2nd", "3rd"];
  view.innerHTML = `${pageHeader("", "Leaderboard", "XP comes from your best score on each assignment, plus 20 XP for every lab task the server checks.",
      d.me ? `<div class="best-badge"><span class="stat-ico">${icon("trophy")}</span><div><span>Your rank</span><b>#${d.me.rank}, ${d.me.xp} XP</b></div></div>` : "")}
    ${podium.length ? `<section class="podium">${podium.map((r, i) => `<div class="pod p${i + 1}"><span class="place"><span>${place[i]}</span></span>
      <b>${esc(r.name)}</b><em>${r.xp} XP</em></div>`).join("")}</section>` : ""}
    <section class="panel">${d.rows.length ? `<div class="table-wrap"><table><thead><tr><th>Rank</th><th>Student</th><th class="num">XP</th>
      <th class="num hide-sm">Assignments</th><th class="num">Average best</th><th class="num hide-sm">Lab tasks</th></tr></thead><tbody>
      ${d.rows.map((r) => {
        const me = d.me && r.user_id === d.me.user_id;
        return `<tr class="${me ? "me" : ""}"><td><b>#${r.rank}</b></td><td>${esc(r.name)}${me ? " <b>(you)</b>" : ""}</td>
        <td class="num"><b>${r.xp}</b></td><td class="num hide-sm">${r.assignments_done}</td><td class="num">${r.avg_best ?? "–"}</td><td class="num hide-sm">${r.labs_done}</td></tr>`;
      }).join("")}
      </tbody></table></div>` : emptyState("The leaderboard is empty", "Finish an assignment or a lab task to be the first one here.", "", "trophy")}</section>`;
}

export async function profile(view) {
  const u = state.user;
  view.innerHTML = `${pageHeader("", "Profile", `Member since ${esc(fmtDate(u.created_at))}`)}
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
      <button class="btn" type="submit">Change password</button>
    </form>
  </section>`;
  $("#profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const res = await api("/api/me", { method: "PUT", body: { name: $("#p-name").value.trim(), entry_no: $("#p-entry").value.trim() || null } });
      state.user = res.user;
      window.dispatchEvent(new Event("auth-changed"));
      toast("Changes saved", "ok");
    } catch (err) { toast(err.message, "error"); }
  });
  $("#pw-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#pw-err").textContent = "";
    try {
      await api("/api/me/password", { method: "POST", body: { current: $("#pw-cur").value, new: $("#pw-new").value } });
      e.target.reset();
      toast("Password changed", "ok");
    } catch (err) { $("#pw-err").textContent = err.status === 403 ? "Your current password isn't right." : err.message; }
  });
}
