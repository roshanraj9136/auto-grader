import { $, DEFAULT_WEIGHTS, DIMENSIONS, TRACKS, api, barChart, emptyState, esc, fmtDate, hbars, pct, toast } from "../core.js";
import { subsTable } from "./student.js";

function stat(label, value, sub = "", cls = "") {
  return `<div class="stat ${cls}"><span class="stat-l">${esc(label)}</span><b class="stat-v">${value}</b>${sub ? `<span class="stat-s">${sub}</span>` : ""}</div>`;
}

export async function dashboard(view) {
  const d = await api("/api/instructor/overview");
  const c = d.counts;
  const dist = Object.entries(d.grade_distribution);
  view.innerHTML = `
  <header class="page-h"><div><p class="kicker">Instructor</p><h1>Class overview</h1>
    <p class="hint">Live view of every submission graded by the agents.</p></div>
    <div class="row-btns"><a class="btn" href="/instructor/assignments">New assignment</a>
      <a class="btn ghost" href="/api/instructor/gradebook.csv" download>Export gradebook (CSV)</a></div></header>
  <section class="stats">
    ${stat("Students", c.students, "", "acc")}
    ${stat("Assignments", c.assignments, "", "cyan")}
    ${stat("Submissions", c.submissions, `${c.graded} graded · ${c.active} in progress`, "green")}
    ${stat("Class average", d.class_avg ?? "–", "best attempt per student", "amber")}
  </section>
  <section class="grid-1-1">
    <div class="panel"><div class="panel-h"><h2>Grade distribution</h2><span class="hint">best attempt per student & assignment</span></div>
      ${dist.some(([, v]) => v) ? barChart(dist, { colorFn: (g) => (g.startsWith("A") ? "g-a" : g.startsWith("B") ? "g-b" : g.startsWith("C") ? "g-c" : "g-f") })
        : emptyState("No grades yet", "")}</div>
    <div class="panel"><div class="panel-h"><h2>Where the class struggles</h2><span class="hint">average per dimension, /10</span></div>
      ${hbars(Object.entries(d.dimension_avg).map(([k, v]) => [DIMENSIONS[k] || k, v]), { max: 10, fmt: (v) => v.toFixed(1) })}
      <p class="hint">Use the weakest dimension to pick next week's lab or lecture topic.</p></div>
  </section>
  <section class="panel"><div class="panel-h"><h2>Assignments</h2><a href="/instructor/assignments">manage →</a></div>
    ${d.assignments.length ? `<div class="table-wrap"><table><thead><tr><th>Assignment</th><th>Track</th><th>Due</th><th class="num">Students</th>
      <th>Completion</th><th class="num">Submissions</th><th class="num">Avg best</th><th class="num">Top</th></tr></thead><tbody>
      ${d.assignments.map((a) => `<tr><td><a href="/student/assignment/${a.id}">${esc(a.title)}</a></td><td><span class="chip track">${esc(TRACKS[a.track] || a.track)}</span></td>
        <td>${esc(fmtDate(a.due_at))}</td><td class="num">${a.students_submitted}</td>
        <td><div class="bar sm"><span style="width:${pct(a.completion)}"></span></div> <span class="hint">${pct(a.completion)}</span></td>
        <td class="num">${a.submissions}</td><td class="num">${a.avg_best ?? "–"}</td><td class="num">${a.max_best ?? "–"}</td></tr>`).join("")}
      </tbody></table></div>` : emptyState("No assignments", "", `<a class="btn" href="/instructor/assignments">Create one</a>`)}</section>
  <section class="panel"><div class="panel-h"><h2>Lab activity</h2></div>
    ${d.labs.length ? `<div class="chips">${d.labs.map((l) => `<span class="chip">${esc(l.lab)}: ${l.n} tasks by ${l.students} student(s)</span>`).join("")}</div>` : `<p class="hint">No lab activity yet.</p>`}</section>
  <section class="panel"><div class="panel-h"><h2>Latest submissions</h2></div>${recentTable(d.recent)}</section>`;
  if (c.active) {
    const t = setTimeout(() => window.__refresh(), 6000);
    return () => clearTimeout(t);
  }
  return null;
}

function recentTable(rows) {
  if (!rows.length) return emptyState("No submissions yet", "They will appear here as students submit.");
  return `<div class="table-wrap"><table><thead><tr><th>When</th><th>Student</th><th>Assignment</th><th>Repository</th><th>Status</th><th class="num">Score</th><th></th></tr></thead><tbody>
    ${rows.map((s) => `<tr><td>${esc(fmtDate(s.created_at, true))}</td><td>${esc(s.student)}${s.entry_no ? ` <span class="hint">${esc(s.entry_no)}</span>` : ""}</td>
      <td>${esc(s.assignment_title || "Practice")}</td>
      <td class="repo"><a href="${esc(s.repo_url)}" target="_blank" rel="noopener">${esc(s.repo_url.replace("https://github.com/", ""))}</a>
        ${s.shared_by > 1 ? `<span class="chip warn" title="Same repository submitted by ${s.shared_by} students for this assignment: group work or copying?">shared ×${s.shared_by}</span>` : ""}</td>
      <td><span class="pill ${s.status === "done" ? "ok" : s.status === "failed" ? "bad" : "run"}">${esc(s.status)}</span></td>
      <td class="num">${s.final_score ?? ""} ${esc(s.grade || "")}</td>
      <td>${s.status === "done" ? `<a href="/api/jobs/${s.job_id}/report.html" target="_blank" rel="noopener">report ↗</a>` : ""}</td></tr>`).join("")}
    </tbody></table></div>`;
}

function toLocalInput(iso) {
  // <input type="datetime-local"> works in local time without an offset; the API stores UTC.
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function assignmentForm(a = null) {
  const w = a?.weights || DEFAULT_WEIGHTS;
  const due = toLocalInput(a?.due_at);
  return `<form id="a-form" class="form" novalidate>
    <input type="hidden" id="a-id" value="${a?.id ?? ""}" />
    <div class="grid2">
      <div class="field"><label for="a-title">Title</label><input id="a-title" required minlength="3" maxlength="120" value="${esc(a?.title || "")}" /></div>
      <div class="field"><label for="a-track">Track</label><select id="a-track">${Object.entries(TRACKS).map(([k, v]) =>
        `<option value="${k}"${(a?.track || "fullstack") === k ? " selected" : ""}>${v}</option>`).join("")}</select></div>
    </div>
    <div class="field"><label for="a-desc">Description (shown to students)</label><textarea id="a-desc" rows="3">${esc(a?.description || "")}</textarea></div>
    <div class="field"><label for="a-notes">Rubric notes (given to every agent and the judge)</label>
      <textarea id="a-notes" rows="3" placeholder="e.g. docker-compose with nginx in front of 2 API replicas; PostgreSQL on a private network; integration tests in CI">${esc(a?.rubric_notes || "")}</textarea></div>
    <fieldset><legend>Rubric weights <span class="hint">(normalised; 0 disables an agent)</span></legend>
      <div class="weights">${Object.entries(DIMENSIONS).map(([k, label]) => `<div><label for="aw-${k}">${label}</label>
        <input id="aw-${k}" type="number" min="0" max="1" step="0.05" value="${w[k] ?? 0}" /></div>`).join("")}</div></fieldset>
    <div class="field"><label for="a-due">Deadline <span class="hint">(local time)</span></label><input id="a-due" type="datetime-local" value="${esc(due)}" /></div>
    <p id="a-err" class="error" role="alert"></p>
    <div class="row-btns"><button class="btn" type="submit">${a ? "Save changes" : "Publish assignment"}</button>
      ${a ? `<button class="ghost" type="button" id="a-cancel">Cancel</button>` : ""}</div>
  </form>`;
}

export async function assignments(view) {
  const load = async () => {
    const rows = await api("/api/assignments");
    $("#a-list").innerHTML = rows.length ? `<div class="table-wrap"><table><thead><tr><th>Title</th><th>Track</th><th>Due</th><th class="num">Students</th><th></th></tr></thead><tbody>
      ${rows.map((a) => `<tr><td><a href="/student/assignment/${a.id}">${esc(a.title)}</a></td><td><span class="chip track">${esc(TRACKS[a.track] || a.track)}</span></td>
        <td>${esc(fmtDate(a.due_at, true))}</td><td class="num">${a.class_stats.students}</td>
        <td class="actions"><button class="ghost sm" data-edit="${a.id}" type="button">Edit</button>
          <button class="ghost sm danger" data-del="${a.id}" type="button">Delete</button></td></tr>`).join("")}</tbody></table></div>`
      : emptyState("No assignments yet", "Create the first one with the form.");
    $("#a-list").querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => {
      edit(rows.find((r) => String(r.id) === b.dataset.edit));
    }));
    $("#a-list").querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      const a = rows.find((r) => String(r.id) === b.dataset.del);
      if (!confirm(`Delete "${a.title}" and all of its submissions? This cannot be undone.`)) return;
      await api(`/api/assignments/${a.id}`, { method: "DELETE" });
      toast("Assignment deleted");
      load();
    }));
  };
  const edit = (a = null) => {
    $("#a-form-host").innerHTML = `<h2>${a ? "Edit assignment" : "New assignment"}</h2>${assignmentForm(a)}`;
    $("#a-cancel")?.addEventListener("click", () => edit(null));
    $("#a-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      $("#a-err").textContent = "";
      const due = $("#a-due").value;
      const body = {
        title: $("#a-title").value.trim(), track: $("#a-track").value, description: $("#a-desc").value.trim(),
        rubric_notes: $("#a-notes").value.trim(),
        weights: Object.fromEntries(Object.keys(DIMENSIONS).map((k) => [k, parseFloat($(`#aw-${k}`).value) || 0])),
        due_at: due ? new Date(due).toISOString() : null,
      };
      try {
        const id = $("#a-id").value;
        await api(id ? `/api/assignments/${id}` : "/api/assignments", { method: id ? "PUT" : "POST", body });
        toast(id ? "Assignment updated" : "Assignment published", "ok");
        edit(null);
        load();
      } catch (err) { $("#a-err").textContent = err.message; }
    });
    if (a) $("#a-form-host").scrollIntoView({ behavior: "smooth" });
  };
  view.innerHTML = `<header class="page-h"><div><p class="kicker">Instructor</p><h1>Manage assignments</h1>
    <p class="hint">Rubric weights and notes steer the five specialist agents and the judge for every submission.</p></div></header>
    <section class="grid-1-1"><div class="panel" id="a-form-host"></div><div class="panel"><h2>Published</h2><div id="a-list"></div></div></section>`;
  edit(null);
  await load();
}

export async function students(view) {
  const rows = await api("/api/instructor/students");
  view.innerHTML = `<header class="page-h"><div><p class="kicker">Instructor</p><h1>Students</h1><p class="hint">${rows.length} registered student(s).</p></div>
    <a class="btn ghost" href="/api/instructor/gradebook.csv" download>Export gradebook (CSV)</a></header>
    <section class="panel">${rows.length ? `<div class="field"><label for="filter">Filter</label><input id="filter" placeholder="name, email or entry number" /></div>
      <div class="table-wrap"><table><thead><tr><th>Name</th><th>Entry no</th><th>Email</th><th class="num">Rank</th><th class="num">XP</th>
      <th class="num">Avg best</th><th class="num">Submissions</th><th class="num">Lab tasks</th><th>Last active</th></tr></thead><tbody id="st-body">
      ${rows.map((r) => `<tr data-q="${esc(`${r.name} ${r.email} ${r.entry_no || ""}`.toLowerCase())}"><td>${esc(r.name)}</td><td>${esc(r.entry_no || "")}</td><td>${esc(r.email)}</td>
        <td class="num">${r.rank ?? "–"}</td><td class="num">${r.xp}</td><td class="num">${r.avg_best ?? "–"}</td><td class="num">${r.submissions}</td>
        <td class="num">${r.labs_done}</td><td>${esc(fmtDate(r.last_active, true))}</td></tr>`).join("")}</tbody></table></div>`
      : emptyState("No students yet", "Students appear here after they create an account.")}</section>`;
  $("#filter")?.addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    view.querySelectorAll("#st-body tr").forEach((tr) => { tr.hidden = q && !tr.dataset.q.includes(q); });
  });
}

export { subsTable };
