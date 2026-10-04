import { $, DEFAULT_WEIGHTS, DIMENSIONS, TRACKS, api, barChart, emptyState, esc, fmtDate, gradeBadge, hbars, icon, pageHeader, pct, statusPill, toast } from "../core.js";
import { subsTable } from "./student.js";

function stat(label, value, sub, ico, cls = "") {
  return `<div class="stat ${cls}"><div class="stat-top"><span class="stat-l">${esc(label)}</span><span class="stat-ico">${icon(ico)}</span></div>
    <b class="stat-v">${value}</b>${sub ? `<span class="stat-s">${sub}</span>` : ""}</div>`;
}

const LAB_NAMES = { frontend: "Frontend", database: "Databases", loadbalancer: "Load balancers", network: "Networks", docker: "Docker" };

export async function dashboard(view) {
  const d = await api("/api/instructor/overview");
  const c = d.counts;
  const dist = Object.entries(d.grade_distribution);
  const weakest = Object.entries(d.dimension_avg).filter(([, v]) => v != null).sort((a, b) => a[1] - b[1])[0];
  view.innerHTML = `
  ${pageHeader("Instructor", "Class overview", "Everything your students have submitted, at a glance.",
    `<a class="btn" href="/instructor/assignments">${icon("plus")} New assignment</a>
     <a class="ghost" href="/api/instructor/gradebook.csv" download>${icon("download")} Gradebook (CSV)</a>`)}
  <section class="stats">
    ${stat("Students", c.students, "", "users")}
    ${stat("Assignments", c.assignments, "", "book", "sky")}
    ${stat("Submissions", c.submissions, `${c.graded} graded${c.active ? ` · ${c.active} in progress` : ""}`, "upload", "violet")}
    ${stat("Class average", d.class_avg ?? "–", "best try per student", "target", "amber")}
  </section>
  <section class="grid-1-1">
    <div class="panel"><div class="panel-h"><h2>${icon("chart")} Grades</h2><span class="hint">best try per student</span></div>
      ${dist.some(([, v]) => v) ? barChart(dist, { colorFn: (g) => (g.startsWith("A") ? "g-a" : g.startsWith("B") ? "g-b" : g.startsWith("C") ? "g-c" : "g-f") })
        : emptyState("No grades yet", "Grades show up here as students submit.", "", "chart")}</div>
    <div class="panel"><div class="panel-h"><h2>${icon("target")} Where the class needs help</h2><span class="hint">average out of 10</span></div>
      ${hbars(Object.entries(d.dimension_avg).map(([k, v]) => [DIMENSIONS[k] || k, v]), { max: 10, fmt: (v) => v.toFixed(1) })}
      ${weakest ? `<div class="banner" style="margin:16px 0 0">${icon("bulb")}<span><b>${esc(DIMENSIONS[weakest[0]])}</b> is the weakest area. A good topic for the next lab or lecture.</span></div>` : ""}</div>
  </section>
  <section class="panel"><div class="panel-h"><h2>${icon("book")} Assignments</h2><a href="/instructor/assignments">Manage</a></div>
    ${d.assignments.length ? `<div class="table-wrap"><table><thead><tr><th>Assignment</th><th>Due</th><th class="num">Students</th>
      <th>Completion</th><th class="num">Average</th><th class="num">Top</th></tr></thead><tbody>
      ${d.assignments.map((a) => `<tr><td><a href="/student/assignment/${a.id}"><b>${esc(a.title)}</b></a><br><span class="chip track" style="margin-top:4px">${esc(TRACKS[a.track] || a.track)}</span></td>
        <td>${esc(fmtDate(a.due_at))}</td><td class="num">${a.students_submitted}</td>
        <td><div class="bar sm"><span style="width:${pct(a.completion)}"></span></div> <span class="hint">${pct(a.completion)}</span></td>
        <td class="num">${a.avg_best != null ? gradeBadge(a.avg_best, "") : "–"}</td><td class="num">${a.max_best ?? "–"}</td></tr>`).join("")}
      </tbody></table></div>` : emptyState("No assignments", "Create your first assignment to get started.", `<a class="btn" href="/instructor/assignments">Create one</a>`, "book")}</section>
  <section class="panel"><div class="panel-h"><h2>${icon("list")} Latest submissions</h2></div>${recentTable(d.recent)}</section>
  ${d.labs.length ? `<section class="panel"><div class="panel-h"><h2>${icon("flask")} Lab activity</h2></div>
    <div class="chips">${d.labs.map((l) => `<span class="chip">${esc(LAB_NAMES[l.lab] || l.lab)}: ${l.n} tasks by ${l.students} student${l.students > 1 ? "s" : ""}</span>`).join("")}</div></section>` : ""}`;
  if (c.active) {
    const t = setTimeout(() => window.__refresh(), 6000);
    return () => clearTimeout(t);
  }
  return null;
}

function recentTable(rows) {
  if (!rows.length) return emptyState("No submissions yet", "They'll appear here as students submit.", "", "upload");
  return `<div class="table-wrap"><table><thead><tr><th>Student</th><th>Assignment</th><th>Repository</th><th>Submitted</th><th>Status</th><th class="num">Score</th><th></th></tr></thead><tbody>
    ${rows.map((s) => `<tr><td><b>${esc(s.student)}</b>${s.entry_no ? `<br><span class="muted">${esc(s.entry_no)}</span>` : ""}</td>
      <td>${esc(s.assignment_title || "Practice")}</td>
      <td class="repo"><a href="${esc(s.repo_url)}" target="_blank" rel="noopener">${esc(s.repo_url.replace("https://github.com/", ""))}</a>
        ${s.shared_by > 1 ? `<br><span class="chip warn" title="The same repository was submitted by ${s.shared_by} students for this assignment: group work, or copying?">${icon("alert")} Shared by ${s.shared_by}</span>` : ""}</td>
      <td>${esc(fmtDate(s.created_at, true))}</td><td>${statusPill(s.status)}</td>
      <td class="num">${gradeBadge(s.final_score, s.grade)}</td>
      <td class="actions">${s.status === "done" ? `<a class="ghost sm" href="/jobs/${esc(s.job_id)}">View</a>` : ""}</td></tr>`).join("")}
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
    <div class="field"><label for="a-desc">Description <span class="muted">(shown to students)</span></label><textarea id="a-desc" rows="3">${esc(a?.description || "")}</textarea></div>
    <div class="field"><label for="a-notes">What will be checked <span class="muted">(separate items with ; and students see them as a checklist)</span></label>
      <textarea id="a-notes" rows="3" placeholder="e.g. docker-compose with nginx in front of 2 API replicas; PostgreSQL on a private network; integration tests in CI">${esc(a?.rubric_notes || "")}</textarea></div>
    <fieldset><legend>How much each area counts <span class="muted">(0 skips it)</span></legend>
      <div class="weights">${Object.entries(DIMENSIONS).map(([k, label]) => `<div><label for="aw-${k}">${label}</label>
        <input id="aw-${k}" type="number" min="0" max="1" step="0.05" value="${w[k] ?? 0}" /></div>`).join("")}</div></fieldset>
    <div class="field"><label for="a-due">Deadline <span class="muted">(your local time)</span></label><input id="a-due" type="datetime-local" value="${esc(due)}" /></div>
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
    $("#a-form-host").innerHTML = `<h2>${icon(a ? "edit" : "plus")} ${a ? "Edit assignment" : "New assignment"}</h2>${assignmentForm(a)}`;
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
  view.innerHTML = `${pageHeader("Instructor", "Manage assignments", "The weights and checklist you set here decide how each submission is scored.")}
    <section class="grid-1-1"><div class="panel" id="a-form-host"></div><div class="panel"><h2>${icon("book")} Published</h2><div id="a-list"></div></div></section>`;
  edit(null);
  await load();
}

export async function students(view) {
  const rows = await api("/api/instructor/students");
  view.innerHTML = `${pageHeader("Instructor", "Students", `${rows.length} student${rows.length === 1 ? "" : "s"} in your class.`,
      `<a class="ghost" href="/api/instructor/gradebook.csv" download>${icon("download")} Gradebook (CSV)</a>`)}
    <section class="panel">${rows.length ? `<div class="field" style="max-width:360px"><label for="filter">Search</label><input id="filter" placeholder="Name, email or entry number" /></div>
      <div class="table-wrap"><table><thead><tr><th>Name</th><th>Entry no</th><th>Email</th><th class="num">Rank</th><th class="num">XP</th>
      <th class="num">Avg best</th><th class="num">Submissions</th><th class="num">Lab tasks</th><th>Last active</th></tr></thead><tbody id="st-body">
      ${rows.map((r) => `<tr data-q="${esc(`${r.name} ${r.email} ${r.entry_no || ""}`.toLowerCase())}"><td>${esc(r.name)}</td><td>${esc(r.entry_no || "")}</td><td>${esc(r.email)}</td>
        <td class="num">${r.rank ?? "–"}</td><td class="num">${r.xp}</td><td class="num">${r.avg_best ?? "–"}</td><td class="num">${r.submissions}</td>
        <td class="num">${r.labs_done}</td><td>${esc(fmtDate(r.last_active, true))}</td></tr>`).join("")}</tbody></table></div>`
      : emptyState("No students yet", "Students show up here after they create an account with your class join code.", "", "users")}</section>`;
  $("#filter")?.addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    view.querySelectorAll("#st-body tr").forEach((tr) => { tr.hidden = q && !tr.dataset.q.includes(q); });
  });
}

export { subsTable };
