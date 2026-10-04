// AutoGrader+ single-page app: History-API router, role-aware layout, page modules (no build step).
import { $, $$, api, esc, homePath, refreshMe, state, toast } from "./js/core.js";
import * as landing from "./js/pages/landing.js";
import * as student from "./js/pages/student.js";
import * as grader from "./js/pages/grader.js";
import * as instructor from "./js/pages/instructor.js";
import * as labs from "./js/pages/labs.js";
import * as system from "./js/pages/system.js";

// [pattern, page, access, title]   access: public | guest | user | student | instructor
const ROUTES = [
  ["/", landing.home, "public", "Learn full-stack, graded by AI agents"],
  ["/login", landing.login, "guest", "Sign in"],
  ["/signup", landing.signup, "guest", "Create account"],
  ["/student/dashboard", student.dashboard, "user", "Dashboard"],
  ["/student/assignments", student.assignments, "user", "Assignments"],
  ["/student/assignment/:id", student.assignment, "user", "Assignment"],
  ["/student/submissions", student.submissions, "user", "My submissions"],
  ["/student/leaderboard", student.leaderboard, "user", "Leaderboard"],
  ["/student/profile", student.profile, "user", "Profile"],
  ["/labs", labs.index, "public", "Labs"],
  ["/labs/:lab", labs.lab, "public", "Lab"],
  ["/grader", grader.page, "user", "Practice grader"],
  ["/jobs/:id", grader.job, "user", "Grading"],
  ["/instructor/dashboard", instructor.dashboard, "instructor", "Class overview"],
  ["/instructor/assignments", instructor.assignments, "instructor", "Manage assignments"],
  ["/instructor/students", instructor.students, "instructor", "Students"],
  ["/system", system.page, "public", "System & latency"],
];

const NAV = {
  student: [
    ["Learn", [["/student/dashboard", "Dashboard", "⌂"], ["/student/assignments", "Assignments", "▤"], ["/labs", "Labs", "⚗"],
      ["/grader", "Practice grader", "▶"]]],
    ["Progress", [["/student/submissions", "Submissions", "☰"], ["/student/leaderboard", "Leaderboard", "★"],
      ["/student/profile", "Profile", "◉"]]],
    ["Platform", [["/system", "System & latency", "◔"]]],
  ],
  instructor: [
    ["Teach", [["/instructor/dashboard", "Class overview", "⌂"], ["/instructor/assignments", "Assignments", "▤"],
      ["/instructor/students", "Students", "☺"]]],
    ["Explore", [["/labs", "Labs", "⚗"], ["/grader", "Grader", "▶"], ["/student/leaderboard", "Leaderboard", "★"]]],
    ["Platform", [["/system", "System & latency", "◔"], ["/student/profile", "Profile", "◉"]]],
  ],
  guest: [
    ["Explore", [["/", "Home", "⌂"], ["/labs", "Labs", "⚗"], ["/system", "System & latency", "◔"]]],
    ["Account", [["/login", "Sign in", "→"], ["/signup", "Create account", "+"]]],
  ],
};

let cleanup = null;
let navToken = 0;

function match(path) {
  for (const [pattern, page, access, title] of ROUTES) {
    const keys = [];
    const re = new RegExp("^" + pattern.replace(/:[a-z]+/g, (k) => { keys.push(k.slice(1)); return "([^/]+)"; }) + "/?$");
    const m = path.match(re);
    if (m) return { page, access, title, params: Object.fromEntries(keys.map((k, i) => [k, decodeURIComponent(m[i + 1])])) };
  }
  return null;
}

export function navigate(path, { replace = false, keepScroll = false } = {}) {
  if (replace) history.replaceState({}, "", path);
  else history.pushState({}, "", path);
  render({ keepScroll });
}
window.__nav = navigate;
// Soft refresh of the current page (e.g. dashboards polling while a grading runs).
window.__refresh = () => render({ keepScroll: true, quiet: true });

function renderShell() {
  const u = state.user;
  const nav = NAV[u ? u.role : "guest"];
  const path = location.pathname;
  $("#sidebar-nav").innerHTML = nav.map(([section, items]) => `<div class="nav-sec"><div class="nav-h">${esc(section)}</div>
    ${items.map(([href, label, ico]) => {
      const active = path === href || (href !== "/" && path.startsWith(href + "/")) || (href === "/student/assignments" && path.startsWith("/student/assignment/"));
      return `<a href="${href}" class="nav-a${active ? " active" : ""}"${active ? ' aria-current="page"' : ""}><span class="ico" aria-hidden="true">${ico}</span>${esc(label)}</a>`;
    }).join("")}</div>`).join("");
  $("#mobile-nav").innerHTML = nav.flatMap(([, items]) => items).slice(0, 5).map(([href, label, ico]) =>
    `<a href="${href}" class="${path === href || path.startsWith(href + "/") ? "active" : ""}"><span aria-hidden="true">${ico}</span>${esc(label.split(" ")[0])}</a>`).join("");
  $("#user-box").innerHTML = u
    ? `<a href="/student/profile" class="avatar" title="Profile">${esc(u.name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase())}</a>
       <div class="who"><b>${esc(u.name)}</b><span>${esc(u.role)}${u.entry_no ? " · " + esc(u.entry_no) : ""}</span></div>
       <button class="ghost sm" id="logout" type="button">Sign out</button>`
    : `<a class="btn sm" href="/login">Sign in</a>`;
  $("#logout")?.addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    state.user = null;
    toast("Signed out");
    navigate("/");
  });
}

async function render({ keepScroll = false, quiet = false } = {}) {
  const token = ++navToken;
  if (typeof cleanup === "function") { try { cleanup(); } catch { /* ignore */ } }
  cleanup = null;
  const route = match(location.pathname);
  const host = $("#view");
  if (!route) {
    renderShell();
    host.innerHTML = `<section class="panel"><h1>Page not found</h1><p>No page at <code>${esc(location.pathname)}</code>.</p><a class="btn" href="${homePath()}">Go home</a></section>`;
    return;
  }
  const u = state.user;
  const here = location.pathname + location.search;
  if (route.access === "guest" && u) return navigate(homePath(), { replace: true });
  if (["user", "student", "instructor"].includes(route.access) && !u) {
    return navigate(`/login?next=${encodeURIComponent(here)}`, { replace: true });
  }
  if (route.access === "instructor" && u.role !== "instructor") return navigate(homePath(), { replace: true });
  if (route.page === landing.home && u) return navigate(homePath(), { replace: true });

  document.title = `${route.title} · AutoGrader+`;
  renderShell();
  document.body.classList.toggle("guest", !u);
  // Each navigation renders into its own container: if the user navigates again while this page is
  // still loading, the stale page writes into a detached element instead of over the new page.
  const view = document.createElement("div");
  view.className = "view-inner";
  const scrollY = window.scrollY;
  if (quiet) {
    // Soft refresh: keep the old content visible until the new one is ready.
    try {
      const result = await route.page(view, route.params, new URLSearchParams(location.search));
      if (token !== navToken) { if (typeof result === "function") result(); return; }
      host.replaceChildren(view);
      cleanup = result;
      window.scrollTo(0, scrollY);
    } catch { /* keep the current content on a failed background refresh */ }
    return;
  }
  host.replaceChildren(view);
  view.innerHTML = `<div class="loading" aria-busy="true"><span class="spinner"></span> Loading…</div>`;
  try {
    const result = await route.page(view, route.params, new URLSearchParams(location.search));
    if (token !== navToken) { if (typeof result === "function") result(); return; }
    cleanup = result;
  } catch (err) {
    if (token !== navToken) return;
    if (err.status === 401) { state.user = null; return navigate(`/login?next=${encodeURIComponent(here)}`, { replace: true }); }
    view.innerHTML = `<section class="panel"><h1>Something went wrong</h1><p class="error">${esc(err.message)}</p>
      <button class="btn" type="button" id="retry">Retry</button></section>`;
    $("#retry").addEventListener("click", () => render());
  }
  host.focus({ preventScroll: true });
  if (!keepScroll) window.scrollTo(0, 0);
}

// Intercept same-origin links for client-side navigation.
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[href]");
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const href = a.getAttribute("href");
  if (!href.startsWith("/") || href.startsWith("//") || href.startsWith("/api/") || a.target || a.hasAttribute("download")) return;
  e.preventDefault();
  $("#app").classList.remove("nav-open");
  if (href !== location.pathname + location.search) navigate(href);
});
window.addEventListener("popstate", () => render());
$("#menu-btn").addEventListener("click", () => {
  const open = $("#app").classList.toggle("nav-open");
  $("#menu-btn").setAttribute("aria-expanded", String(open));
});
window.addEventListener("auth-changed", renderShell);

async function loadHealth() {
  try {
    state.health = await api("/api/health");
    const h = state.health;
    $("#health").innerHTML = `<span class="dot ${h.status === "ok" ? "ok" : "bad"}" aria-hidden="true"></span>
      <span>${h.llm_mode ? "LLM agents" : "Heuristic agents"}</span><span class="sep">·</span>
      <span>${esc(h.database.engine.split(" ")[0])}</span><span class="sep">·</span><span title="replica that served this request">${esc(h.instance)}</span>`;
  } catch {
    $("#health").innerHTML = `<span class="dot bad" aria-hidden="true"></span> API unreachable`;
  }
}

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* offline shell is optional */ });
}

await refreshMe();
loadHealth();
render();
