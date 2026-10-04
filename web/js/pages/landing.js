import { $, api, esc, homePath, icon, state, toast } from "../core.js";

const FEATURES = [
  ["sparkles", "Feedback in about a minute", "Paste your GitHub link and get a score, what you did well, and exactly what to fix next, with file names."],
  ["target", "Graded like a real project", "Your whole app is reviewed: code quality, structure, security, tests, and your Docker setup."],
  ["bulb", "A learning path made for you", "Every result ends with the topics to learn next, so each submission makes you a better developer."],
  ["flask", "Hands-on labs", "Practise frontend, SQL, load balancers, networks and Dockerfiles right in your browser."],
  ["trophy", "Track your progress", "Watch your scores grow, earn XP, level up and see where you stand on the class leaderboard."],
  ["smartphone", "Works on your phone", "Check results anywhere. Install it on your phone like an app."],
];

const LABS = [
  ["frontend", "code", "Frontend", "HTML, CSS & JS"],
  ["database", "database", "Databases", "SQL & indexes"],
  ["loadbalancer", "network", "Load balancers", "Spread the traffic"],
  ["network", "globe", "Networks", "How requests travel"],
  ["docker", "box", "Docker", "Fix a Dockerfile"],
];

export async function home(view) {
  view.innerHTML = `
  <section class="l-hero">
    <span class="badge">${icon("graduation")} CSL100 · the next Autograder</span>
    <h1>Build real apps.<br/><em>Get feedback like a senior developer.</em></h1>
    <p class="lead">Submit your GitHub project and AutoGrader+ reviews the whole thing, from frontend to database to Docker,
      then tells you what to learn next.</p>
    <div class="cta">
      <a class="btn lg" href="/signup">Create free account ${icon("arrowRight")}</a>
      <a class="ghost lg" href="/login">Sign in</a>
    </div>
    ${state.demo ? `<p class="demo">${icon("sparkles")} Try it: <code>student@autograder.local</code> / <code>student123</code></p>` : ""}
    <div class="trust"><span>${icon("checkCircle")} Free for students</span><span>${icon("checkCircle")} Results in about a minute</span>
      <span>${icon("checkCircle")} Any language</span></div>
    <div class="preview" aria-hidden="true">
      <div class="preview-bar"><i></i><i></i><i></i></div>
      <div class="preview-body">
        <div class="ring g-b" style="--p:76%;--size:120px"><span>76<small>B</small></span></div>
        <div>
          <b style="font-size:1.1rem">Great progress on your REST API!</b>
          <p class="hint" style="margin:4px 0 0">Your routes are well organised and your Dockerfile is solid. Next: add tests and hash passwords.</p>
          <div class="pv-dims"><div><b>8.1</b>Code</div><div><b>7.9</b>Structure</div><div><b>6.2</b>Security</div><div><b>5.4</b>Testing</div><div><b>8.4</b>Docker</div></div>
        </div>
      </div>
    </div>
  </section>
  <section class="l-section alt"><div class="l-inner">
    <div class="l-title"><h2>Everything you need to level up</h2><p>Made for students learning full-stack development.</p></div>
    <div class="features">${FEATURES.map(([ico, t, d]) => `<article class="feature"><div class="f-ico">${icon(ico)}</div><h3>${esc(t)}</h3><p>${esc(d)}</p></article>`).join("")}</div>
  </div></section>
  <section class="l-section white"><div class="l-inner">
    <div class="l-title"><h2>How it works</h2><p>Three steps, no setup.</p></div>
    <div class="steps3">
      <div><h3>Pick an assignment</h3><p>See the brief and exactly what will be checked.</p></div>
      <div><h3>Paste your GitHub link</h3><p>We review your code while you wait, usually in under a minute.</p></div>
      <div><h3>Improve and resubmit</h3><p>Follow the fixes, resubmit, and watch your score go up.</p></div>
    </div>
  </div></section>
  <section class="l-section alt"><div class="l-inner">
    <div class="l-title"><h2>Practise in the labs</h2><p>Learn each part of the stack hands-on. No install needed.</p></div>
    <div class="lab-strip">${LABS.map(([id, ico, t, d]) => `<a href="/labs/${id}">${icon(ico)}<b>${esc(t)}</b><span>${esc(d)}</span></a>`).join("")}</div>
  </div></section>
  <section class="l-section alt" style="padding-top:0"><div class="cta-band">
    <h2>Ready to see how your project scores?</h2><p>Create your account with your class join code and submit your first repo today.</p>
    <a class="btn lg" href="/signup">Get started ${icon("arrowRight")}</a>
  </div></section>
  <footer class="l-footer"><div class="l-inner"><span>AutoGrader+ · CSL100 group project</span>
    <span><a href="/labs">Labs</a> · <a href="/login">Sign in</a></span></div></footer>`;
}

function authLayout(view, title, sub, form) {
  view.innerHTML = `<section class="auth">
    <div class="auth-card panel">
      <span class="logo lg">${icon("graduation")}</span>
      <h1>${esc(title)}</h1><p class="hint">${sub}</p>
      ${form}
    </div></section>`;
}

function nextPath(query) {
  const n = query.get("next");
  return n && n.startsWith("/") && !n.startsWith("//") ? n : null;
}

export async function login(view, _p, query) {
  authLayout(view, "Welcome back", "Sign in to see your assignments and feedback.", `
    <form id="login-form" class="form" novalidate>
      <label for="email">Email</label>
      <input id="email" type="email" autocomplete="username" required placeholder="you@college.edu" />
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password" required />
      <p class="error" id="err" role="alert"></p>
      <button class="btn block lg" type="submit">Sign in</button>
      ${state.demo ? `<div class="divider">or try a demo account</div><div class="demo-btns">
        <button type="button" class="ghost sm" data-demo="student">${icon("user")} Student</button>
        <button type="button" class="ghost sm" data-demo="instructor">${icon("users")} Instructor</button></div>` : ""}
      <p class="hint center" style="margin-top:18px">New here? <a href="/signup">Create an account</a></p>
    </form>`);
  const submit = async (email, password) => {
    $("#err").textContent = "";
    try {
      const res = await api("/api/auth/login", { method: "POST", body: { email, password } });
      state.user = res.user;
      toast(`Welcome back, ${res.user.name.split(" ")[0]}!`, "ok");
      window.__nav(nextPath(query) || homePath(), { replace: true });
    } catch (e) {
      $("#err").textContent = e.status === 401 ? "That email and password don't match. Try again." : e.message;
    }
  };
  $("#login-form").addEventListener("submit", (e) => {
    e.preventDefault();
    submit($("#email").value.trim(), $("#password").value);
  });
  view.querySelectorAll("[data-demo]").forEach((b) => b.addEventListener("click", () => {
    const who = b.dataset.demo;
    submit(`${who}@autograder.local`, `${who}123`);
  }));
  $("#email").focus();
}

export async function signup(view) {
  authLayout(view, "Create your account", "Join your class to submit assignments and track your progress.", `
    <form id="signup-form" class="form" novalidate>
      <label for="name">Full name</label>
      <input id="name" autocomplete="name" required minlength="2" placeholder="Aarav Sharma" />
      <label for="entry">Entry number <span class="muted">(optional)</span></label>
      <input id="entry" placeholder="2024CS10001" autocomplete="off" />
      <label for="email">Email</label>
      <input id="email" type="email" autocomplete="email" required placeholder="you@college.edu" />
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="new-password" required minlength="8" placeholder="At least 8 characters" />
      ${state.signupCode ? `<label for="code">Class join code</label><input id="code" required autocomplete="off" placeholder="Ask your instructor" />` : ""}
      <p class="error" id="err" role="alert"></p>
      <button class="btn block lg" type="submit">Create account</button>
      <p class="hint center" style="margin-top:18px">Already have an account? <a href="/login">Sign in</a></p>
    </form>`);
  $("#signup-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    if ($("#password").value.length < 8) { $("#err").textContent = "Your password needs at least 8 characters."; return; }
    try {
      const res = await api("/api/auth/signup", { method: "POST", body: {
        name: $("#name").value.trim(), entry_no: $("#entry").value.trim() || null, email: $("#email").value.trim(),
        password: $("#password").value, code: $("#code")?.value || null } });
      state.user = res.user;
      toast(`Welcome to AutoGrader+, ${res.user.name.split(" ")[0]}!`, "ok");
      window.__nav("/student/dashboard", { replace: true });
    } catch (err) {
      $("#err").textContent = err.status === 403 ? "That class join code isn't right. Check with your instructor." : err.message;
    }
  });
  $("#name").focus();
}
