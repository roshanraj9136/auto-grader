// AutoGrader+ single-page app: History-API router, role-aware layout, page modules (no build step).
import { $, api, esc, homePath, icon, isReadOnly, refreshMe, state, toast } from "./js/core.js";
import * as landing from "./js/pages/landing.js";
import * as student from "./js/pages/student.js";
import * as grader from "./js/pages/grader.js";
import * as instructor from "./js/pages/instructor.js";
import * as insights from "./js/pages/insights.js";
import * as about from "./js/pages/about.js";
import * as labs from "./js/pages/labs.js";
import * as system from "./js/pages/system.js";

// [pattern, page, access, title]   access: public | guest | user | instructor
const ROUTES = [
  ["/", landing.home, "public", "Learn full-stack development"],
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
  ["/how-it-works", about.page, "public", "How it works"],
  ["/grader", grader.page, "user", "Practice"],
  ["/jobs/:id", grader.job, "user", "Feedback"],
  ["/instructor/dashboard", instructor.dashboard, "instructor", "Class overview"],
  ["/instructor/assignments", instructor.assignments, "instructor", "Manage assignments"],
  ["/instructor/students", instructor.students, "instructor", "Students"],
  ["/instructor/gradebook", insights.gradebook, "instructor", "Gradebook"],
  ["/instructor/assignment/:id", insights.assignmentReport, "instructor", "Assignment analytics"],
  ["/instructor/student/:id", insights.studentProfile, "instructor", "Student"],
  ["/system", system.page, "instructor", "Platform health"],
];

const NAV = {
  student: [
    ["", [["/student/dashboard", "Home", "home"], ["/student/assignments", "Assignments", "book"],
      ["/labs", "Labs", "flask"], ["/grader", "Practice", "zap"]]],
    ["Your progress", [["/student/submissions", "My submissions", "list"], ["/student/leaderboard", "Leaderboard", "trophy"],
      ["/student/profile", "Profile", "user"]]],
    ["About", [["/how-it-works", "How it works", "layers"]]],
  ],
  instructor: [
    ["", [["/instructor/dashboard", "Overview", "chart"], ["/instructor/gradebook", "Gradebook", "list"],
      ["/instructor/students", "Students", "users"], ["/instructor/assignments", "Assignments", "book"]]],
    ["Course tools", [["/labs", "Labs", "flask"], ["/grader", "Practice grading", "zap"], ["/student/leaderboard", "Leaderboard", "trophy"]]],
    ["Admin", [["/system", "Platform health", "activity"], ["/how-it-works", "How it works", "layers"], ["/student/profile", "Profile", "user"]]],
  ],
};
// Instructors work at a desk: their sections run across the top bar instead of a sidebar.
const TABS = [["/instructor/dashboard", "Overview"], ["/instructor/gradebook", "Gradebook"], ["/instructor/students", "Students"],
  ["/instructor/assignments", "Assignments"], ["/labs", "Labs"], ["/grader", "Practice grading"], ["/student/leaderboard", "Leaderboard"],
  ["/system", "Platform health"], ["/how-it-works", "How it works"]];
const MOBILE = {
  student: [["/student/dashboard", "Home", "home"], ["/student/assignments", "Assignments", "book"], ["/labs", "Labs", "flask"],
    ["/student/submissions", "Results", "list"], ["/student/profile", "Profile", "user"]],
  instructor: [["/instructor/dashboard", "Overview", "chart"], ["/instructor/gradebook", "Grades", "list"],
    ["/instructor/students", "Students", "users"], ["/instructor/assignments", "Assignments", "book"], ["/student/profile", "Profile", "user"]],
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

const isActive = (href, path) => path === href || (href !== "/" && path.startsWith(href + "/"))
  || (href === "/student/assignments" && path.startsWith("/student/assignment/"))
  || (href === "/instructor/assignments" && path.startsWith("/instructor/assignment/"))
  || (href === "/instructor/students" && path.startsWith("/instructor/student/"));

// The public demo instructor can look at everything but not change it: say so, and disable write controls.
// (The server refuses those requests anyway; this only avoids confusing error messages.)
function applyReadOnly(root) {
  if (!isReadOnly()) return;
  root.querySelectorAll("[data-write]").forEach((el) => {
    el.setAttribute("aria-disabled", "true");
    el.title = "Read-only demo: sign in with the real instructor account to make changes";
    if (el.tagName === "A") { el.removeAttribute("href"); el.classList.add("is-disabled"); } else el.disabled = true;
  });
}
window.__applyReadOnly = applyReadOnly;

async function signOut() {
  await api("/api/auth/logout", { method: "POST" }).catch(() => {});
  state.user = null;
  toast("You're signed out.");
  navigate("/");
}

function renderShell() {
  const u = state.user;
  const path = location.pathname;
  document.body.classList.toggle("guest", !u);
  document.body.classList.toggle("role-student", u?.role === "student");
  document.body.classList.toggle("role-instructor", u?.role === "instructor");
  if (u) {
    const current = (href) => isActive(href, path) ? ' class="active" aria-current="page"' : "";
    $("#brand-sub").textContent = u.role === "instructor" ? "Instructor workspace" : "Full-stack course";
    $("#sidebar-nav").innerHTML = NAV[u.role].map(([section, items]) => `<div class="nav-sec">${section ? `<div class="nav-h">${esc(section)}</div>` : ""}
      ${items.map(([href, label, ico]) => {
        const active = isActive(href, path);
        return `<a href="${href}" class="nav-a${active ? " active" : ""}"${active ? ' aria-current="page"' : ""}>${icon(ico)}<span>${esc(label)}</span></a>`;
      }).join("")}</div>`).join("");
    $("#mobile-nav").innerHTML = MOBILE[u.role].map(([href, label, ico]) =>
      `<a href="${href}"${current(href)}>${icon(ico)}<span>${esc(label)}</span></a>`).join("");
    $("#role-tabs").innerHTML = u.role === "instructor" ? TABS.map(([href, label]) => `<a href="${href}"${current(href)}>${esc(label)}</a>`).join("") : "";
    const initials = u.name.split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
    const role = u.role === "instructor" ? "Instructor" : `Student${u.entry_no ? `, ${esc(u.entry_no)}` : ""}`;
    $("#side-foot").innerHTML = `<div class="user-card"><a href="/student/profile" class="avatar" aria-label="Your profile">${esc(initials)}</a>
      <div class="who grow"><b>${esc(u.name)}</b><span>${role}</span></div>
      <button class="icon-btn" data-signout type="button" aria-label="Sign out" title="Sign out">${icon("logout")}</button></div>`;
    $("#top-user").innerHTML = u.role === "instructor" ? `${isReadOnly() ? '<span class="chip warn" title="Public demo account: nothing can be changed">Read-only demo</span>' : ""}
      <a href="/student/profile" class="avatar" aria-label="Your profile" title="${esc(u.name)}">${esc(initials)}</a>
      <button class="icon-btn" data-signout type="button" aria-label="Sign out" title="Sign out">${icon("logout")}</button>` : "";
    $("#top-links").innerHTML = "";
    document.querySelectorAll("[data-signout]").forEach((b) => b.addEventListener("click", signOut));
  } else {
    $("#sidebar-nav").innerHTML = "";
    $("#mobile-nav").innerHTML = "";
    $("#side-foot").innerHTML = "";
    $("#role-tabs").innerHTML = "";
    $("#top-user").innerHTML = "";
    $("#top-links").innerHTML = `<a href="/how-it-works">How it works</a><a href="/labs">Labs</a><a href="/login" class="keep">Sign in</a>`
      + (state.demo ? "" : `<a href="/signup" class="btn sm">Create account</a>`);
  }
}

function setThemeButton() {
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  const b = $("#theme-btn");
  b.innerHTML = icon(dark ? "sun" : "moon");
  b.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
}

function finishPage(view, route) {
  if (!isReadOnly()) return;
  if (route.access === "instructor" && !view.querySelector(".ro-note")) {
    view.insertAdjacentHTML("afterbegin", `<div class="banner ro-note">${icon("shield")}<span><b>Read-only demo.</b> You can open every
      instructor page, but grades and assignments can only be changed with the real instructor account.</span></div>`);
  }
  applyReadOnly(view);
}

async function render({ keepScroll = false, quiet = false } = {}) {
  const token = ++navToken;
  if (typeof cleanup === "function") { try { cleanup(); } catch { /* ignore */ } }
  cleanup = null;
  const route = match(location.pathname);
  const host = $("#view");
  if (!route) {
    renderShell();
    host.innerHTML = `<div class="view-inner"><section class="panel center"><div class="empty"><div class="empty-ico">${icon("alert")}</div>
      <h3>Page not found</h3><p>There's nothing at <code>${esc(location.pathname)}</code>.</p><a class="btn" href="${homePath()}">Go home</a></div></section></div>`;
    return;
  }
  const u = state.user;
  const here = location.pathname + location.search;
  if (route.access === "guest" && u) return navigate(homePath(), { replace: true });
  if (["user", "instructor"].includes(route.access) && !u) {
    return navigate(`/login?next=${encodeURIComponent(here)}`, { replace: true });
  }
  if (route.access === "instructor" && u.role !== "instructor") return navigate(homePath(), { replace: true });
  if (route.page === landing.home && u) return navigate(homePath(), { replace: true });

  document.title = `${route.title} · AutoGrader+`;
  renderShell();
  // Each navigation renders into its own container: if the user navigates again while this page is
  // still loading, the stale page writes into a detached element instead of over the new page.
  const view = document.createElement("div");
  view.className = "view-inner";
  const scrollY = window.scrollY;
  if (quiet) {
    try {
      const result = await route.page(view, route.params, new URLSearchParams(location.search));
      if (token !== navToken) { if (typeof result === "function") result(); return; }
      host.replaceChildren(view);
      cleanup = result;
      finishPage(view, route);
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
    finishPage(view, route);
  } catch (err) {
    if (token !== navToken) return;
    if (err.status === 401) { state.user = null; return navigate(`/login?next=${encodeURIComponent(here)}`, { replace: true }); }
    view.innerHTML = `<section class="panel"><div class="empty"><div class="empty-ico">${icon("alert")}</div><h3>Something went wrong</h3>
      <p>${esc(err.message)}</p><button class="btn" type="button" id="retry">${icon("refresh")} Try again</button></div></section>`;
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
$("#menu-btn").innerHTML = icon("menu");
$("#logo-side").innerHTML = icon("check");
$("#logo-top").innerHTML = icon("check");
$("#menu-btn").addEventListener("click", () => {
  const open = $("#app").classList.toggle("nav-open");
  $("#menu-btn").setAttribute("aria-expanded", String(open));
});
document.querySelector(".scrim").addEventListener("click", () => $("#app").classList.remove("nav-open"));
$("#theme-btn").addEventListener("click", () => {
  const dark = document.documentElement.getAttribute("data-theme") !== "dark";
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  try { localStorage.setItem("ag-theme", dark ? "dark" : "light"); } catch { /* ignore */ }
  setThemeButton();
});
setThemeButton();
window.addEventListener("auth-changed", renderShell);

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* offline shell is optional */ });
}

await refreshMe();
render();
