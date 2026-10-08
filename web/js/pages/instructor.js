// Instructor workspace: the class at a glance (what needs attention first), students, and assignment management.
import {
  $, DEFAULT_WEIGHTS, DIMENSIONS, TRACKS, api, barChart, daysLeft, emptyState, esc, fmtDate, gradeBadge, hbars, icon, pageHeader, pct,
  relTime, statusPill, toast,
} from "../core.js";
import { subsTable } from "./student.js";

const LAB_NAMES = { frontend: "Frontend", database: "Databases", loadbalancer: "Load balancers", network: "Networks", docker: "Docker" };
const LOW = 50; // a best-try average under this is flagged as "below 50"

const repoShort = (url) => String(url || "").replace("https://github.com/", "");
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const nameList = (rows, max = 4) => {
  const names = rows.slice(0, max).map((r) => esc(r.name));
  return rows.length > max ? `${names.join(", ")} and ${rows.length - max} more` : names.join(", ");
};

/** Where a student stands, for the status column and the filters. */
function standing(r) {
  if (!r.submissions) return ["none", "Not started"];
  if (r.avg_best == null) return ["wait", "No grade yet"];
  if (r.avg_best < LOW) return ["risk", `Below ${LOW}`];
  return ["ok", "On track"];
}

function attentionItems(d, students) {
  const items = [];
  const shared = new Map();
  for (const s of d.recent) {
    if (s.shared_by > 1) shared.set(`${s.assignment_id}|${s.repo_url}`, s);
  }
  if (d.shared_repos) {
    const eg = [...shared.values()].slice(0, 2).map((s) => `<span class="mono">${esc(repoShort(s.repo_url))}</span> for ${esc(s.assignment_title || "an assignment")}`);
    items.push(["", `${plural(d.shared_repos, "repository", "repositories")} submitted by more than one student`,
      `${eg.join("; ")}. Group work, or copying?`, `<button class="ghost sm" type="button" data-show="shared">Show them</button>`]);
  }
  const failed = d.recent.filter((s) => s.status === "failed");
  if (failed.length) {
    items.push(["", `${plural(failed.length, "grading")} didn't finish`, `${nameList(failed.map((s) => ({ name: s.student })))} may need to submit again.`,
      `<button class="ghost sm" type="button" data-show="failed">Show them</button>`]);
  }
  const low = students.filter((r) => standing(r)[0] === "risk");
  if (low.length) {
    items.push(["", `${plural(low.length, "student")} averaging below ${LOW}`, `<span class="names">${nameList(low)}</span>`,
      `<a class="go" href="/instructor/students?show=risk">See students</a>`]);
  }
  const idle = students.filter((r) => !r.submissions);
  if (idle.length) {
    items.push(["amber", `${plural(idle.length, "student")} ${idle.length === 1 ? "hasn't" : "haven't"} submitted anything`, `<span class="names">${nameList(idle)}</span>`,
      `<a class="go" href="/instructor/students?show=none">See students</a>`]);
  }
  for (const a of d.assignments) {
    const left = daysLeft(a.due_at);
    if (left != null && left >= 0 && left <= 7 && a.completion < 0.6) {
      items.push(["amber", `${esc(a.title)} is due ${esc(relTime(a.due_at))}`, `Only ${pct(a.completion)} of the class has submitted so far.`,
        `<a class="go" href="/student/assignment/${a.id}">Open</a>`]);
    }
  }
  const weakest = Object.entries(d.dimension_avg).filter(([, v]) => v != null).sort((a, b) => a[1] - b[1])[0];
  if (weakest && weakest[1] < 6) {
    items.push(["ink", `${esc(DIMENSIONS[weakest[0]])} is the class's weakest area`, `It averages ${weakest[1].toFixed(1)} out of 10. A good topic for the next lab or lecture.`, ""]);
  }
  return items;
}

function latestTable(rows) {
  if (!rows.length) return emptyState("Nothing to show", "No submissions match this filter.", "", "upload");
  return `<div class="table-wrap"><table><thead><tr><th>Student</th><th>Assignment</th><th class="hide-sm">Repository</th><th class="hide-sm">Submitted</th><th>Status</th><th class="num">Score</th><th></th></tr></thead><tbody>
    ${rows.map((s) => `<tr class="${s.shared_by > 1 ? "flagged" : ""}"><td><b>${esc(s.student)}</b>${s.entry_no ? `<span class="sub-l">${esc(s.entry_no)}</span>` : ""}</td>
      <td>${esc(s.assignment_title || "Practice")}</td>
      <td class="repo hide-sm"><a href="${esc(s.repo_url)}" target="_blank" rel="noopener">${esc(repoShort(s.repo_url))}</a>
        ${s.shared_by > 1 ? `<span class="chip bad" title="The same repository was submitted by ${s.shared_by} students for this assignment">Shared by ${s.shared_by}</span>` : ""}</td>
      <td class="hide-sm">${esc(fmtDate(s.created_at, true))}</td><td>${statusPill(s.status)}</td>
      <td class="num">${gradeBadge(s.final_score, s.grade)}</td>
      <td class="actions">${s.status === "done" ? `<a class="ghost sm" href="/jobs/${esc(s.job_id)}">Feedback</a>` : ""}</td></tr>`).join("")}
    </tbody></table></div>`;
}

export async function dashboard(view) {
  const [d, students] = await Promise.all([api("/api/instructor/overview"), api("/api/instructor/students")]);
  const c = d.counts;
  const dist = Object.entries(d.grade_distribution);
  const active = students.filter((r) => r.submissions).length;
  const low = students.filter((r) => standing(r)[0] === "risk").length;
  const items = attentionItems(d, students);
  const FILTERS = [["all", "All", () => true], ["shared", "Shared repo", (s) => s.shared_by > 1], ["failed", "Failed", (s) => s.status === "failed"],
    ["running", "In progress", (s) => s.status === "queued" || s.status === "running"]];
  view.innerHTML = `
  ${pageHeader("", "Class overview", `${plural(c.students, "student")}, ${plural(c.assignments, "assignment")}. Start with the items marked in red.`,
    `<a class="btn" href="/instructor/assignments">${icon("plus")} New assignment</a>
     <a class="ghost" href="/api/instructor/gradebook.csv" download>${icon("download")} Export gradebook</a>`)}
  <section class="ledger" aria-label="Class numbers">
    <div><span>Students active</span><b>${active}<small>of ${c.students}</small></b></div>
    <div><span>Submissions</span><b>${c.submissions}<small>${c.graded} graded${c.active ? `, ${c.active} running` : ""}</small></b></div>
    <div><span>Class average</span><b>${d.class_avg ?? "–"}<small>best try</small></b></div>
    <div class="${low ? "flag" : ""}"><span>Averaging below ${LOW}</span><b>${low}</b></div>
    <div class="${d.shared_repos ? "flag" : ""}"><span>Shared repositories</span><b>${d.shared_repos}</b></div>
  </section>
  <section class="attn-grid">
    <div class="panel attn"><div class="panel-h"><h2>${icon("alert")} Needs your attention</h2><span class="hint">${items.length ? plural(items.length, "item") : ""}</span></div>
      ${items.length ? `<ul class="attn-list">${items.map(([tone, title, detail, go]) => `<li><span class="mk ${tone}" aria-hidden="true"></span>
        <div><b>${title}</b><p>${detail}</p></div>${go}</li>`).join("")}</ul>`
        : `<p class="attn-ok">${icon("checkCircle")} Nothing needs your attention right now.</p>`}</div>
    <div class="panel"><div class="panel-h"><h2>Grade distribution</h2><span class="hint">best try per student and assignment</span></div>
      ${dist.some(([, v]) => v) ? barChart(dist, { colorFn: (g) => (g.startsWith("A") ? "g-a" : g.startsWith("B") ? "g-b" : g.startsWith("C") ? "g-c" : "g-f") })
        : emptyState("No grades yet", "The distribution appears as students submit.", "", "chart")}</div>
  </section>
  <section class="panel"><div class="panel-h"><h2>Assignments</h2><a href="/instructor/assignments">Manage</a></div>
    ${d.assignments.length ? `<div class="table-wrap"><table><thead><tr><th>Assignment</th><th>Due</th><th>Submitted</th>
      <th class="num">Average</th><th class="num">Top</th><th class="num hide-sm">Attempts</th></tr></thead><tbody>
      ${d.assignments.map((a) => {
        const left = daysLeft(a.due_at);
        return `<tr><td><a href="/student/assignment/${a.id}"><b>${esc(a.title)}</b></a><span class="sub-l">${esc(TRACKS[a.track] || a.track)}</span></td>
        <td>${a.due_at ? `${esc(fmtDate(a.due_at))}<span class="sub-l">${left < 0 ? "closed" : esc(relTime(a.due_at))}</span>` : `<span class="muted">No deadline</span>`}</td>
        <td><div class="compl">${`<div class="bar"><span style="width:${pct(a.completion)}"></span></div>`}<span class="t">${a.students_submitted} of ${c.students}</span></div></td>
        <td class="num">${a.avg_best != null ? gradeBadge(a.avg_best, "") : "–"}</td><td class="num">${a.max_best ?? "–"}</td>
        <td class="num hide-sm">${a.submissions}</td></tr>`;
      }).join("")}
      </tbody></table></div>` : emptyState("No assignments yet", "Publish the first one to start collecting submissions.", `<a class="btn" href="/instructor/assignments">New assignment</a>`, "book")}</section>
  <section class="grid-1-1">
    <div class="panel"><div class="panel-h"><h2>Average by area</h2><span class="hint">out of 10, latest 500 gradings</span></div>
      ${hbars(Object.entries(d.dimension_avg).map(([k, v]) => [DIMENSIONS[k] || k, v]), { max: 10, fmt: (v) => v.toFixed(1) })}</div>
    <div class="panel"><div class="panel-h"><h2>Lab activity</h2><a href="/labs">Labs</a></div>
      ${d.labs.length ? `<table><thead><tr><th>Lab</th><th class="num">Tasks done</th><th class="num">Students</th></tr></thead><tbody>
        ${d.labs.map((l) => `<tr><td>${esc(LAB_NAMES[l.lab] || l.lab)}</td><td class="num">${l.n}</td><td class="num">${l.students}</td></tr>`).join("")}</tbody></table>`
        : emptyState("No lab work yet", "Tasks finished in the labs show up here.", "", "flask")}</div>
  </section>
  <section class="panel" id="latest"><div class="panel-h"><h2>Latest submissions</h2>
      <div class="seg" role="group" aria-label="Filter submissions">${FILTERS.map(([k, label, fn], i) =>
        `<button type="button" data-f="${k}" aria-pressed="${i === 0}">${label}<span class="n">${d.recent.filter(fn).length}</span></button>`).join("")}</div></div>
    <div id="latest-rows">${latestTable(d.recent)}</div></section>`;
  const setFilter = (k) => {
    const [, , fn] = FILTERS.find(([key]) => key === k) || FILTERS[0];
    view.querySelectorAll("[data-f]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.f === k)));
    $("#latest-rows").innerHTML = latestTable(d.recent.filter(fn));
  };
  view.querySelectorAll("[data-f]").forEach((b) => b.addEventListener("click", () => setFilter(b.dataset.f)));
  view.querySelectorAll("[data-show]").forEach((b) => b.addEventListener("click", () => {
    setFilter(b.dataset.show);
    $("#latest").scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  if (c.active) {
    const t = setTimeout(() => window.__refresh(), 6000);
    return () => clearTimeout(t);
  }
  return null;
}

// ------------------------------------------------------------------------------------ assignments
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
    <div class="field"><label for="a-notes">What will be checked <span class="muted">(separate items with ; and students see a checklist)</span></label>
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

export async function assignments(view, _p, query) {
  let rows = [];
  let editing = null;
  const load = async () => {
    rows = await api("/api/assignments");
    $("#a-list").innerHTML = rows.length ? `<div class="table-wrap"><table><thead><tr><th>Title</th><th>Due</th><th class="num">Students</th><th></th></tr></thead><tbody>
      ${rows.map((a) => `<tr class="${editing === a.id ? "flagged" : ""}"><td><a href="/student/assignment/${a.id}"><b>${esc(a.title)}</b></a><span class="sub-l">${esc(TRACKS[a.track] || a.track)}</span></td>
        <td>${a.due_at ? esc(fmtDate(a.due_at, true)) : `<span class="muted">No deadline</span>`}</td><td class="num">${a.class_stats.students}</td>
        <td class="actions"><button class="ghost sm" data-edit="${a.id}" type="button">Edit</button>
          <button class="ghost sm danger" data-del="${a.id}" type="button">Delete</button></td></tr>`).join("")}</tbody></table></div>`
      : emptyState("No assignments yet", "Publish the first one with the form.", "", "book");
    $("#a-list").querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => {
      edit(rows.find((r) => String(r.id) === b.dataset.edit));
    }));
    $("#a-list").querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      const a = rows.find((r) => String(r.id) === b.dataset.del);
      if (!confirm(`Delete "${a.title}" and all of its submissions? This can't be undone.`)) return;
      await api(`/api/assignments/${a.id}`, { method: "DELETE" });
      toast("Assignment deleted");
      if (editing === a.id) edit(null);
      load();
    }));
  };
  const edit = (a = null) => {
    editing = a?.id ?? null;
    $("#a-form-host").innerHTML = `<h2>${icon(a ? "edit" : "plus")} ${a ? `Edit ${esc(a.title)}` : "New assignment"}</h2>${assignmentForm(a)}`;
    $("#a-cancel")?.addEventListener("click", () => { edit(null); load(); });
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
        toast(id ? "Changes saved" : "Assignment published", "ok");
        edit(null);
        load();
      } catch (err) { $("#a-err").textContent = err.message; }
    });
    if (a) $("#a-form-host").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  view.innerHTML = `${pageHeader(`<a href="/instructor/dashboard">Overview</a>`, "Assignments", "The weights and checklist you set here decide how every submission is scored.")}
    <section class="grid-1-1"><div class="panel" id="a-form-host"></div><div class="panel"><h2>${icon("book")} Published</h2><div id="a-list"></div></div></section>`;
  edit(null);
  await load();
  const want = query?.get("edit");
  const target = want && rows.find((r) => String(r.id) === want);
  if (target) { edit(target); load(); }
}

// ------------------------------------------------------------------------------------ students
const COLS = [
  ["name", "Name", (r) => r.name.toLowerCase(), ""],
  ["email", "Email", (r) => r.email.toLowerCase(), "hide-sm"],
  ["status", "Status", (r) => ({ risk: 0, none: 1, wait: 2, ok: 3 })[standing(r)[0]], ""],
  ["avg", "Average best", (r) => r.avg_best ?? -1, "num"],
  ["subs", "Submissions", (r) => r.submissions, "num hide-sm"],
  ["labs", "Lab tasks", (r) => r.labs_done, "num hide-sm"],
  ["xp", "XP", (r) => r.xp, "num"],
  ["active", "Last active", (r) => r.last_active || "", "hide-sm"],
];

export async function students(view, _p, query) {
  const rows = await api("/api/instructor/students");
  const groups = [["all", "All"], ["risk", `Below ${LOW}`], ["none", "Not started"], ["ok", "On track"]];
  const count = (k) => (k === "all" ? rows.length : rows.filter((r) => standing(r)[0] === k).length);
  let show = groups.some(([k]) => k === query?.get("show")) ? query.get("show") : "all";
  let sort = { key: "status", dir: 1 };
  let q = "";
  view.innerHTML = `${pageHeader(`<a href="/instructor/dashboard">Overview</a>`, "Students", `${plural(rows.length, "student")} in your class. Sorted so the ones who need help come first.`,
      `<a class="ghost" href="/api/instructor/gradebook.csv" download>${icon("download")} Export gradebook</a>`)}
    <section class="panel">${rows.length ? `<div class="toolbar">
        <div class="seg" role="group" aria-label="Filter students">${groups.map(([k, label]) =>
          `<button type="button" data-g="${k}" aria-pressed="${k === show}">${label}<span class="n">${count(k)}</span></button>`).join("")}</div>
        <input id="filter" type="search" placeholder="Search name, email or entry number" aria-label="Search students" /></div>
      <div class="table-wrap"><table><thead><tr>${COLS.map(([k, label, , cls]) =>
        `<th class="sort ${cls}" data-k="${k}" tabindex="0">${label}</th>`).join("")}</tr></thead><tbody id="st-body"></tbody></table></div>`
      : emptyState("No students yet", "Students appear here after they create an account with your class join code.", "", "users")}</section>`;
  if (!rows.length) return;
  const paint = () => {
    const [, , val] = COLS.find(([k]) => k === sort.key);
    const list = rows.filter((r) => (show === "all" || standing(r)[0] === show)
      && (!q || `${r.name} ${r.email} ${r.entry_no || ""}`.toLowerCase().includes(q)))
      .sort((a, b) => (val(a) < val(b) ? -1 : val(a) > val(b) ? 1 : 0) * sort.dir || a.name.localeCompare(b.name));
    view.querySelectorAll("th.sort").forEach((th) => {
      if (th.dataset.k === sort.key) th.setAttribute("aria-sort", sort.dir > 0 ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
    });
    $("#st-body").innerHTML = list.length ? list.map((r) => {
      const [cls, label] = standing(r);
      return `<tr class="${cls === "risk" ? "flagged" : ""}"><td><b>${esc(r.name)}</b>${r.entry_no ? `<span class="sub-l">${esc(r.entry_no)}</span>` : ""}</td>
        <td class="hide-sm">${esc(r.email)}</td><td><span class="status-tag ${cls}">${label}</span></td>
        <td class="num">${r.avg_best != null ? gradeBadge(r.avg_best, "") : "–"}</td><td class="num hide-sm">${r.submissions}</td>
        <td class="num hide-sm">${r.labs_done}</td><td class="num">${r.xp}</td>
        <td class="hide-sm">${r.last_active ? esc(relTime(r.last_active)) : `<span class="muted">Never</span>`}</td></tr>`;
    }).join("") : `<tr><td colspan="${COLS.length}">${emptyState("No students match", "Try another filter or search.", "", "users")}</td></tr>`;
  };
  view.querySelectorAll("[data-g]").forEach((b) => b.addEventListener("click", () => {
    show = b.dataset.g;
    view.querySelectorAll("[data-g]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    paint();
  }));
  view.querySelectorAll("th.sort").forEach((th) => {
    const go = () => { sort = { key: th.dataset.k, dir: sort.key === th.dataset.k ? -sort.dir : 1 }; paint(); };
    th.addEventListener("click", go);
    th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
  $("#filter").addEventListener("input", (e) => { q = e.target.value.trim().toLowerCase(); paint(); });
  paint();
}

export { subsTable };
