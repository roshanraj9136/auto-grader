// Shared helpers: API client, auth state, formatting, icons, toasts and small SVG charts (no dependencies).
export const DIMENSIONS = {
  code_quality: "Code quality",
  architecture: "Architecture",
  security: "Security",
  testing: "Testing",
  devops: "Docker & DevOps",
};
export const DIM_HELP = {
  code_quality: "Readable, well-structured code",
  architecture: "How the app is organised",
  security: "Keeping users and data safe",
  testing: "Tests that prove it works",
  devops: "Containers and deployment",
};
export const DEFAULT_WEIGHTS = { code_quality: 0.25, architecture: 0.25, security: 0.15, testing: 0.2, devops: 0.15 };
export const TRACKS = {
  frontend: "Frontend", backend: "Backend", database: "Database", networking: "Networking",
  devops: "DevOps", security: "Security", fullstack: "Full-stack",
};

export const state = { user: null, demo: false, signupCode: false };

// Public demo logins (AUTOGRADER_DEMO_SEED=1). The server refuses their write actions; the UI says so up front.
const DEMO_LOGINS = new Set(["instructor@autograder.local", "student@autograder.local"]);
export const isDemoUser = (u = state.user) => !!u && DEMO_LOGINS.has(String(u.email).toLowerCase());
export const isReadOnly = (u = state.user) => isDemoUser(u) && u.role === "instructor";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
export const fmtMs = (ms) => (ms == null ? "" : ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`);
export const pct = (v) => `${Math.round((v || 0) * 100)}%`;

// ---- icons (24px line icons, stroke = currentColor) -------------------------------------
const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
  book: '<path d="M2 4h7a3 3 0 0 1 3 3v14a2 2 0 0 0-2-2H2z"/><path d="M22 4h-7a3 3 0 0 0-3 3v14a2 2 0 0 1 2-2h8z"/>',
  flask: '<path d="M9 3h6"/><path d="M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3"/><path d="M7 15h10"/>',
  zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
  trophy: '<path d="M8 21h8M12 17v4"/><path d="M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  users: '<circle cx="9" cy="8" r="4"/><path d="M2 21a7 7 0 0 1 14 0"/><path d="M16 4a4 4 0 0 1 0 8M22 21a7 7 0 0 0-4-6.3"/>',
  chart: '<path d="M3 3v18h18"/><path d="M8 17v-5M13 17V8M18 17v-7"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  git: '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/><path d="M6 7v10M18 9a6 6 0 0 1-6 6H8"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  download: '<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  chevronRight: '<path d="m9 6 6 6-6 6"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  arrowRight: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  sparkles: '<path d="M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8z"/><path d="M19 15l.8 2.2 2.2.8-2.2.8L19 21l-.8-2.2-2.2-.8 2.2-.8z"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
  code: '<path d="m16 18 6-6-6-6M8 6l-6 6 6 6"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  network: '<rect x="9" y="2" width="6" height="5" rx="1"/><rect x="2" y="17" width="6" height="5" rx="1"/><rect x="16" y="17" width="6" height="5" rx="1"/><path d="M12 7v5M5 17v-2.5h14V17"/>',
  box: '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3l-5.5 2.9 1-6.2L3 9.6l6.2-.9z"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
  testCheck: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m8 12 3 3 5-6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  smartphone: '<rect x="6" y="2" width="12" height="20" rx="2"/><path d="M11 18h2"/>',
  graduation: '<path d="m2 9 10-5 10 5-10 5z"/><path d="M6 11v5c3 2 9 2 12 0v-5M22 9v6"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m14 6 4 4"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  flame: '<path d="M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-2 1-3.5 2-4.5.3 1.6 1 2.5 2 3C11 9 11 6 12 3z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
};
export function icon(name, cls = "") {
  return `<svg class="i ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${ICONS[name] || ICONS.star}</svg>`;
}
export const DIM_ICON = { code_quality: "code", architecture: "layers", security: "shield", testing: "testCheck", devops: "box" };
export const LAB_ICON = { frontend: "code", database: "database", loadbalancer: "network", network: "globe", docker: "box" };

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
    throw new ApiError(res.status, msg.charAt(0).toUpperCase() + msg.slice(1));
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
  el.innerHTML = `${icon(kind === "error" ? "alert" : kind === "ok" ? "checkCircle" : "sparkles")}<span></span>`;
  el.querySelector("span").textContent = message;
  host.appendChild(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 300); }, ms);
}

// ---- small UI pieces -------------------------------------------------------------------
export function scoreRing(score, grade, size = 112) {
  const p = score == null ? 0 : Math.max(0, Math.min(100, score));
  const label = score == null ? "not graded yet" : `Score ${score} out of 100, grade ${grade}`;
  return `<div class="ring ${gradeClass(score)}" style="--p:${p}%;--size:${size}px" role="img" aria-label="${esc(label)}">
    <span>${score == null ? "–" : esc(Math.round(score))}<small>${esc(grade || "")}</small></span></div>`;
}

const STATUS_LABEL = { done: "Graded", running: "Grading…", queued: "Waiting…", failed: "Failed" };
export function statusPill(status) {
  const map = { done: "ok", running: "run", queued: "run", failed: "bad" };
  return `<span class="pill ${map[status] || ""}">${esc(STATUS_LABEL[status] || status)}</span>`;
}

export function gradeBadge(score, grade) {
  if (score == null) return `<span class="grade g-none">–</span>`;
  return `<span class="grade ${gradeClass(score)}" title="${esc(score)} out of 100">${grade ? `<b>${esc(grade)}</b>` : ""}${esc(Math.round(score))}</span>`;
}

export function emptyState(title, body = "", action = "", ico = "sparkles") {
  return `<div class="empty"><div class="empty-ico">${icon(ico)}</div><h3>${esc(title)}</h3>${body ? `<p>${body}</p>` : ""}${action}</div>`;
}

export function progressBar(value, max, label) {
  const p = max ? Math.min(100, (value / max) * 100) : 0;
  return `<div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="${max}" aria-valuenow="${value}" aria-label="${esc(label)}">
    <span style="width:${p}%"></span></div>`;
}

export function pageHeader(kicker, title, sub = "", actions = "") {
  return `<header class="page-h"><div class="page-h-text">${kicker ? `<p class="kicker">${kicker}</p>` : ""}<h1>${title}</h1>${sub ? `<p class="sub">${sub}</p>` : ""}</div>
    ${actions ? `<div class="page-h-actions">${actions}</div>` : ""}</header>`;
}

// ---- SVG charts ------------------------------------------------------------------------
export function lineChart(points, { height = 200, min = 0, max = 100 } = {}) {
  if (!points.length) return emptyState("No grades yet", "Submit a repository to start tracking your progress.", "", "chart");
  // Narrower drawing space on phones so axis labels and dots aren't scaled down to a few pixels.
  const W = window.innerWidth < 600 ? 360 : 640, H = height, pl = 34, pr = 14, pt = 16, pb = 26;
  const n = points.length;
  const x = (i) => pl + (n === 1 ? (W - pl - pr) / 2 : (i * (W - pl - pr)) / (n - 1));
  const y = (v) => pt + (1 - (v - min) / (max - min)) * (H - pt - pb);
  const grid = [0, 25, 50, 75, 100].map((v) =>
    `<line x1="${pl}" x2="${W - pr}" y1="${y(v)}" y2="${y(v)}" class="grid"/><text x="${pl - 8}" y="${y(v) + 4}" class="axis" text-anchor="end">${v}</text>`).join("");
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");
  const area = `${path} L${x(n - 1).toFixed(1)},${y(min)} L${x(0).toFixed(1)},${y(min)} Z`;
  const dots = points.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.score)}" r="5" class="dot ${gradeClass(p.score)}">
      <title>${esc(p.label)}: ${esc(p.score)} (${esc(p.grade)}), ${esc(fmtDate(p.t, true))}</title></circle>`).join("");
  const summary = points.map((p) => `${p.label}: ${p.score}`).join(", ");
  const note = n === 1 ? `<text x="${W / 2}" y="${H - 6}" text-anchor="middle" class="axis">Submit again to see your trend</text>` : "";
  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="Score history: ${esc(summary)}">
    ${grid}${n > 1 ? `<path d="${area}" class="area"/><path d="${path}" class="line"/>` : ""}${dots}${note}</svg>`;
}

/** A learning-path line such as "Containers: multi-stage builds, non-root images" with its topic in bold. */
export function learnLine(text) {
  const s = String(text ?? "");
  const i = s.indexOf(":");
  if (i < 3 || i > 90) return esc(s);
  return `<b>${esc(s.slice(0, i))}</b>${esc(s.slice(i))}`;
}

/** Days until an ISO date: negative once it has passed, null when there is no date. */
export function daysLeft(iso) {
  return iso ? (new Date(iso).getTime() - Date.now()) / 86400e3 : null;
}

export function radarChart(values, { size = 280 } = {}) {
  const keys = Object.keys(DIMENSIONS);
  const c = size / 2, r = size / 2 - 62;
  const pt = (i, v) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / keys.length;
    return [c + Math.cos(a) * r * v, c + Math.sin(a) * r * v];
  };
  const rings = [0.25, 0.5, 0.75, 1].map((f) =>
    `<polygon points="${keys.map((_, i) => pt(i, f).join(",")).join(" ")}" class="grid"/>`).join("");
  const spokes = keys.map((_, i) => `<line x1="${c}" y1="${c}" x2="${pt(i, 1)[0]}" y2="${pt(i, 1)[1]}" class="grid"/>`).join("");
  const has = keys.some((k) => values[k] != null);
  const shape = has ? `<polygon points="${keys.map((k, i) => pt(i, (values[k] ?? 0) / 10).join(",")).join(" ")}" class="shape"/>` +
    keys.map((k, i) => values[k] == null ? "" : `<circle cx="${pt(i, values[k] / 10)[0]}" cy="${pt(i, values[k] / 10)[1]}" r="4" class="vertex"/>`).join("") : "";
  const labels = keys.map((k, i) => {
    const [lx, ly] = pt(i, 1.27);
    return `<text x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="middle" class="axis">${esc(DIMENSIONS[k].split(" ")[0])}
      <tspan x="${lx}" dy="15" class="val">${values[k] == null ? "–" : values[k]}</tspan></text>`;
  }).join("");
  const desc = keys.map((k) => `${DIMENSIONS[k]} ${values[k] ?? "not graded"}`).join(", ");
  return `<svg viewBox="0 0 ${size} ${size}" class="chart radar" role="img" aria-label="Skill profile out of 10: ${esc(desc)}">${rings}${spokes}${shape}${labels}</svg>`;
}

export function barChart(entries, { max, unit = "", height = 180, colorFn } = {}) {
  if (!entries.length) return "";
  const W = window.innerWidth < 600 ? 360 : 640, H = height, pb = 26, pt = 18;
  const top = max ?? Math.max(1, ...entries.map(([, v]) => v || 0));
  // Bars never grow wider than 72 units, so a chart with one or two bars stays readable; the group is centred.
  const bw = Math.min((W - 20) / entries.length, 72);
  const x0 = (W - bw * entries.length) / 2;
  const bars = entries.map(([label, v], i) => {
    const h = ((v || 0) / top) * (H - pb - pt);
    const xx = x0 + i * bw + bw * 0.18;
    return `<g><rect x="${xx}" y="${H - pb - h}" width="${bw * 0.64}" height="${Math.max(h, 2)}" rx="6" class="barfill ${colorFn ? colorFn(label, v) : ""}"><title>${esc(label)}: ${esc(v)}${unit}</title></rect>
      <text x="${xx + bw * 0.32}" y="${H - pb - h - 6}" text-anchor="middle" class="axis val">${v ?? 0}${unit}</text>
      <text x="${xx + bw * 0.32}" y="${H - 7}" text-anchor="middle" class="axis">${esc(label)}</text></g>`;
  }).join("");
  const desc = entries.map(([l, v]) => `${l}: ${v ?? 0}${unit}`).join(", ");
  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="${esc(desc)}">${bars}</svg>`;
}

export function hbars(entries, { max = 10, fmt = (v) => v } = {}) {
  return `<div class="hbars">${entries.map(([label, v]) => `<div class="hb"><span class="hb-l">${esc(label)}</span>
    <div class="hb-t"><span class="${gradeClass(v == null ? null : (v / max) * 100)}" style="width:${v == null ? 0 : Math.min(100, (v / max) * 100)}%"></span></div>
    <span class="hb-v">${v == null ? "–" : esc(fmt(v))}</span></div>`).join("")}</div>`;
}
