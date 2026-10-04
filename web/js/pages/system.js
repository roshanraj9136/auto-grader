// Instructor-only: platform health and grading-engine latency (kept out of the student UI).
import { api, emptyState, esc, fmtMs, icon, pageHeader } from "../core.js";

function stat(label, value, sub, ico, cls = "") {
  return `<div class="stat ${cls}"><div class="stat-top"><span class="stat-l">${esc(label)}</span><span class="stat-ico">${icon(ico)}</span></div>
    <b class="stat-v sm">${value}</b>${sub ? `<span class="stat-s">${sub}</span>` : ""}</div>`;
}

export async function page(view) {
  const [h, m] = await Promise.all([api("/api/health"), api("/api/metrics")]);
  const rows = Object.entries(m.stages);
  view.innerHTML = `${pageHeader("Admin", "Platform health", "How the grading engine is running on the server that answered this page.",
      `<button class="ghost" id="sys-refresh" type="button">${icon("refresh")} Refresh</button>`)}
  <section class="stats">
    ${stat("Status", h.status === "ok" ? "All good" : esc(h.status), `version ${esc(h.version)}`, "activity")}
    ${stat("Database", esc(h.database.engine), `responds in ${h.database.ping_ms ?? "–"} ms`, "database", "sky")}
    ${stat("Reviewers", h.llm_mode ? "AI (LLM)" : "Rule-based", h.llm_mode ? esc(h.agent_model) : "add ANTHROPIC_API_KEY for AI feedback", "sparkles", "violet")}
    ${stat("Docker builds", h.docker_available ? "On" : "Off", h.docker_available ? "Dockerfiles are built and run" : "Dockerfiles are checked, not built", "box", "amber")}
  </section>
  <section class="panel"><div class="panel-h"><h2>${icon("clock")} Grading speed by step</h2><span class="hint">since this server started</span></div>
    ${rows.length ? `<div class="table-wrap"><table><thead><tr><th>Step</th><th class="num">Runs</th><th class="num">Typical (p50)</th><th class="num">Slow (p95)</th><th class="num">Slowest</th></tr></thead>
      <tbody>${rows.map(([n, s]) => `<tr><td>${esc(n)}</td><td class="num">${s.count}</td><td class="num">${fmtMs(s.p50_ms)}</td><td class="num">${fmtMs(s.p95_ms)}</td><td class="num">${fmtMs(s.max_ms)}</td></tr>`).join("")}</tbody></table></div>`
      : emptyState("No gradings yet on this server", "Numbers appear after the first submission.", "", "clock")}</section>
  <section class="panel"><div class="panel-h"><h2>${icon("layers")} How it's built</h2><a href="/docs" target="_blank" rel="noopener">API docs</a></div>
    <div class="arch">
      <div class="node">Browser / phone<small>web app</small></div><div class="arrow" aria-hidden="true">→</div>
      <div class="node">Load balancer<small>Nginx</small></div><div class="arrow" aria-hidden="true">→</div>
      <div class="node">API servers<small>FastAPI</small></div><div class="arrow" aria-hidden="true">→</div>
      <div class="node">5 reviewers + judge<small>grading engine</small></div><div class="arrow" aria-hidden="true">→</div>
      <div class="node">PostgreSQL<small>accounts, grades, reports</small></div>
    </div>
    <p class="hint" style="margin-top:12px">Server: ${esc(h.instance)}</p></section>`;
  view.querySelector("#sys-refresh").addEventListener("click", () => page(view));
}
