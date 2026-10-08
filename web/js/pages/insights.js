// Instructor deep views: the gradebook matrix, one assignment's analytics, one student's profile,
// and the grade-adjustment dialog. Write actions carry data-write so the read-only demo can disable them.
import {
  $, DIMENSIONS, TRACKS, api, barChart, daysLeft, emptyState, esc, fmtDate, fmtMs, gradeBadge, gradeClass, hbars,
  icon, isReadOnly, lineChart, pageHeader, radarChart, relTime, statusPill, toast,
} from "../core.js";

const LOW = 50;
const LAB_NAMES = { frontend: "Frontend", database: "Databases", loadbalancer: "Load balancers", network: "Networks", docker: "Docker" };
const repoShort = (url) => String(url || "").replace("https://github.com/", "");
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const fmt1 = (v) => (v == null ? "–" : Number(v).toFixed(1));

function adjustedMark(o) {
  return o ? ` <span class="adj" title="Adjusted by ${esc(o.by_name || "an instructor")} from ${esc(fmt1(o.original_score))}: ${esc(o.reason)}">adjusted</span>` : "";
}

// ------------------------------------------------------------------------------------ adjust dialog
/** Set or revert a graded submission's score. Calls onDone() after a change. */
export function openAdjust({ submissionId, score, studentName, override, onDone }) {
  const dlg = document.createElement("dialog");
  dlg.className = "adjust";
  dlg.innerHTML = `<form method="dialog" class="form" novalidate>
      <h2>Adjust grade</h2>
      <p class="hint">${esc(studentName || "Student")}, currently <b>${esc(fmt1(score))}</b> out of 100${override ? `, adjusted from ${esc(fmt1(override.original_score))}` : ""}.
        The student sees the new score and your reason on their feedback page.</p>
      <label for="adj-score">New score (0 to 100)</label>
      <input id="adj-score" type="number" min="0" max="100" step="0.1" required value="${esc(score ?? "")}" />
      <label for="adj-reason">Reason</label>
      <textarea id="adj-reason" rows="3" maxlength="500" required placeholder="e.g. Tests run in CI but the grader could not detect them">${esc(override?.reason || "")}</textarea>
      <p class="error" id="adj-err" role="alert"></p>
      <div class="row-btns">
        <button class="btn" type="submit" value="save">Save score</button>
        ${override ? `<button class="ghost" type="button" id="adj-revert">Restore original (${esc(fmt1(override.original_score))})</button>` : ""}
        <button class="ghost" type="button" id="adj-cancel">Cancel</button>
      </div></form>`;
  document.body.appendChild(dlg);
  const close = () => { dlg.close(); dlg.remove(); };
  dlg.addEventListener("cancel", () => dlg.remove());
  dlg.querySelector("#adj-cancel").addEventListener("click", close);
  dlg.querySelector("#adj-revert")?.addEventListener("click", async () => {
    try {
      await api(`/api/instructor/submissions/${submissionId}/override`, { method: "DELETE" });
      toast("Original score restored", "ok");
      close();
      onDone?.();
    } catch (e) { dlg.querySelector("#adj-err").textContent = e.message; }
  });
  dlg.querySelector("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const v = parseFloat(dlg.querySelector("#adj-score").value);
    const reason = dlg.querySelector("#adj-reason").value.trim();
    if (!(v >= 0 && v <= 100)) { dlg.querySelector("#adj-err").textContent = "Enter a score between 0 and 100."; return; }
    if (reason.length < 3) { dlg.querySelector("#adj-err").textContent = "Write a short reason. The student will see it."; return; }
    try {
      const r = await api(`/api/instructor/submissions/${submissionId}/override`, { method: "POST", body: { score: v, reason } });
      toast(`Score set to ${r.score} (${r.grade})`, "ok");
      close();
      onDone?.();
    } catch (err) { dlg.querySelector("#adj-err").textContent = err.message; }
  });
  dlg.showModal();
  dlg.querySelector("#adj-score").focus();
}

async function regrade(submissionId) {
  try {
    await api(`/api/instructor/submissions/${submissionId}/regrade`, { method: "POST" });
    toast("Grading again. The new attempt appears in a minute.", "ok");
  } catch (e) { toast(e.message, "error"); }
}

function bindRowActions(root, rowsById, refresh) {
  root.querySelectorAll("[data-adjust]").forEach((b) => b.addEventListener("click", () => {
    const r = rowsById.get(b.dataset.adjust);
    if (r) openAdjust({ ...r, onDone: refresh });
  }));
  root.querySelectorAll("[data-regrade]").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true;
    await regrade(b.dataset.regrade);
    setTimeout(refresh, 1500);
  }));
}

// ------------------------------------------------------------------------------------ gradebook
function cell(c, a) {
  if (!c) {
    const missing = a.due_at && daysLeft(a.due_at) < 0;
    return `<td class="gb-cell ${missing ? "missing" : "empty"}">${missing ? "Missing" : "–"}</td>`;
  }
  if (c.best == null) {
    const st = c.status === "failed" ? "Failed" : c.status === "done" ? "–" : "Grading";
    return `<td class="gb-cell empty" title="${c.attempts} attempt(s)">${st}</td>`;
  }
  const marks = `${c.late ? '<i class="late-dot" title="Best attempt was submitted after the deadline"></i>' : ""}${c.adjusted ? '<sup title="Adjusted by an instructor">adj</sup>' : ""}`;
  return `<td class="gb-cell ${gradeClass(c.best)}"><a href="/jobs/${esc(c.job_id)}" title="${esc(c.grade)}, ${c.attempts} attempt(s): open the feedback">
    <b>${esc(Math.round(c.best))}</b><span>${esc(c.grade || "")}</span>${marks}</a></td>`;
}

export async function gradebook(view) {
  const d = await api("/api/instructor/gradebook");
  let q = "";
  view.innerHTML = `${pageHeader(`<a href="/instructor/dashboard">Overview</a>`, "Gradebook",
      "Best graded attempt for every student and assignment. Open a score for the feedback, a name for the student, a column title for that assignment's analytics.",
      `<a class="ghost" href="/api/instructor/gradebook.csv" download>${icon("download")} Export CSV</a>`)}
    <section class="panel">
      <div class="toolbar"><input id="gb-q" type="search" placeholder="Search students" aria-label="Search students" />
        <span class="legend"><span class="gb-key g-a">A</span><span class="gb-key g-b">B</span><span class="gb-key g-c">C</span><span class="gb-key g-f">D/F</span>
          <span><i class="late-dot"></i> late</span><span><sup>adj</sup> adjusted</span><span class="missing-key">Missing</span> past deadline</span></div>
      ${d.students.length && d.assignments.length ? `<div class="table-wrap gb-wrap"><table class="gb"><thead><tr><th class="gb-name">Student</th>
        ${d.assignments.map((a) => `<th class="gb-col"><a href="/instructor/assignment/${a.id}">${esc(a.title)}</a>
          <span class="sub-l">${a.due_at ? `due ${esc(fmtDate(a.due_at))}` : "no deadline"}</span></th>`).join("")}
        <th class="num">Average</th></tr></thead><tbody id="gb-body"></tbody>
        <tfoot><tr><th class="gb-name">Class average</th>${d.assignments.map((a) => `<td class="gb-cell foot">${a.mean != null ? `<b>${esc(fmt1(a.mean))}</b><span>${a.count} graded</span>` : "–"}</td>`).join("")}
          <td></td></tr></tfoot></table></div>`
        : emptyState("Nothing to show yet", "The gradebook fills in as students submit work for your assignments.", "", "list")}
    </section>`;
  const paint = () => {
    const body = $("#gb-body");
    if (!body) return;
    const rows = d.students.filter((s) => !q || `${s.name} ${s.email} ${s.entry_no || ""}`.toLowerCase().includes(q));
    body.innerHTML = rows.map((s) => `<tr><th class="gb-name"><a href="/instructor/student/${s.id}">${esc(s.name)}</a><span class="sub-l">${esc(s.entry_no || s.email)}</span></th>
      ${d.assignments.map((a) => cell(s.cells[String(a.id)], a)).join("")}
      <td class="num">${s.avg != null ? gradeBadge(s.avg, "") : "–"}</td></tr>`).join("")
      || `<tr><td colspan="${d.assignments.length + 2}">${emptyState("No students match", "Try another search.", "", "users")}</td></tr>`;
  };
  $("#gb-q")?.addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase(); paint(); });
  paint();
}

// ------------------------------------------------------------------------------------ assignment analytics
export async function assignmentReport(view, { id }) {
  const load = () => api(`/api/instructor/assignments/${encodeURIComponent(id)}`);
  let d = await load();
  const render = () => {
    const a = d.assignment;
    const s = d.stats;
    const left = daysLeft(a.due_at);
    const weights = Object.entries(a.weights).sort((x, y) => y[1] - x[1]);
    const rowsById = new Map();
    const labels = ["0", "10", "20", "30", "40", "50", "60", "70", "80", "90+"];
    view.innerHTML = `
    ${pageHeader(`<a href="/instructor/assignments">Assignments</a> / ${esc(TRACKS[a.track] || a.track)}`, esc(a.title),
      `${a.due_at ? `${left < 0 ? "Closed" : "Due"} ${esc(fmtDate(a.due_at, true))}, ${esc(relTime(a.due_at))}` : "No deadline"}`,
      `<a class="ghost" href="/instructor/assignments?edit=${a.id}" data-write>${icon("edit")} Edit</a>
       <button class="ghost" type="button" id="rerun-all" data-write title="Grade every student's latest submission again with the current rubric">${icon("refresh")} Re-run all</button>`)}
    <section class="ledger ledger-7" aria-label="Assignment numbers">
      <div><span>Submitted</span><b>${d.submitted}<small>of ${d.class_size}</small></b></div>
      <div><span>Average</span><b>${fmt1(s.mean)}</b></div>
      <div><span>Median</span><b>${fmt1(s.median)}</b></div>
      <div><span>Spread (std dev)</span><b>${fmt1(s.stdev)}</b></div>
      <div><span>Range</span><b>${s.count ? `${fmt1(s.min)}<small>to ${fmt1(s.max)}</small>` : "–"}</b></div>
      <div class="${d.below_low ? "flag" : ""}"><span>Below ${LOW}</span><b>${d.below_low}</b></div>
      <div class="${d.late ? "warn" : ""}"><span>Late attempts</span><b>${d.late}<small>of ${d.attempts}</small></b></div>
    </section>
    <section class="grid-1-1">
      <div class="panel"><div class="panel-h"><h2>Score distribution</h2><span class="hint">best attempt per student</span></div>
        ${s.count ? barChart(d.histogram.map((n, i) => [labels[i], n]), { colorFn: (l) => gradeClass(parseInt(l, 10) + 5) }) : emptyState("No grades yet", "The distribution appears as students submit.", "", "chart")}
        ${s.count ? `<p class="hint chart-note">Each bar counts students whose best score falls in that band of 10 points.</p>` : ""}</div>
      <div class="panel"><div class="panel-h"><h2>Average by area</h2><span class="hint">out of 10, best attempts</span></div>
        ${hbars(weights.map(([k]) => [DIMENSIONS[k] || k, d.dimension_avg[k]]), { max: 10, fmt: (v) => v.toFixed(1) })}
        <div class="weights-mini" style="margin-top:14px">${weights.map(([k, w]) => `<span>${esc(DIMENSIONS[k] || k)} ${Math.round(w * 100)}%</span>`).join("")}</div></div>
    </section>
    <section class="grid-1-1">
      <div class="panel"><div class="panel-h"><h2>Not submitted yet</h2><span class="hint">${plural(d.not_submitted.length, "student")}</span></div>
        ${d.not_submitted.length ? `<ul class="name-list">${d.not_submitted.map((u) => `<li><a href="/instructor/student/${u.id}">${esc(u.name)}</a><span>${esc(u.entry_no || "")}</span></li>`).join("")}</ul>`
          : `<p class="attn-ok">${icon("checkCircle")} Everyone has submitted.</p>`}</div>
      <div class="panel ${d.similar.length ? "attn" : ""}"><div class="panel-h"><h2>${d.similar.length ? icon("alert") : ""} Possible copying</h2><span class="hint">same repository or same commit</span></div>
        ${d.similar.length ? `<ul class="attn-list">${d.similar.map((g) => `<li><span class="mk" aria-hidden="true"></span><div>
          <b>${esc(g.students.join(", "))}</b>
          <p>${g.kind === "same repository" ? `Same repository <span class="mono">${esc(repoShort(g.repo_url))}</span>`
            : `Same commit <span class="mono">${esc(g.commit)}</span> in ${esc(g.repos.map(repoShort).join(" and "))}`}. Group work, or copying?</p></div><span></span></li>`).join("")}</ul>`
          : `<p class="attn-ok">${icon("checkCircle")} No two students submitted the same repository or commit.</p>`}</div>
    </section>
    <section class="panel"><div class="panel-h"><h2>Students</h2><span class="hint">${plural(d.submitted, "student")}, ${plural(d.attempts, "attempt")}; best attempt counts</span></div>
      ${d.students.length ? `<div class="table-wrap"><table><thead><tr><th>Student</th><th class="num">Best</th><th class="num hide-sm">Attempts</th>
        <th>Latest attempt</th><th class="hide-sm">Repository</th><th class="hide-sm">Time</th><th></th></tr></thead><tbody>
        ${d.students.map((p) => {
          const b = p.best, l = p.latest;
          if (b) rowsById.set(String(b.id), { submissionId: b.id, score: b.final_score, studentName: p.name, override: b.override });
          return `<tr><td><a href="/instructor/student/${p.user_id}"><b>${esc(p.name)}</b></a><span class="sub-l">${esc(p.entry_no || "")}</span></td>
            <td class="num">${b ? `${gradeBadge(b.final_score, b.grade)}${adjustedMark(b.override)}` : "–"}</td>
            <td class="num hide-sm">${p.attempts}</td>
            <td>${statusPill(l.status)}<span class="sub-l">${esc(fmtDate(l.created_at, true))}${l.late ? ' <span class="chip warn">late</span>' : ""}</span></td>
            <td class="repo hide-sm"><a href="${esc(l.repo_url)}" target="_blank" rel="noopener">${esc(repoShort(l.repo_url))}</a>${l.commit ? `<span class="sub-l">${esc(l.commit.slice(0, 7))}</span>` : ""}</td>
            <td class="hide-sm">${b?.total_ms ? esc(fmtMs(b.total_ms)) : "–"}</td>
            <td class="actions">${b ? `<a class="ghost sm" href="/jobs/${esc(b.job_id)}">Feedback</a>
              <button class="ghost sm" type="button" data-adjust="${b.id}" data-write>Adjust</button>` : ""}
              <button class="ghost sm" type="button" data-regrade="${l.id}" data-write title="Grade the latest attempt again">Re-run</button></td></tr>`;
        }).join("")}</tbody></table></div>`
        : emptyState("No submissions yet", "Students' work for this assignment shows up here.", "", "upload")}</section>
    <section class="grid-1-1">
      <div class="panel"><div class="panel-h"><h2>When students submitted</h2><span class="hint">attempts per day, last 3 weeks</span></div>
        ${d.by_day.length ? barChart(d.by_day.slice(-21).map((x) => [x.day.slice(5), x.n]), { height: 170 })
          : emptyState("No attempts yet", "Submissions per day appear here.", "", "calendar")}</div>
      <div class="panel"><div class="panel-h"><h2>The brief students see</h2><a href="/instructor/assignments?edit=${a.id}" data-write>Edit</a></div>
        <p>${esc(a.description)}</p>${a.rubric_notes ? `<h3>Checklist</h3><p class="hint">${esc(a.rubric_notes)}</p>` : ""}</div>
    </section>`;
    bindRowActions(view, rowsById, refresh);
    $("#rerun-all")?.addEventListener("click", async (e) => {
      if (!confirm(`Grade every student's latest submission for "${a.title}" again with the current rubric?`)) return;
      e.target.disabled = true;
      try {
        const r = await api(`/api/instructor/assignments/${a.id}/regrade`, { method: "POST" });
        toast(`${plural(r.queued, "grading")} queued${r.skipped ? `, ${r.skipped} skipped (already busy)` : ""}`, "ok");
      } catch (err) { toast(err.message, "error"); }
      e.target.disabled = false;
    });
    window.__applyReadOnly?.(view);
  };
  const refresh = async () => { try { d = await load(); render(); } catch (e) { toast(e.message, "error"); } };
  render();
}

// ------------------------------------------------------------------------------------ student profile
export async function studentProfile(view, { id }) {
  const load = () => api(`/api/instructor/students/${encodeURIComponent(id)}`);
  let d = await load();
  const render = () => {
    const u = d.user, s = d.stats;
    const status = !s.submissions ? ["none", "Not started"] : s.avg_best == null ? ["wait", "No grade yet"]
      : s.avg_best < LOW ? ["risk", `Below ${LOW}`] : ["ok", "On track"];
    const rowsById = new Map();
    for (const x of d.submissions) {
      if (x.status === "done") rowsById.set(String(x.id), { submissionId: x.id, score: x.final_score, studentName: u.name, override: x.override });
    }
    const labTotal = Object.values(d.labs).reduce((n, v) => n + v.length, 0);
    view.innerHTML = `
    ${pageHeader(`<a href="/instructor/students">Students</a>`, esc(u.name),
      `<span class="status-tag ${status[0]}">${status[1]}</span> ${u.entry_no ? `<span class="hint">${esc(u.entry_no)}</span>` : ""} <span class="hint">${esc(u.email)}</span>
       <span class="hint">joined ${esc(fmtDate(u.created_at))}</span>`)}
    <section class="ledger ledger-6" aria-label="Student numbers">
      <div class="${status[0] === "risk" ? "flag" : ""}"><span>Average best</span><b>${fmt1(s.avg_best)}</b></div>
      <div><span>Assignments graded</span><b>${s.assignments_done}<small>of ${d.assignments.length}</small></b></div>
      <div><span>Submissions</span><b>${s.submissions}<small>${s.graded} graded</small></b></div>
      <div><span>Lab tasks</span><b>${s.labs_done}</b></div>
      <div><span>XP and rank</span><b>${s.xp}<small>${s.rank ? `rank #${s.rank}` : "unranked"}</small></b></div>
      <div><span>Last active</span><b class="sm">${s.last_active ? esc(relTime(s.last_active)) : "Never"}</b></div>
    </section>
    <section class="grid-2-1">
      <div class="panel"><div class="panel-h"><h2>Score history</h2><span class="hint">${plural(d.timeline.length, "graded attempt")}</span></div>${lineChart(d.timeline)}</div>
      <div class="panel"><div class="panel-h"><h2>Skills</h2><span class="hint">average of the last 10, out of 10</span></div>
        ${Object.values(d.skills).some((v) => v != null) ? radarChart(d.skills) : emptyState("No skills yet", "Appears after the first graded submission.", "", "target")}</div>
    </section>
    <section class="panel"><div class="panel-h"><h2>Assignments</h2><span class="hint">best attempt counts</span></div>
      <div class="table-wrap"><table><thead><tr><th>Assignment</th><th class="num">Best</th><th class="num">Attempts</th><th class="hide-sm">Last attempt</th><th></th></tr></thead><tbody>
      ${d.assignments.map((a) => {
        const missing = !a.attempts && a.due_at && daysLeft(a.due_at) < 0;
        const ovr = a.submission_id ? rowsById.get(String(a.submission_id))?.override : null;
        return `<tr><td><a href="/instructor/assignment/${a.id}"><b>${esc(a.title)}</b></a><span class="sub-l">${a.due_at ? `due ${esc(fmtDate(a.due_at))}` : "no deadline"}</span></td>
          <td class="num">${a.best != null ? `${gradeBadge(a.best, a.grade)}${adjustedMark(ovr)}` : missing ? '<span class="chip bad">Missing</span>' : "–"}</td>
          <td class="num">${a.attempts}</td>
          <td class="hide-sm">${a.last_at ? esc(fmtDate(a.last_at, true)) : "–"}${a.late ? ' <span class="chip warn">late</span>' : ""}</td>
          <td class="actions">${a.job_id ? `<a class="ghost sm" href="/jobs/${esc(a.job_id)}">Feedback</a>
            <button class="ghost sm" type="button" data-adjust="${a.submission_id}" data-write>Adjust</button>` : ""}</td></tr>`;
      }).join("")}</tbody></table></div></section>
    <section class="grid-2-1">
      <div class="panel"><div class="panel-h"><h2>All submissions</h2><span class="hint">${plural(d.submissions.length, "submission")}</span></div>
        ${d.submissions.length ? `<div class="table-wrap"><table><thead><tr><th>Assignment</th><th class="hide-sm">Repository</th><th>Submitted</th><th class="num">Score</th><th></th></tr></thead><tbody>
          ${d.submissions.map((x) => `<tr><td>${esc(x.assignment_title || "Practice")}<span class="sub-l">${statusPill(x.status)}</span></td>
            <td class="repo hide-sm"><a href="${esc(x.repo_url)}" target="_blank" rel="noopener">${esc(repoShort(x.repo_url))}</a></td>
            <td>${esc(fmtDate(x.created_at, true))}</td>
            <td class="num">${gradeBadge(x.final_score, x.grade)}${adjustedMark(x.override)}</td>
            <td class="actions">${x.status === "done" ? `<a class="ghost sm" href="/jobs/${esc(x.job_id)}">Feedback</a>` : ""}
              <button class="ghost sm" type="button" data-regrade="${x.id}" data-write title="Grade this submission again">Re-run</button></td></tr>`).join("")}
          </tbody></table></div>` : emptyState("No submissions yet", "Nothing submitted so far.", "", "upload")}</div>
      <div class="panel"><div class="panel-h"><h2>Labs</h2><span class="hint">${plural(labTotal, "task")} done</span></div>
        ${labTotal ? `<ul class="list">${Object.entries(d.labs).filter(([, v]) => v.length).map(([lab, tasks]) => `<li><span class="list-ico">${icon({ frontend: "code", database: "database", loadbalancer: "network", network: "globe", docker: "box" }[lab] || "flask")}</span>
          <div class="li-main"><b>${esc(LAB_NAMES[lab] || lab)}</b><span>${esc(tasks.join(", "))}</span></div><span class="hint">${tasks.length}</span></li>`).join("")}</ul>`
          : emptyState("No lab work yet", "Finished lab tasks show up here.", "", "flask")}</div>
    </section>`;
    bindRowActions(view, rowsById, refresh);
    window.__applyReadOnly?.(view);
  };
  const refresh = async () => { try { d = await load(); render(); } catch (e) { toast(e.message, "error"); } };
  render();
}

