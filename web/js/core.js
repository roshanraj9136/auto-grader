// Shared helpers: API client, auth state, formatting, toasts and tiny SVG charts (no dependencies).
export const DIMENSIONS = {
  code_quality: "Code quality",
  architecture: "Architecture",
  security: "Security",
  testing: "Testing",
  devops: "DevOps & Docker",
};
export const DEFAULT_WEIGHTS = { code_quality: 0.25, architecture: 0.25, security: 0.15, testing: 0.2, devops: 0.15 };
export const TRACKS = {
  frontend: "Frontend", backend: "Backend", database: "Database", networking: "Networking",
  devops: "DevOps", security: "Security", fullstack: "Full-stack",
};

export const state = { user: null, health: null, demo: false, signupCode: false };

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
export const fmtMs = (ms) => (ms == null ? "" : ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`);
export const pct = (v) => `${Math.round((v || 0) * 100)}%`;

export function fmtDate(iso, withTime = false) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, withTime
    ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }
    : { day: "numeric", month: "short", year: "numeric" });
}

export function relTime(iso) {
  if (!iso) return "";
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, s] of [["day", 86400], ["hour", 3600], ["minute", 60]]) {
    if (abs >= s) return rtf.format(Math.round(diff / s), unit);
  }
  return rtf.format(Math.round(diff), "second");
}

export function gradeClass(score) {
  if (score == null) return "g-none";
  if (score >= 78) return "g-a";
  if (score >= 62) return "g-b";
  if (score >= 48) return "g-c";
  return "g-f";
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export async function api(path, { method = "GET", body, raw = false } = {}) {
  const opts = { method, headers: {}, credentials: "same-origin" };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (raw) return res;
  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    let msg = res.statusText;
    if (data && typeof data === "object" && data.detail) {
      msg = typeof data.detail === "string" ? data.detail
        : data.detail.map?.((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ") || JSON.stringify(data.detail);
    }
    throw new ApiError(res.status, msg);
  }
  return data;
}

export async function refreshMe() {
  try {
    const me = await api("/api/auth/me");
    state.user = me.user;
    state.demo = me.demo;
    state.signupCode = me.signup_code_required;
  } catch {
    state.user = null;
  }
  return state.user;
}

export function homePath(user = state.user) {
  if (!user) return "/";
  return user.role === "instructor" ? "/instructor/dashboard" : "/student/dashboard";
}

// ---- toasts ----------------------------------------------------------------------------
export function toast(message, kind = "info", ms = 4200) {
  const host = $("#toasts");
  if (!host) return;
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.setAttribute("role", kind === "error" ? "alert" : "status");
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 300); }, ms);
}

// ---- small UI pieces -------------------------------------------------------------------
export function scoreRing(score, grade, size = 112) {
  const p = score == null ? 0 : Math.max(0, Math.min(100, score));
  const label = score == null ? "not graded" : `Score ${score} of 100, grade ${grade}`;
  return `<div class="ring ${gradeClass(score)}" style="--p:${p}%;--size:${size}px" role="img" aria-label="${esc(label)}">
    <span>${score == null ? "–" : esc(score)}<small>${esc(grade || "")}</small></span></div>`;
}

export function statusPill(status) {
  const map = { done: "ok", running: "run", queued: "run", failed: "bad" };
  return `<span class="pill ${map[status] || ""}">${esc(status)}</span>`;
}

export function gradeBadge(score, grade) {
  if (score == null) return `<span class="grade g-none">–</span>`;
  return `<span class="grade ${gradeClass(score)}" title="${esc(score)}/100">${esc(grade || "")} <b>${esc(score)}</b></span>`;
}

export function emptyState(title, body = "", action = "") {
  return `<div class="empty"><div class="empty-ico" aria-hidden="true">◇</div><h3>${esc(title)}</h3><p>${body}</p>${action}</div>`;
}

export function progressBar(value, max, label) {
  const p = max ? Math.min(100, (value / max) * 100) : 0;
  return `<div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="${max}" aria-valuenow="${value}" aria-label="${esc(label)}">
    <span style="width:${p}%"></span></div>`;
}

// ---- SVG charts ------------------------------------------------------------------------
export function lineChart(points, { height = 190, min = 0, max = 100 } = {}) {
  if (!points.length) return emptyState("No graded submissions yet", "Submit a repository to see your progress over time.");
  const W = 640, H = height, pl = 34, pr = 14, pt = 14, pb = 26;
  const n = points.length;
  const x = (i) => pl + (n === 1 ? (W - pl - pr) / 2 : (i * (W - pl - pr)) / (n - 1));
  const y = (v) => pt + (1 - (v - min) / (max - min)) * (H - pt - pb);
  const grid = [0, 25, 50, 75, 100].map((v) =>
    `<line x1="${pl}" x2="${W - pr}" y1="${y(v)}" y2="${y(v)}" class="grid"/><text x="${pl - 6}" y="${y(v) + 4}" class="axis" text-anchor="end">${v}</text>`).join("");
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");
  const area = `${path} L${x(n - 1).toFixed(1)},${y(min)} L${x(0).toFixed(1)},${y(min)} Z`;
  const dots = points.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.score)}" r="4.5" class="dot ${gradeClass(p.score)}">
      <title>${esc(p.label)} · ${esc(p.score)} (${esc(p.grade)}) · ${esc(fmtDate(p.t, true))}</title></circle>`).join("");
  const summary = points.map((p) => `${p.label}: ${p.score}`).join(", ");
  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Score history: ${esc(summary)}">
    <defs><linearGradient id="lg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="var(--acc)" stop-opacity=".35"/><stop offset="1" stop-color="var(--acc)" stop-opacity="0"/></linearGradient></defs>
    ${grid}<path d="${area}" fill="url(#lg)"/><path d="${path}" class="line"/>${dots}</svg>`;
}

export function radarChart(values, { size = 260 } = {}) {
  const keys = Object.keys(DIMENSIONS);
  const c = size / 2, r = size / 2 - 42;
  const pt = (i, v) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / keys.length;
    return [c + Math.cos(a) * r * v, c + Math.sin(a) * r * v];
  };
  const rings = [0.25, 0.5, 0.75, 1].map((f) =>
    `<polygon points="${keys.map((_, i) => pt(i, f).join(",")).join(" ")}" class="grid"/>`).join("");
  const spokes = keys.map((_, i) => `<line x1="${c}" y1="${c}" x2="${pt(i, 1)[0]}" y2="${pt(i, 1)[1]}" class="grid"/>`).join("");
  const has = keys.some((k) => values[k] != null);
  const shape = has ? `<polygon points="${keys.map((k, i) => pt(i, (values[k] ?? 0) / 10).join(",")).join(" ")}" class="shape"/>` +
    keys.map((k, i) => values[k] == null ? "" : `<circle cx="${pt(i, values[k] / 10)[0]}" cy="${pt(i, values[k] / 10)[1]}" r="3.5" class="vertex"/>`).join("") : "";
  const labels = keys.map((k, i) => {
    const [lx, ly] = pt(i, 1.24);
    return `<text x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="middle" class="axis">${esc(DIMENSIONS[k].split(" ")[0])}
      <tspan x="${lx}" dy="13" class="val">${values[k] == null ? "–" : values[k]}</tspan></text>`;
  }).join("");
  const desc = keys.map((k) => `${DIMENSIONS[k]} ${values[k] ?? "not graded"}`).join(", ");
  return `<svg viewBox="0 0 ${size} ${size}" class="chart radar" role="img" aria-label="Skill profile out of 10: ${esc(desc)}">${rings}${spokes}${shape}${labels}</svg>`;
}

export function barChart(entries, { max, unit = "", height = 170, colorFn } = {}) {
  if (!entries.length) return "";
  const W = 640, H = height, pb = 24, pt = 16;
  const top = max ?? Math.max(1, ...entries.map(([, v]) => v || 0));
  const bw = (W - 20) / entries.length;
  const bars = entries.map(([label, v], i) => {
    const h = ((v || 0) / top) * (H - pb - pt);
    const xx = 10 + i * bw + bw * 0.15;
    return `<g><rect x="${xx}" y="${H - pb - h}" width="${bw * 0.7}" height="${Math.max(h, 1)}" rx="5" class="barfill ${colorFn ? colorFn(label, v) : ""}"><title>${esc(label)}: ${esc(v)}${unit}</title></rect>
      <text x="${xx + bw * 0.35}" y="${H - pb - h - 5}" text-anchor="middle" class="axis">${v ?? 0}${unit}</text>
      <text x="${xx + bw * 0.35}" y="${H - 7}" text-anchor="middle" class="axis">${esc(label)}</text></g>`;
  }).join("");
  const desc = entries.map(([l, v]) => `${l}: ${v ?? 0}${unit}`).join(", ");
  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="${esc(desc)}">${bars}</svg>`;
}

export function hbars(entries, { max = 10, fmt = (v) => v } = {}) {
  return `<div class="hbars">${entries.map(([label, v]) => `<div class="hb"><span class="hb-l">${esc(label)}</span>
    <div class="hb-t"><span class="${gradeClass(v == null ? null : v * 10)}" style="width:${v == null ? 0 : Math.min(100, (v / max) * 100)}%"></span></div>
    <span class="hb-v">${v == null ? "–" : esc(fmt(v))}</span></div>`).join("")}</div>`;
}
