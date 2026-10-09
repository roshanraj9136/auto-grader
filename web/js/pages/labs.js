// Hands-on labs: Frontend, Databases, Load balancers, Networks, Containers.
import { $, LAB_ICON, api, emptyState, esc, fmtMs, icon, pageHeader, progressBar, state, toast } from "../core.js";

let catalog = null;

async function loadCatalog() {
  catalog = await api("/api/labs");
  return catalog;
}

function isDone(lab, task) {
  return (catalog?.progress?.[lab] || []).includes(task);
}

function tasksPanel(lab) {
  const l = catalog.labs.find((x) => x.id === lab);
  const done = (catalog.progress[lab] || []).length;
  return `<div class="panel tasks" id="tasks-panel"><div class="panel-h"><h2>${icon("checkCircle")} Your tasks</h2><span class="hint">${done} of ${l.tasks.length} done</span></div>
    ${progressBar(done, l.tasks.length, "Lab progress")}
    <ul class="task-list">${l.tasks.map((t) => `<li class="${isDone(lab, t.id) ? "done" : ""}" data-task="${t.id}">
      <span class="tick" aria-hidden="true">${icon("check")}</span><span class="grow">${esc(t.title)}</span>
      ${t.xp ? `<span class="chip track" title="Checked by the server">+${t.xp} XP</span>` : ""}</li>`).join("")}</ul>
    ${state.user ? "" : `<p class="hint" style="margin-top:12px"><a href="/login?next=${encodeURIComponent(location.pathname)}">Sign in</a> to save your progress and earn XP.</p>`}</div>`;
}

function refreshTasks(lab) {
  const host = $("#tasks-panel");
  if (host) host.outerHTML = tasksPanel(lab);
}

async function complete(lab, task, { serverRecorded = false } = {}) {
  if (isDone(lab, task)) return;
  if (!state.user) { toast("Task passed! Sign in to save it.", "ok"); return; }
  const xp = catalog.labs.find((l) => l.id === lab)?.tasks.find((t) => t.id === task)?.xp || 0;
  try {
    if (!serverRecorded) await api("/api/labs/progress", { method: "POST", body: { lab, task } });
    catalog.progress[lab] = [...(catalog.progress[lab] || []), task];
    refreshTasks(lab);
    toast(xp ? `Task complete! +${xp} XP` : "Task complete!", "ok");
  } catch (e) { toast(e.message, "error"); }
}

function header(l, extra = "") {
  const track = String(l.track || "");
  return pageHeader(`<a href="/labs">Labs</a> / ${esc(track.charAt(0).toUpperCase() + track.slice(1))}`, esc(l.title), esc(l.summary), extra);
}

const DIM_CLASS = { code_quality: "a-code", architecture: "a-arch", security: "a-sec", testing: "a-test", devops: "a-ops" };

/** "Start here": the next tasks, weakest marked area first. The server picks them from the student's own grades. */
function planPanel(rec) {
  if (!rec?.length) return "";
  const measured = rec.some((t) => t.reason !== "Next up");
  return `<section class="panel next-up"><div class="panel-h"><h2>${icon("target")} Start here</h2>
      <span class="hint">${measured ? "Picked from your lowest marks" : "A good order to begin in"}</span></div>
    <div class="mini-plan">${rec.map((t) => `<a class="plan-row ${DIM_CLASS[t.dimension] || "a-code"}" href="/labs/${esc(t.lab)}">
      ${icon(LAB_ICON[t.lab] || "flask")}<div><b>${esc(t.title)}</b><span>${esc(t.lab_title)}</span></div>
      <span class="why">${esc(t.reason)}</span></a>`).join("")}</div></section>`;
}

export async function index(view) {
  await loadCatalog();
  const total = catalog.total_tasks, doneN = catalog.completed;
  view.innerHTML = `${pageHeader("", "Labs", "Practise each part of the stack hands-on: frontend, databases, load balancers, networks and Docker. Everything runs in your browser.",
      state.user ? `<div class="best-badge"><span class="stat-ico">${icon("flask")}</span><div><span>Your progress</span><b>${doneN} of ${total} tasks</b></div></div>` : "")}
    ${planPanel(catalog.recommended)}
    <section class="cards labs">${catalog.labs.map((l) => {
      const d = (catalog.progress[l.id] || []).length;
      return `<article class="card lab-card"><div class="lab-top"><span class="lab-ico">${icon(LAB_ICON[l.id] || "flask")}</span>
          <span class="lab-n">${d} of ${l.tasks.length} done</span></div>
        <h2><a href="/labs/${l.id}">${esc(l.title)}</a></h2><p>${esc(l.summary)}</p>
        <ul class="mini-tasks">${l.tasks.map((t) => `<li class="${isDone(l.id, t.id) ? "done" : ""}">${icon(isDone(l.id, t.id) ? "checkCircle" : "target")} ${esc(t.title)}</li>`).join("")}</ul>
        <div class="card-foot">${progressBar(d, l.tasks.length, `${l.title} progress`)}<a class="${d ? "ghost" : "btn"} sm" href="/labs/${l.id}">${d === l.tasks.length ? "Review" : d ? "Continue" : "Start"}</a></div></article>`;
    }).join("")}</section>`;
}

export async function lab(view, { lab: id }) {
  await loadCatalog();
  const l = catalog.labs.find((x) => x.id === id);
  if (!l) { view.innerHTML = emptyState("Unknown lab", "", `<a class="btn" href="/labs">All labs</a>`); return null; }
  const impl = { frontend: frontendLab, database: databaseLab, loadbalancer: lbLab, network: networkLab, docker: dockerLab }[id];
  return impl(view, l);
}

// ======================================================================== Frontend lab
const FE_STARTER = {
  html: `<main>
  <h1>Hello, full-stack!</h1>
  <p>Edit the HTML, CSS and JS panes. The preview updates as you type.</p>

  <div class="row">
    <div class="card">Frontend</div>
    <div class="card">API</div>
    <div class="card">Database</div>
  </div>

  <p>Clicks: <span id="count">0</span></p>
  <button id="inc">Click me</button>

  <img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='60' height='60'%3E%3Ccircle cx='30' cy='30' r='26' fill='%237c83ff'/%3E%3C/svg%3E">
  <input id="name" placeholder="Your name">
</main>`,
  css: `body { font-family: system-ui, sans-serif; margin: 24px; color: #1f2937; }
.card { padding: 12px 16px; border-radius: 10px; background: #eef2ff; margin: 6px; }
/* Task: make .row a horizontal flexbox */
button { padding: 8px 14px; border-radius: 8px; border: 0; background: #4f46e5; color: #fff; }`,
  js: `// Task: make #inc increment the number shown in #count
const btn = document.querySelector('#inc');
console.log('script loaded', btn);`,
};

function frontendLab(view, l) {
  const saved = JSON.parse(localStorage.getItem("ag-fe-lab") || "null") || FE_STARTER;
  view.innerHTML = `${header(l, `<button class="ghost" id="fe-reset" type="button">${icon("refresh")} Reset code</button>
    <button class="btn" id="fe-check" type="button">${icon("checkCircle")} Check my work</button>`)}
  <section class="fe-grid">
    <div class="panel editor">
      <div class="tabs" role="tablist">${["html", "css", "js"].map((t, i) =>
        `<button role="tab" type="button" class="tab${i === 0 ? " active" : ""}" data-tab="${t}" aria-selected="${i === 0}">${t.toUpperCase()}</button>`).join("")}</div>
      ${["html", "css", "js"].map((t, i) => `<textarea class="code" id="fe-${t}" spellcheck="false" aria-label="${t.toUpperCase()} editor"${i ? " hidden" : ""}>${esc(saved[t])}</textarea>`).join("")}
      <div class="console" id="fe-console" aria-live="polite" aria-label="Console output"></div>
    </div>
    <div class="panel preview-frame"><div class="panel-h"><h2>${icon("globe")} Live preview</h2><span class="hint">updates as you type</span></div>
      <iframe id="fe-frame" src="/sandbox.html" sandbox="allow-scripts" title="Live preview of your page"></iframe></div>
  </section>
  <section class="grid-2-1"><div class="panel"><h2>${icon("bulb")} Learn the concepts</h2>
    <ul class="concepts"><li><b>DOM</b>: the browser turns HTML into a tree of nodes; JS reads and changes it (<code>querySelector</code>, <code>textContent</code>).</li>
    <li><b>Events</b>: <code>addEventListener('click', …)</code> runs code when the user interacts.</li>
    <li><b>Flexbox</b>: <code>display:flex</code> lays children out in a row; <code>gap</code>, <code>justify-content</code>, <code>align-items</code> control spacing.</li>
    <li><b>Accessibility</b>: images need <code>alt</code> text and inputs need a <code>&lt;label for&gt;</code> so screen readers can describe them.</li>
    <li><b>Security</b>: the preview runs in an opaque-origin sandbox; it cannot read this site's cookies (same-origin policy).</li></ul></div>
    ${tasksPanel("frontend")}</section>`;
  const frame = $("#fe-frame");
  const consoleEl = $("#fe-console");
  const code = () => ({ html: $("#fe-html").value, css: $("#fe-css").value, js: $("#fe-js").value });
  let ready = false;
  let timer = null;
  const pending = new Map();
  const renderPreview = () => {
    localStorage.setItem("ag-fe-lab", JSON.stringify(code()));
    consoleEl.innerHTML = "";
    if (ready) frame.contentWindow.postMessage({ type: "render", ...code() }, "*");
  };
  const onMsg = (e) => {
    if (e.source !== frame.contentWindow || typeof e.data !== "object" || !e.data) return;
    const m = e.data;
    if (m.type === "ready") { if (!ready) { ready = true; renderPreview(); } return; }
    if (m.type === "log") {
      const line = document.createElement("div");
      line.className = `log ${m.level === "error" ? "err" : ""}`;
      line.textContent = `${m.level === "error" ? "✖" : "›"} ${String(m.text).slice(0, 500)}`;
      consoleEl.appendChild(line);
      consoleEl.scrollTop = consoleEl.scrollHeight;
    }
    if (m.type === "result" && pending.has(m.task)) { pending.get(m.task)(m); pending.delete(m.task); }
  };
  window.addEventListener("message", onMsg);
  const check = (task) => new Promise((resolve) => {
    pending.set(task, resolve);
    frame.contentWindow.postMessage({ type: "check", task }, "*");
    setTimeout(() => { if (pending.has(task)) { pending.delete(task); resolve({ ok: false, msg: "preview did not answer" }); } }, 1500);
  });
  view.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
    view.querySelectorAll(".tab").forEach((x) => { x.classList.toggle("active", x === b); x.setAttribute("aria-selected", String(x === b)); });
    ["html", "css", "js"].forEach((t) => { $(`#fe-${t}`).hidden = t !== b.dataset.tab; });
    $(`#fe-${b.dataset.tab}`).focus();
  }));
  view.querySelectorAll("textarea.code").forEach((t) => {
    t.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(renderPreview, 350); });
    t.addEventListener("keydown", (e) => {
      if (e.key === "Tab" && !e.shiftKey && !e.altKey) { // indent instead of leaving the editor (Esc then Tab leaves)
        if (t.dataset.esc === "1") { t.dataset.esc = ""; return; }
        e.preventDefault();
        const s = t.selectionStart;
        t.setRangeText("  ", s, t.selectionEnd, "end");
        t.dispatchEvent(new Event("input"));
      } else if (e.key === "Escape") t.dataset.esc = "1";
    });
  });
  $("#fe-reset").addEventListener("click", () => {
    if (!confirm("Reset the editors to the starter code?")) return;
    for (const t of ["html", "css", "js"]) $(`#fe-${t}`).value = FE_STARTER[t];
    renderPreview();
  });
  $("#fe-check").addEventListener("click", async () => {
    renderPreview();
    await new Promise((r) => setTimeout(r, 250));
    const results = [];
    for (const t of catalog.labs.find((x) => x.id === "frontend").tasks) {
      const r = await check(t.id);
      results.push([t, r]);
      if (r.ok) await complete("frontend", t.id);
    }
    const passed = results.filter(([, r]) => r.ok).length;
    toast(`${passed}/${results.length} checks passed`, passed === results.length ? "ok" : "info");
    results.forEach(([t, r]) => {
      const li = view.querySelector(`#tasks-panel li[data-task="${t.id}"]`);
      if (li && !r.ok) li.title = r.msg;
      if (li && !r.ok) li.classList.add("fail");
    });
    const fails = results.filter(([, r]) => !r.ok).map(([t, r]) => `${t.title}: ${r.msg}`);
    if (fails.length) {
      const line = document.createElement("div");
      line.className = "log err";
      line.textContent = "Checks: " + fails.join(" | ");
      consoleEl.appendChild(line);
    }
  });
  return () => { window.removeEventListener("message", onMsg); clearTimeout(timer); };
}

// ======================================================================== Database lab
const SQL_SAMPLES = {
  select: "SELECT name, year\nFROM students\nWHERE branch = 'CSE' AND year = 3\nORDER BY name;",
  join: "SELECT s.name\nFROM students s\nJOIN enrollments e ON e.student_id = s.id\nJOIN courses c ON c.id = e.course_id\nWHERE c.code = 'CSL100'\nORDER BY s.name;",
  aggregate: "SELECT branch, COUNT(*) AS n\nFROM students\nGROUP BY branch\nORDER BY n DESC;",
  index: "EXPLAIN QUERY PLAN\nSELECT * FROM enrollments WHERE student_id = 42;",
};

async function databaseLab(view, l) {
  const meta = await api("/api/lab/sql/schema");
  view.innerHTML = `${header(l)}
  <section class="grid-2-1">
    <div class="panel">
      <div class="panel-h"><h2>${icon("database")} Query editor</h2><span class="hint">Ctrl + Enter to run</span></div>
      <div class="field"><label for="sql-task">Task to check <span class="hint">(optional)</span></label>
        <select id="sql-task"><option value="">Free play: no check</option>${Object.entries(meta.tasks).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></div>
      <textarea id="sql" class="code" rows="8" spellcheck="false" aria-label="SQL query">SELECT * FROM courses;</textarea>
      <div class="row-btns"><button class="btn" id="sql-run" type="button">Run query</button>
        <label class="check"><input type="checkbox" id="sql-index" /> Index on <code>enrollments(student_id)</code></label>
        <button class="ghost sm" id="sql-hint" type="button">Show a solution</button></div>
      <div id="sql-check" role="status" aria-live="polite"></div>
      <div id="sql-out"></div>
    </div>
    <div>
      <div class="panel"><h2>${icon("layers")} Tables</h2><pre class="schema">${esc(meta.schema)}</pre>
        <p class="hint">240 students · 10 courses · ~1,100 enrollments. Every query runs on a fresh, read-only, in-memory copy, with a 0.5 s limit.</p></div>
      ${tasksPanel("database")}
      <div class="panel"><h2>${icon("bulb")} Learn the concepts</h2><ul class="concepts">
        <li><b>JOIN</b> combines rows from tables using keys (<code>enrollments.student_id → students.id</code>).</li>
        <li><b>GROUP BY</b> collapses rows into groups; aggregates like <code>COUNT</code>, <code>AVG</code> summarise them.</li>
        <li><b>Index</b>: a B-tree that turns a full table <i>SCAN</i> into a <i>SEARCH</i>: O(log n) instead of O(n).</li>
        <li><b>Parameterised queries</b> in your apps prevent SQL injection: never build SQL with string concatenation.</li></ul></div>
    </div>
  </section>`;
  const run = async () => {
    const task = $("#sql-task").value || null;
    $("#sql-run").disabled = true;
    $("#sql-check").innerHTML = "";
    try {
      const r = await api("/api/lab/sql", { method: "POST", body: { query: $("#sql").value, with_index: $("#sql-index").checked, task } });
      $("#sql-out").innerHTML = `<p class="hint">${r.rows.length}${r.truncated ? "+" : ""} row(s) in ${r.ms} ms</p>
        ${r.columns.length ? `<div class="table-wrap result-table"><table><thead><tr>${r.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
        <tbody>${r.rows.map((row) => `<tr>${row.map((v) => `<td>${v == null ? '<span class="hint">NULL</span>' : esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : ""}
        ${r.plan.length ? `<h3>Query plan</h3><ul class="plan">${r.plan.map((p) => `<li class="${/SEARCH|INDEX/.test(p) ? "good" : /SCAN/.test(p) ? "warn" : ""}">${esc(p)}</li>`).join("")}</ul>` : ""}`;
      if (r.check) {
        $("#sql-check").innerHTML = `<p class="check-msg ${r.check.passed ? "ok" : "bad"}">${icon(r.check.passed ? "checkCircle" : "alert")} ${esc(r.check.message)}</p>`;
        if (r.check.passed) await complete("database", task, { serverRecorded: true }); // the server already recorded it
      }
    } catch (e) {
      $("#sql-out").innerHTML = `<p class="error">${icon("alert")} ${esc(e.message)}</p>`;
    } finally { $("#sql-run").disabled = false; }
  };
  $("#sql-run").addEventListener("click", run);
  $("#sql").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); } });
  $("#sql-task").addEventListener("change", () => {
    const t = $("#sql-task").value;
    if (t === "index") $("#sql-index").checked = false;
    if (t) $("#sql").value = `-- ${meta.tasks[t]}\n`;
    $("#sql").focus();
  });
  $("#sql-hint").addEventListener("click", () => {
    const t = $("#sql-task").value || "join";
    $("#sql-task").value = t;
    $("#sql").value = SQL_SAMPLES[t];
    if (t === "index") $("#sql-index").checked = true;
  });
  return null;
}

// ======================================================================== Load-balancer lab
const LB_COLORS = ["#2140d9", "#0e8fb0", "#16794a", "#c27410", "#c4302b", "#6d4fc2", "#0f766e", "#8a6d00"];

function lbLab(view, l) {
  const used = new Set();
  view.innerHTML = `${header(l)}
  <div id="lb-banner"></div>
  <section class="grid-2-1">
    <div class="panel">
      <div class="panel-h"><h2>${icon("zap")} Send traffic</h2></div>
      <div class="grid3">
        <div class="field"><label for="lb-algo">Algorithm (Nginx upstream)</label><select id="lb-algo">
          <option value="rr">Round-robin</option><option value="least">Least connections</option>
          <option value="hash">Sticky: hash of session cookie</option><option value="direct">No load balancer (direct)</option></select></div>
        <div class="field"><label for="lb-n">Requests</label><input id="lb-n" type="number" min="5" max="200" value="30" /></div>
        <div class="field"><label for="lb-c">Concurrency</label><input id="lb-c" type="number" min="1" max="20" value="6" /></div>
      </div>
      <label class="check"><input type="checkbox" id="lb-slow" /> Make 1 in 4 requests slow (0.6 s): shows why least-connections exists</label>
      <div class="row-btns"><button class="btn" id="lb-go" type="button">Fire requests</button><span id="lb-status" class="hint" role="status"></span></div>
      <h3>Responses in arrival order</h3><div id="lb-strip" class="strip" aria-label="Which replica served each request"></div>
      <h3>Distribution</h3><div id="lb-dist"></div>
      <div id="lb-lat" class="hint"></div>
    </div>
    <div>${tasksPanel("loadbalancer")}
      <div class="panel"><h2>${icon("bulb")} How it works</h2><ul class="concepts">
        <li><b>Round-robin</b>: each new request goes to the next replica in turn. Even spread, but blind to load.</li>
        <li><b>Least connections</b>: send to the replica with the fewest in-flight requests. Better when some requests are slow.</li>
        <li><b>Sticky / hash</b>: the same client (session cookie) always lands on the same replica, needed when state lives in memory (here: live grading streams).</li>
        <li><b>Stateless replicas</b>: sessions and grades live in PostgreSQL, so any replica can serve any page.</li>
        <li>Scale it yourself: <code>docker compose up -d --scale api=5</code>, then <code>docker compose restart nginx</code>.</li></ul></div></div>
  </section>`;
  let running = false;
  $("#lb-go").addEventListener("click", async () => {
    if (running) return;
    running = true;
    $("#lb-go").disabled = true;
    const algo = $("#lb-algo").value;
    const n = Math.max(5, Math.min(200, +$("#lb-n").value || 30));
    const conc = Math.max(1, Math.min(20, +$("#lb-c").value || 6));
    const slow = $("#lb-slow").checked;
    const url = algo === "direct" ? "/api/lab/whoami" : `/lb/${algo}/whoami`;
    const results = [];
    const counts = {};
    const colors = {};
    const strip = $("#lb-strip");
    strip.innerHTML = "";
    let next = 0;
    let behindProxy = false;
    const worker = async () => {
      while (next < n) {
        const i = next++;
        const delay = slow && i % 4 === 0 ? 600 : 0;
        const t0 = performance.now();
        try {
          const r = await api(`${url}?delay_ms=${delay}&i=${i}&t=${Date.now()}`);
          const ms = performance.now() - t0;
          behindProxy ||= r.behind_proxy;
          counts[r.instance] = (counts[r.instance] || 0) + 1;
          colors[r.instance] ??= LB_COLORS[Object.keys(colors).length % LB_COLORS.length];
          results.push({ ...r, ms });
          const b = document.createElement("span");
          b.className = "blk";
          b.style.background = colors[r.instance];
          b.title = `#${i} → ${r.instance} in ${Math.round(ms)} ms${delay ? " (slow)" : ""}`;
          b.textContent = Object.keys(colors).indexOf(r.instance) + 1;
          strip.appendChild(b);
          $("#lb-status").textContent = `${results.length}/${n}`;
        } catch (e) { $("#lb-status").textContent = e.message; }
      }
    };
    await Promise.all(Array.from({ length: conc }, worker));
    const entries = Object.entries(counts);
    $("#lb-dist").innerHTML = entries.map(([inst, c]) => `<div class="hb"><span class="hb-l"><i class="sw" style="background:${colors[inst]}"></i>${esc(inst)}</span>
      <div class="hb-t"><span style="width:${(c / results.length) * 100}%;background:${colors[inst]}"></span></div><span class="hb-v">${c} (${Math.round((c / results.length) * 100)}%)</span></div>`).join("");
    const lat = results.map((r) => r.ms).sort((a, b) => a - b);
    const q = (p) => lat[Math.min(lat.length - 1, Math.floor(p * lat.length))];
    $("#lb-lat").textContent = lat.length ? `${results.length} responses from ${entries.length} server${entries.length > 1 ? "s" : ""}. Typical response ${fmtMs(q(0.5))}, slowest ${fmtMs(lat[lat.length - 1])}.` : "";
    $("#lb-banner").innerHTML = entries.length > 1 ? "" : `<div class="banner">${icon("bulb")}<span>Every request was answered by the same server, because this deployment runs one copy of the app.
      To see traffic spread across 3 servers, run the project locally with <code>docker compose up</code> and open <code>http://localhost:8080</code>.</span></div>`;
    if (results.length >= 30) await complete("loadbalancer", "burst");
    if (entries.length >= 2) await complete("loadbalancer", "replicas");
    used.add(algo);
    if (used.has("rr") && used.has("hash") && behindProxy) await complete("loadbalancer", "sticky");
    running = false;
    $("#lb-go").disabled = false;
  });
  return () => { running = false; };
}

// ======================================================================== Network lab
function networkLab(view, l) {
  view.innerHTML = `${header(l)}
  <section class="grid-1-1">
    <div class="panel"><div class="panel-h"><h2>${icon("clock")} Round-trip time</h2><button class="btn sm" id="rtt-go" type="button">Measure 20 requests</button></div>
      <div id="rtt-out"><p class="hint">Sends 20 sequential requests and measures each round trip with <code>performance.now()</code>.</p></div></div>
    <div class="panel"><div class="panel-h"><h2>${icon("network")} Request path</h2><button class="btn sm" id="path-go" type="button">Trace my request</button></div>
      <div id="path-out"><p class="hint">Shows the hops your request takes and the headers the backend actually receives.</p></div></div>
  </section>
  <section class="grid-2-1">
    <div class="panel"><div class="panel-h"><h2>${icon("activity")} Timing breakdown</h2><button class="btn sm" id="tim-go" type="button">Break down a request</button></div>
      <div id="tim-out"><p class="hint">Uses the Resource Timing API and the backend's <code>Server-Timing</code> header.</p></div></div>
    <div>${tasksPanel("network")}
      <div class="panel"><h2>${icon("bulb")} Learn the concepts</h2><ul class="concepts">
        <li><b>RTT</b>: time for a request to reach the server and the response to come back. <b>Jitter</b> = variation between RTTs.</li>
        <li><b>Reverse proxy</b>: Nginx terminates your connection and opens its own to a replica; <code>X-Forwarded-For</code> keeps your IP.</li>
        <li><b>Keep-alive</b>: reused TCP connections skip DNS + TCP handshake, which is why those bars are often 0.</li>
        <li><b>TTFB</b>: time to first byte = network + server processing. <code>Server-Timing</code> tells you the server's share.</li></ul></div></div>
  </section>`;
  $("#rtt-go").addEventListener("click", async () => {
    $("#rtt-go").disabled = true;
    const times = [];
    for (let i = 0; i < 20; i++) {
      const t0 = performance.now();
      await api(`/api/lab/whoami?rtt=${i}&t=${Date.now()}`);
      times.push(performance.now() - t0);
      $("#rtt-out").innerHTML = `<p class="hint">${i + 1}/20…</p>`;
    }
    const s = [...times].sort((a, b) => a - b);
    const avg = times.reduce((a, b) => a + b, 0) / times.length;
    const jitter = times.slice(1).reduce((a, t, i) => a + Math.abs(t - times[i]), 0) / (times.length - 1);
    const max = Math.max(...times);
    $("#rtt-out").innerHTML = `<div class="stats tight">
      <div class="stat"><span class="stat-l">min</span><b class="stat-v">${s[0].toFixed(1)}<small>ms</small></b></div>
      <div class="stat"><span class="stat-l">avg</span><b class="stat-v">${avg.toFixed(1)}<small>ms</small></b></div>
      <div class="stat"><span class="stat-l">p95</span><b class="stat-v">${s[Math.floor(0.95 * (s.length - 1))].toFixed(1)}<small>ms</small></b></div>
      <div class="stat"><span class="stat-l">jitter</span><b class="stat-v">${jitter.toFixed(1)}<small>ms</small></b></div></div>
      <div class="spark" aria-label="RTT per request">${times.map((t) => `<span style="height:${Math.max(4, (t / max) * 60)}px" title="${t.toFixed(1)} ms"></span>`).join("")}</div>
      <p class="hint">The first request is often slower (connection setup); later ones reuse the keep-alive connection.</p>`;
    $("#rtt-go").disabled = false;
    await complete("network", "rtt");
  });
  $("#path-go").addEventListener("click", async () => {
    const r = await api("/api/lab/network");
    $("#path-out").innerHTML = `<ol class="hops">${r.hops.map((h) => `<li><b>${esc(h.name)}</b><span>${esc(h.detail)}</span></li>`).join("")}</ol>
      <p class="hint">${esc(r.scheme)}://${esc(r.host)} · HTTP/${esc(r.http_version)} between the proxy and the API · ${r.x_forwarded_for.length ? "via reverse proxy" : "no proxy in front"}</p>
      <details><summary>Headers received by the API (${Object.keys(r.headers).length})</summary>
      <div class="table-wrap"><table><tbody>${Object.entries(r.headers).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</tbody></table></div></details>`;
    await complete("network", "headers");
  });
  $("#tim-go").addEventListener("click", async () => {
    const url = `/api/lab/network?timing=${Date.now()}`;
    await api(url);
    await new Promise((r) => setTimeout(r, 50));
    const e = performance.getEntriesByName(new URL(url, location.href).href).pop();
    if (!e) { $("#tim-out").innerHTML = `<p class="error">Resource timing not available in this browser.</p>`; return; }
    const parts = [
      ["Queue / stalled", e.domainLookupStart - e.startTime],
      ["DNS lookup", e.domainLookupEnd - e.domainLookupStart],
      ["TCP connect", e.connectEnd - e.connectStart],
      ["Request → first byte (TTFB)", e.responseStart - e.requestStart],
      ["Download", e.responseEnd - e.responseStart],
    ].map(([k, v]) => [k, Math.max(0, v || 0)]);
    const server = (e.serverTiming || []).map((s) => [`server: ${s.description || s.name}`, s.duration]);
    const total = e.duration || parts.reduce((a, [, v]) => a + v, 0);
    const all = [...parts, ...server];
    const maxV = Math.max(1, ...all.map(([, v]) => v));
    $("#tim-out").innerHTML = `<p>Total <b>${total.toFixed(2)} ms</b>${server.length ? `, of which the server spent <b>${server.reduce((a, [, v]) => a + v, 0).toFixed(2)} ms</b>` : ""}.</p>
      <div class="hbars">${all.map(([k, v]) => `<div class="hb"><span class="hb-l">${esc(k)}</span><div class="hb-t"><span class="${k.startsWith("server") ? "g-b" : "g-a"}" style="width:${(v / maxV) * 100}%"></span></div><span class="hb-v">${v.toFixed(2)} ms</span></div>`).join("")}</div>
      <p class="hint">Protocol: ${esc(e.nextHopProtocol || "n/a")} · transfer ${e.transferSize ?? "?"} bytes.</p>`;
    await complete("network", "timing");
  });
  return null;
}

// ======================================================================== Docker lab
const DOCKER_STARTER = `FROM node:latest
WORKDIR /app
COPY . .
RUN npm install
ENV API_KEY=supersecret123
RUN npm run build
EXPOSE 3000
CMD npm start
`;

function dockerLab(view, l) {
  const saved = localStorage.getItem("ag-docker-lab") || DOCKER_STARTER;
  view.innerHTML = `${header(l)}
  <section class="grid-2-1">
    <div class="panel"><div class="panel-h"><h2>${icon("box")} Your Dockerfile</h2><button class="ghost sm" id="dk-reset" type="button">${icon("refresh")} Reset</button></div>
      <textarea id="dk" class="code" rows="16" spellcheck="false" aria-label="Dockerfile editor">${esc(saved)}</textarea>
      <div class="row-btns"><button class="btn" id="dk-go" type="button">Lint Dockerfile</button>
        <label class="check"><input type="checkbox" id="dk-ignore" checked /> My repo has a <code>.dockerignore</code></label></div>
      <div id="dk-out"></div></div>
    <div>${tasksPanel("docker")}
      <div class="panel"><h2>${icon("bulb")} Learn the concepts</h2><ul class="concepts">
        <li><b>Pin base images</b> (<code>node:20.11-alpine</code>) so builds are reproducible.</li>
        <li><b>Layer cache</b>: copy <code>package*.json</code> and install deps <i>before</i> <code>COPY . .</code>.</li>
        <li><b>Multi-stage</b>: build in one stage, copy only the output into a slim runtime image.</li>
        <li><b>Least privilege</b>: never run as root; never bake secrets into <code>ENV</code>.</li>
        <li><b>HEALTHCHECK</b> lets load balancers route around a broken container.</li></ul></div></div>
  </section>`;
  const sevIcon = { critical: "⛔", high: "▲", medium: "◆", low: "●", info: "ℹ" };
  $("#dk-go").addEventListener("click", async () => {
    localStorage.setItem("ag-docker-lab", $("#dk").value);
    try {
      const r = await api("/api/lab/dockerfile", { method: "POST", body: { dockerfile_text: $("#dk").value, has_dockerignore: $("#dk-ignore").checked } });
      $("#dk-out").innerHTML = `<div class="dk-head"><div class="ring sm ${r.score >= 85 ? "g-a" : r.score >= 60 ? "g-b" : r.score >= 40 ? "g-c" : "g-f"}" style="--p:${r.score}%;--size:72px" role="img" aria-label="Lint score ${r.score}"><span>${r.score}</span></div>
        <div><b>${r.findings.length} finding(s)</b> · ${r.instructions} instructions · ${r.stages} stage(s)<div class="chips">${Object.entries(r.checks).map(([k, c]) =>
          `<span class="chip ${c.passed ? "ok" : "warn"}">${icon(c.passed ? "checkCircle" : "target")} ${esc(c.detail)}</span>`).join("")}</div></div></div>
        ${r.findings.length ? `<ul class="findings">${r.findings.map((f) => `<li class="sev-${f.severity}"><span class="sev">${sevIcon[f.severity] || ""} ${esc(f.severity)}</span>
          <div><b>${esc(f.title)}</b><p>${esc(f.detail)}</p><p class="fix">${icon("bulb")} ${esc(f.recommendation)}</p></div></li>`).join("")}</ul>` : `<p class="check-msg ok">${icon("checkCircle")} No findings: production-grade Dockerfile.</p>`}`;
      for (const [k, c] of Object.entries(r.checks)) if (c.passed) await complete("docker", k, { serverRecorded: true });
    } catch (e) { $("#dk-out").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
  });
  $("#dk-reset").addEventListener("click", () => { $("#dk").value = DOCKER_STARTER; $("#dk-out").innerHTML = ""; });
  return null;
}
