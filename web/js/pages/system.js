import { api, emptyState, esc, fmtMs, state } from "../core.js";

export async function page(view) {
  const [h, m] = await Promise.all([api("/api/health"), api("/api/metrics")]);
  const rows = Object.entries(m.stages);
  view.innerHTML = `<header class="page-h"><div><p class="kicker">Platform</p><h1>System & latency</h1>
    <p class="hint">Live numbers from the replica that served this page. Grading is a latency-optimised DAG; these are rolling p50/p95 per stage.</p></div>
    <button class="btn ghost" id="sys-refresh" type="button">Refresh</button></header>
  <section class="stats">
    <div class="stat acc"><span class="stat-l">Status</span><b class="stat-v">${esc(h.status)}</b><span class="stat-s">v${esc(h.version)}</span></div>
    <div class="stat cyan"><span class="stat-l">Replica</span><b class="stat-v sm">${esc(h.instance)}</b><span class="stat-s">served this request</span></div>
    <div class="stat green"><span class="stat-l">Database</span><b class="stat-v sm">${esc(h.database.engine)}</b><span class="stat-s">ping ${h.database.ping_ms ?? "–"} ms</span></div>
    <div class="stat amber"><span class="stat-l">Agents</span><b class="stat-v sm">${h.llm_mode ? esc(h.agent_model) : "heuristic"}</b><span class="stat-s">${h.llm_mode ? "LLM mode" : "no API key: deterministic scorers"}</span></div>
    <div class="stat"><span class="stat-l">Docker sandbox</span><b class="stat-v sm">${h.docker_available ? "on" : "off"}</b><span class="stat-s">${h.docker_available ? "build + smoke run" : "static Dockerfile lint"}</span></div>
  </section>
  <section class="panel"><h2>Stage latency</h2>
    ${rows.length ? `<div class="table-wrap"><table><thead><tr><th>Stage</th><th class="num">n</th><th class="num">p50</th><th class="num">p95</th><th class="num">max</th></tr></thead>
      <tbody>${rows.map(([n, s]) => `<tr><td>${esc(n)}</td><td class="num">${s.count}</td><td class="num">${fmtMs(s.p50_ms)}</td><td class="num">${fmtMs(s.p95_ms)}</td><td class="num">${fmtMs(s.max_ms)}</td></tr>`).join("")}</tbody></table></div>
      <p class="hint mono">counters: ${esc(JSON.stringify(m.counters))} · jobs: ${esc(JSON.stringify(m.jobs.by_status))}</p>`
      : emptyState("No jobs on this replica yet", "Grade a repository to populate the latency table.")}</section>
  <section class="panel"><h2>Architecture</h2>
    <div class="arch">
      <div class="node">Browser / PWA</div><div class="arrow" aria-hidden="true">→</div>
      <div class="node">Nginx<small>rate limit · SSE · LB</small></div><div class="arrow" aria-hidden="true">→</div>
      <div class="node">API replicas<small>FastAPI · JobManager</small></div><div class="arrow" aria-hidden="true">→</div>
      <div class="node">Grading DAG<small>5 agents + judge</small></div><div class="arrow" aria-hidden="true">→</div>
      <div class="node">PostgreSQL · reports<small>shared state</small></div>
    </div>
    <p class="hint">API docs: <a href="/docs" target="_blank" rel="noopener">OpenAPI / Swagger</a> · ${state.user ? "" : "sign in to grade repositories."}</p></section>`;
  view.querySelector("#sys-refresh").addEventListener("click", () => page(view));
}
