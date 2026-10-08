import { $, api, esc, homePath, icon, state, toast } from "../core.js";

const LABS = [
  ["frontend", "code", "Frontend", "Edit HTML, CSS and JS with a live preview and DOM checks."],
  ["database", "database", "Databases", "Write SQL joins and aggregates, then watch an index change the query plan."],
  ["loadbalancer", "network", "Load balancers", "Fire requests at round-robin, least-connections and sticky routing."],
  ["network", "globe", "Networks", "Measure round trips, trace proxy headers and break down a request."],
  ["docker", "box", "Docker", "Fix a Dockerfile until the linter has nothing left to say."],
];

const SAMPLE = [["Code quality", 8.1, "g-a"], ["Architecture", 7.9, "g-a"], ["Security", 6.2, "g-c"], ["Testing", 5.4, "g-c"], ["Docker", 8.4, "g-a"]];

export async function home(view) {
  view.innerHTML = `
  <section class="l-hero"><div class="l-wrap">
    <div>
      <h1>Push your project. Get it marked like a code review.</h1>
      <p class="lead">AutoGrader+ reads your whole GitHub repo, from the frontend to the Dockerfile, and gives back a score,
        the exact files to fix, and what to learn next. Usually in under a minute.</p>
      <div class="cta">
        <a class="btn lg" href="/signup">Create a student account</a>
        <a class="ghost lg" href="/login">Sign in</a>
      </div>
      ${state.demo ? `<p class="demo">Just looking? Sign in with <code>student@autograder.local</code> and <code>student123</code>.</p>` : ""}
    </div>
    <figure class="sheet-demo" aria-label="Example feedback for a student's REST API: 76 out of 100, grade B">
      <div class="sd-top"><code>aarav-s/campus-events-api</code><span>commit 3f9c2a1</span></div>
      <div class="sd-score"><b>76</b><span>/100</span><strong>Grade B</strong></div>
      <div class="sd-rows">${SAMPLE.map(([k, v, g]) => `<div class="${g}"><span>${k}</span><i style="--w:${v * 10}%"></i><b>${v}</b></div>`).join("")}</div>
      <div class="sd-fix"><p>Fix this first</p><b><span class="hl">Hash passwords</span> before saving them</b> in <code>src/routes/auth.js</code></div>
    </figure>
  </div></section>

  <section class="l-sec"><div class="l-wrap">
    <h2 class="l-h">One course, two views</h2>
    <p class="l-lead">Students see what to do next. Instructors see who needs help.</p>
    <div class="roles">
      <div class="role">
        <h3>For students</h3><p class="role-who">Submit, read the feedback, improve.</p>
        <ul>
          <li>${icon("check")}<span>Every assignment lists exactly what will be checked and how much each part counts.</span></li>
          <li>${icon("check")}<span>Feedback names the file and the fix, not just a number.</span></li>
          <li>${icon("check")}<span>Resubmit as often as you like. Your best score counts.</span></li>
          <li>${icon("check")}<span>Practise SQL, load balancers, networks and Docker in the labs.</span></li>
        </ul>
        <div class="row-btns"><a class="btn" href="/signup">Create a student account</a></div>
      </div>
      <div class="role teach">
        <h3>For instructors</h3><p class="role-who">Set the work, then watch the class.</p>
        <ul>
          <li>${icon("check")}<span>Publish an assignment with its own rubric weights and deadline.</span></li>
          <li>${icon("check")}<span>See who hasn't started and who is scoring below 50, on one screen.</span></li>
          <li>${icon("check")}<span>Spot the same repository submitted by more than one student.</span></li>
          <li>${icon("check")}<span>Export the gradebook as a CSV whenever you need it.</span></li>
        </ul>
        <div class="row-btns"><a class="ghost" href="/login">Sign in as an instructor</a></div>
      </div>
    </div>
  </div></section>

  <section class="l-sec"><div class="l-wrap">
    <h2 class="l-h">How a submission is marked</h2>
    <p class="l-lead">The same four steps run for every repository, whether it's for an assignment or just practice.</p>
    <ol class="steps4">
      <li><h3>Download</h3><p>Your repo is cloned at the branch or commit you chose.</p></li>
      <li><h3>Read</h3><p>Languages, tests, Dockerfiles and config files are found and indexed.</p></li>
      <li><h3>Review</h3><p>Five reviewers check code quality, structure, security, tests and Docker at the same time.</p></li>
      <li><h3>Judge</h3><p>A judge compares their notes, sets the score and writes your next steps.</p></li>
    </ol>
  </div></section>

  <section class="l-sec"><div class="l-wrap">
    <h2 class="l-h">Practise each layer in the labs</h2>
    <p class="l-lead">Everything runs in your browser. Sign in to save your progress and earn XP.</p>
    <ul class="lab-rows">${LABS.map(([id, ico, t, d]) => `<li><a href="/labs/${id}">${icon(ico)}<b>${esc(t)}</b><span>${esc(d)}</span><span class="go">Open lab</span></a></li>`).join("")}</ul>
  </div></section>

  <section class="l-end"><div class="l-wrap">
    <div><h2>Your first feedback is a minute away.</h2><p>Sign up with your class join code and submit a repository.</p></div>
    <a class="btn lg" href="/signup">Create a student account</a>
  </div></section>
  <footer class="l-footer"><div class="l-wrap"><span>AutoGrader+, a CSL100 group project</span>
    <nav aria-label="Footer"><a href="/labs">Labs</a><a href="/login">Sign in</a></nav></div></footer>`;
}

function authLayout(view, title, sub, form) {
  view.innerHTML = `<section class="auth">
    <div class="auth-card panel">
      <span class="logo lg">${icon("check")}</span>
      <h1>${esc(title)}</h1><p class="hint">${sub}</p>
      ${form}
    </div></section>`;
}

function nextPath(query) {
  const n = query.get("next");
  return n && n.startsWith("/") && !n.startsWith("//") ? n : null;
}

export async function login(view, _p, query) {
  authLayout(view, "Sign in", "Students see their assignments and feedback. Instructors see the class.", `
    <form id="login-form" class="form" novalidate>
      <label for="email">Email</label>
      <input id="email" type="email" autocomplete="username" required placeholder="you@college.edu" />
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password" required />
      <p class="error" id="err" role="alert"></p>
      <button class="btn block lg" type="submit">Sign in</button>
      <p class="hint" style="margin-top:16px">New here? <a href="/signup">Create a student account</a></p>
      ${state.demo ? `<div class="demo-box"><p>Or look around with a demo account:</p><div class="demo-btns">
        <button type="button" class="ghost" data-demo="student">${icon("user")} Student view</button>
        <button type="button" class="ghost" data-demo="instructor">${icon("users")} Instructor view</button></div></div>` : ""}
    </form>`);
  const submit = async (email, password) => {
    $("#err").textContent = "";
    try {
      const res = await api("/api/auth/login", { method: "POST", body: { email, password } });
      state.user = res.user;
      toast(`Signed in as ${res.user.name.split(" ")[0]}`, "ok");
      window.__nav(nextPath(query) || homePath(), { replace: true });
    } catch (e) {
      $("#err").textContent = e.status === 401 ? "That email and password don't match. Check both and try again." : e.message;
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
      ${state.signupCode ? `<label for="code">Class join code</label><input id="code" required autocomplete="off" placeholder="Your instructor shares this" />` : ""}
      <p class="error" id="err" role="alert"></p>
      <button class="btn block lg" type="submit">Create account</button>
      <p class="hint" style="margin-top:16px">Already have an account? <a href="/login">Sign in</a></p>
    </form>`);
  $("#signup-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    if ($("#password").value.length < 8) { $("#err").textContent = "Use at least 8 characters for your password."; return; }
    try {
      const res = await api("/api/auth/signup", { method: "POST", body: {
        name: $("#name").value.trim(), entry_no: $("#entry").value.trim() || null, email: $("#email").value.trim(),
        password: $("#password").value, code: $("#code")?.value || null } });
      state.user = res.user;
      toast(`Account created. Welcome, ${res.user.name.split(" ")[0]}!`, "ok");
      window.__nav("/student/dashboard", { replace: true });
    } catch (err) {
      $("#err").textContent = err.status === 403 ? "That class join code isn't right. Check it with your instructor." : err.message;
    }
  });
  $("#name").focus();
}
