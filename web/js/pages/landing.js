import { $, api, esc, homePath, icon, refreshMe, state, toast } from "../core.js";

// Landing page: one promise, one action (paste a link), then proof. The product pictures are built from real
// markup rather than screenshots, so they stay sharp at any size and follow the light/dark theme.
const SAMPLE_REPO = "https://github.com/dockersamples/example-voting-app";
const GITHUB = "https://github.com/roshanraj9136";

const STEPS = [
  ["Step 1", "Paste a GitHub link", "Any public repository: a website, an API, a full-stack app. No setup, no config file."],
  ["Step 2", "Five reviewers read it", "They work in parallel on code, architecture, security, tests and your Docker setup."],
  ["Step 3", "Fix what matters first", "A score, the exact files to change, and the practice that closes the gap. Submit again as often as you like."],
];

const AREAS = [
  ["code", "Code quality", "Structure, naming, duplication", "a-code"],
  ["layers", "Architecture", "Layers, coupling, data flow", "a-arch"],
  ["shield", "Security", "Secrets, injection, auth", "a-sec"],
  ["testCheck", "Testing", "Coverage, CI, what is untested", "a-test"],
  ["box", "Docker & DevOps", "Images, compose, delivery", "a-ops"],
];

// A real review, kept as markup so it stays sharp at any size and follows the theme.
const DEMO_AREAS = [["Code quality", 6.5, "a-code"], ["Architecture", 6.5, "a-arch"], ["Security", 4.0, "a-sec"],
  ["Testing", 1.0, "a-test"], ["Docker & DevOps", 7.5, "a-ops"]];
const DEMO_FIXES = [
  ["crit", "Hard-coded database credentials", "Move them to environment variables or a secret store.", "vote/app.py"],
  ["high", "No automated tests in CI", "The pipeline builds images but never runs a test suite.", ".github/workflows/"],
];

function tryForm(id) {
  return `<form class="try" id="${id}" novalidate>
    <label class="sr" for="${id}-url">GitHub repository link</label>
    <div class="try-box">${icon("git")}
      <input id="${id}-url" type="url" inputmode="url" autocomplete="url" spellcheck="false"
        placeholder="github.com/your-name/your-project" />
      <button class="btn" type="submit">Review my code</button>
    </div>
    <p class="try-note">Free, no account needed. <button type="button" class="linklike" data-sample>Use a sample project</button></p>
    <p class="error" role="alert"></p>
  </form>`;
}

function bindTry(view, id) {
  const form = view.querySelector(`#${id}`);
  if (!form) return;
  const input = form.querySelector("input");
  const err = form.querySelector(".error");
  const btn = form.querySelector("button[type=submit]");
  form.querySelector("[data-sample]").addEventListener("click", () => { input.value = SAMPLE_REPO; input.focus(); });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.textContent = "";
    const url = input.value.trim().replace(/^(?!https?:\/\/)(?=github\.com\/)/i, "https://");
    if (!/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/.test(url)) {
      err.textContent = "Paste a public GitHub link, like github.com/your-name/your-project";
      input.focus();
      return;
    }
    btn.disabled = true;
    btn.textContent = "Starting…";
    try {
      const r = await api("/api/try", { method: "POST", body: { repo_url: url } });
      await refreshMe();
      window.dispatchEvent(new Event("auth-changed"));
      window.__nav(`/jobs/${encodeURIComponent(r.job_id)}`);
    } catch (ex) {
      err.textContent = ex.status === 429 ? "You've used the free reviews for this hour. Please try again later." : ex.message;
      btn.disabled = false;
      btn.textContent = "Review my code";
    }
  });
}

function reportCard() {
  return `<div class="demo" aria-label="Example review">
    <div class="demo-h">${icon("git")}<code>dockersamples/example-voting-app</code>
      <span class="done">${icon("checkCircle")} Reviewed in 18s</span></div>
    <div class="demo-body">
      <div class="demo-main">
        <div class="demo-top"><span class="demo-score">52</span><span class="demo-of">out of 100</span><span class="demo-grade">Grade C-</span></div>
        <p class="demo-sum">Solid microservice split and a working Docker Compose setup. It is held back by a complete lack of
          automated tests and by credentials committed to the repository.</p>
        <div class="demo-fixes"><h4>Fix these first</h4>
          ${DEMO_FIXES.map(([sev, title, fix, file]) => `<div class="demo-fix"><span class="sev sev-${sev}">${sev === "crit" ? "critical" : "high"}</span>
            <b>${esc(title)}</b><span>${esc(fix)} <code>${esc(file)}</code></span></div>`).join("")}
        </div>
      </div>
      <div class="demo-side"><h4>Marks by area</h4>
        ${DEMO_AREAS.map(([label, v, cls]) => `<div class="demo-area ${cls}">
          <div class="row"><b>${label}</b><em>${v.toFixed(1)}</em></div>
          <div class="t"><span style="width:${v * 10}%"></span></div></div>`).join("")}
      </div>
    </div>
  </div>`;
}

function miniGradebook() {
  const rows = [["Diya Patel", ["69", "b"], ["74", "a"], ["72", "a"]], ["Ananya Rao", ["58", "c"], ["71", "b"], ["64", "b"]],
    ["Aarav Sharma", ["54", "c"], ["60", "c"], ["57", "c"]], ["Kabir Singh", ["49", "d"], null, ["49", "d"]],
    ["Rohan Gupta", null, null, null]];
  return `<div class="mini" aria-label="Example class view">
    <div class="mini-h">${icon("users")} Class overview · 8 students</div>
    <div class="mini-alert">${icon("alert")}<div><b>2 students submitted the same repository</b>
      <span>Lab 1 · group work, or copying?</span></div></div>
    <table><thead><tr><th>Student</th><th class="n">Lab 1</th><th class="n">Lab 2</th><th class="n">Average</th></tr></thead>
      <tbody>${rows.map(([name, ...cells]) => `<tr><td>${esc(name)}</td>${cells.map((c) =>
        `<td class="n"><span class="g ${c ? c[1] : "none"}">${c ? c[0] : "–"}</span></td>`).join("")}</tr>`).join("")}</tbody></table>
  </div>`;
}

function miniPlan() {
  const rows = [
    ["testCheck", "a-test", "Catch the off-by-one bug", "Testing lab · task 2", "Testing 1.0"],
    ["shield", "a-sec", "Keep secrets out of your code", "Security lab · task 2", "Security 4.0"],
    ["database", "a-code", "Make a query use an index", "Database lab · task 4", "Next up"],
  ];
  return `<div class="mini mini-plan" aria-label="Example practice plan">
    ${rows.map(([ico, cls, title, sub, why]) => `<div class="plan-row ${cls}">${icon(ico)}
      <div><b>${esc(title)}</b><span>${esc(sub)}</span></div><span class="why">${esc(why)}</span></div>`).join("")}
  </div>`;
}

export async function home(view) {
  const canTry = state.demo;
  const action = (id) => canTry ? tryForm(id)
    : `<div class="cta"><a class="btn" href="/signup">Create a free account</a><a class="ghost" href="/login">Sign in</a></div>`;
  view.innerHTML = `
  <section class="hero"><div class="l-wrap">
    <p class="hero-tag">${icon("sparkles")} Free AI code review for students</p>
    <h1>Find out what to fix in your project, in a minute.</h1>
    <p class="hero-lead">Paste a GitHub link. Five reviewers read your code and tell you your score, the exact files
      that need work, and what to practise next.</p>
    ${action("try-top")}
    ${reportCard()}
  </div></section>

  <section class="facts"><div class="l-wrap facts-row">
    <div><b>5</b><span>reviewers per project</span></div>
    <div><b>~1 min</b><span>link to full review</span></div>
    <div><b>Free</b><span>no card, no limits per class</span></div>
    <div><b>20</b><span>hands-on practice tasks</span></div>
  </div></section>

  <section class="l-sec plain"><div class="l-wrap">
    <div class="l-head center"><h2 class="l-h">How it works</h2>
      <p class="l-sub">No install, no config file, nothing to set up.</p></div>
    <ol class="steps3">${STEPS.map(([n, t, d]) => `<li><span class="n">${n}</span><h3>${t}</h3><p>${d}</p></li>`).join("")}</ol>
    <div class="areas">${AREAS.map(([ico, t, d, cls]) => `<div class="area ${cls}">${icon(ico)}<b>${t}</b><span>${d}</span></div>`).join("")}</div>
  </div></section>

  <section class="l-sec"><div class="l-wrap split">
    <div class="split-text a-sec">
      <span class="eyebrow">For teachers</span>
      <h2 class="l-h">See the whole class at a glance</h2>
      <p class="l-sub">Who needs help, who hasn't started, and who handed in the same repository as someone else.</p>
      <ul class="ticks">
        <li>${icon("check")}A gradebook with every attempt, exportable to Excel</li>
        <li>${icon("check")}Statistics per assignment, and the class's weakest area</li>
        <li>${icon("check")}Change a grade with a reason, or run the review again</li>
        <li>${icon("check")}Your own rubric: decide how much each area counts</li>
      </ul>
    </div>
    ${miniGradebook()}
  </div></section>

  <section class="l-sec"><div class="l-wrap split rev">
    <div class="split-text a-test">
      <span class="eyebrow">Practice</span>
      <h2 class="l-h">Practice chosen from your own code</h2>
      <p class="l-sub">The review knows your weakest area, so the labs start with the tasks that raise your score the most.</p>
      <ul class="ticks">
        <li>${icon("check")}Write tests and see which seeded bugs your suite catches</li>
        <li>${icon("check")}Write SQL against a real schema and read the query plan</li>
        <li>${icon("check")}Send traffic through a load balancer and watch it spread</li>
        <li>${icon("check")}Fix a Dockerfile against the same linter that grades you</li>
        <li>${icon("check")}Everything runs in your browser. Nothing to install.</li>
      </ul>
      <div class="row-btns top"><a class="ghost" href="/labs">Open the labs</a></div>
    </div>
    ${miniPlan()}
  </div></section>

  <section class="l-end"><div class="l-wrap narrow">
    <h2>See your score in a minute.</h2>
    <p>Free, and nothing to install.</p>
    ${action("try-bottom")}
  </div></section>

  <footer class="site-foot"><div class="l-wrap"><div class="foot-grid">
    <div class="foot-brand"><a href="/" class="brand"><span class="logo">${icon("check")}</span><span>AutoGrader<i>+</i></span></a>
      <p>AI code review and grading for full-stack student projects.</p></div>
    <nav aria-label="Product"><b>Product</b>${canTry ? `<a href="#try-top">Review my code</a>` : ""}<a href="/labs">Labs</a><a href="/login">Student sign-in</a><a href="/login/instructor">Instructor sign-in</a></nav>
    <nav aria-label="Project"><b>Project</b><a href="https://github.com/roshanraj9136/auto-grader" target="_blank" rel="noopener">Source code</a>
      <a href="/docs" target="_blank" rel="noopener">API reference</a></nav>
  </div><div class="foot-base"><span>© ${new Date().getFullYear()} AutoGrader+</span>
    <span>Built by <b><a href="${GITHUB}" target="_blank" rel="noopener">Roshan Raj</a></b></span></div></div></footer>`;
  bindTry(view, "try-top");
  bindTry(view, "try-bottom");
  view.querySelector('a[href="#try-top"]')?.addEventListener("click", (e) => {
    e.preventDefault();
    view.querySelector("#try-top-url")?.focus();
  });
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

const GOOGLE_MARK = `<svg viewBox="0 0 48 48" width="18" height="18" aria-hidden="true" focusable="false">
  <path fill="#4285F4" d="M45.1 24.5c0-1.6-.1-3.2-.4-4.7H24v8.9h11.8a10 10 0 0 1-4.4 6.6v5.5h7.1c4.2-3.8 6.6-9.5 6.6-16.3z"/>
  <path fill="#34A853" d="M24 46c6 0 11-2 14.6-5.2l-7.1-5.5c-2 1.3-4.5 2.1-7.5 2.1-5.8 0-10.7-3.9-12.4-9.1H4.3v5.7A22 22 0 0 0 24 46z"/>
  <path fill="#FBBC05" d="M11.6 28.3a13.2 13.2 0 0 1 0-8.6v-5.7H4.3a22 22 0 0 0 0 20l7.3-5.7z"/>
  <path fill="#EA4335" d="M24 9.5c3.3 0 6.2 1.1 8.5 3.3l6.3-6.3C35 2.9 30 1 24 1A22 22 0 0 0 4.3 14l7.3 5.7C13.3 13.4 18.2 9.5 24 9.5z"/>
</svg>`;

const AUTH_ERRORS = {
  google: "That didn't work. Please try signing in with Google again.",
  domain: () => `Use your college Google account${state.googleDomain ? ` (${state.googleDomain})` : ""}. Other accounts can't sign in here.`,
};

/** The "Continue with Google" button, when the server has Google sign-in configured. */
function googleButton(next) {
  if (!state.google) return "";
  const href = `/api/auth/google/start${next ? `?next=${encodeURIComponent(next)}` : ""}`;
  return `<a class="ghost block lg google-btn" href="${href}">${GOOGLE_MARK} Continue with Google</a>
    ${state.googleDomain ? `<p class="hint center">For ${esc(state.googleDomain)} accounts</p>` : ""}
    <div class="or"><span>or</span></div>`;
}

function authError(query) {
  const key = query?.get("error");
  const msg = AUTH_ERRORS[key];
  return msg ? `<p class="error" style="margin-bottom:14px">${esc(typeof msg === "function" ? msg() : msg)}</p>` : "";
}

function bindPasswordForm(view, query, { onDone } = {}) {
  const submit = async (email, password) => {
    $("#err").textContent = "";
    try {
      const res = await api("/api/auth/login", { method: "POST", body: { email, password } });
      state.user = res.user;
      toast(`Signed in as ${res.user.name.split(" ")[0]}`, "ok");
      onDone?.(res.user);
      window.__nav(nextPath(query) || homePath(), { replace: true });
    } catch (e) {
      $("#err").textContent = e.status === 401 ? "That email and password don't match. Check both and try again."
        : e.status === 429 ? "Too many attempts. Please wait a few minutes and try again."
        : e.message;
    }
  };
  $("#login-form").addEventListener("submit", (e) => {
    e.preventDefault();
    submit($("#email").value.trim(), $("#password").value);
  });
  $("#email").focus();
}

export async function login(view, _p, query) {
  const next = nextPath(query) || "";
  authLayout(view, "Student sign-in", "Your assignments, your feedback and your practice.", `
    ${authError(query)}
    ${googleButton(next)}
    <form id="login-form" class="form" novalidate>
      <label for="email">Email</label>
      <input id="email" type="email" autocomplete="username" required placeholder="you@college.edu" />
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password" required />
      <p class="error" id="err" role="alert"></p>
      <button class="btn block lg" type="submit">Sign in</button>
      ${state.signupOpen ? `<p class="hint center" style="margin-top:16px">New here? <a href="/signup">Create an account</a></p>` : ""}
    </form>
    <p class="auth-switch"><a href="/login/instructor">${icon("graduation")} I'm an instructor</a></p>`);
  bindPasswordForm(view, query);
}

export async function instructorLogin(view, _p, query) {
  authLayout(view, "Instructor sign-in", "The class overview, the gradebook and every student's work.", `
    ${authError(query)}
    <form id="login-form" class="form" novalidate>
      <label for="email">Email</label>
      <input id="email" type="email" autocomplete="username" required placeholder="you@college.edu" />
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password" required />
      <p class="error" id="err" role="alert"></p>
      <button class="btn block lg" type="submit">Sign in</button>
    </form>
    <p class="hint center" style="margin-top:16px">Instructor access is given by an existing instructor.
      It can't be created here.</p>
    <p class="auth-switch"><a href="/login">${icon("user")} I'm a student</a></p>`);
  bindPasswordForm(view, query);
}

export async function signup(view, _p, query) {
  if (!state.signupOpen) {
    authLayout(view, "Accounts are not open here", state.google
      ? `Sign in with your college Google account instead.`
      : "Ask your instructor to add you to the class.",
      `${googleButton("")}<div class="row-btns" style="margin-top:4px"><a class="ghost block" href="/login">Back to sign-in</a></div>`);
    return;
  }
  authLayout(view, "Create your account", "Join your class to submit assignments and track your progress.", `
    ${authError(query)}
    ${googleButton("")}
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
      <p class="hint center" style="margin-top:16px">Already have an account? <a href="/login">Sign in</a></p>
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
