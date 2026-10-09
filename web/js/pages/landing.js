import { $, api, esc, homePath, icon, refreshMe, state, toast } from "../core.js";

// Landing page, modelled on how code-review and grading products present themselves: one clear promise, one
// action (paste a link), real screenshots, three steps, then what each kind of user gets.
const SAMPLE_REPO = "https://github.com/dockersamples/example-voting-app";
const GITHUB = "https://github.com/roshanraj9136";

const STEPS = [
  ["git", "Paste your GitHub link", "Any public repository: a website, an API, a full-stack app."],
  ["zap", "Watch the review happen", "Five AI reviewers check your code, design, security, tests and Docker setup at the same time."],
  ["checkCircle", "Fix it and score higher", "You get a score, the exact files to fix and how to fix them. Submit again and watch it go up."],
];

const AREAS = [["code", "Code quality", "a-code"], ["layers", "Architecture", "a-arch"], ["shield", "Security", "a-sec"],
  ["testCheck", "Testing", "a-test"], ["box", "Docker & DevOps", "a-ops"]];

function tryForm(id) {
  return `<form class="try" id="${id}" novalidate>
    <label class="sr" for="${id}-url">GitHub repository link</label>
    <div class="try-box">${icon("git")}
      <input id="${id}-url" type="url" inputmode="url" autocomplete="url" spellcheck="false"
        placeholder="https://github.com/your-name/your-project" />
      <button class="btn lg" type="submit">Review my code</button>
    </div>
    <p class="try-note"><span>Free. No sign-up needed.</span> <button type="button" class="linklike" data-sample>Try it with a sample project</button></p>
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
    const url = input.value.trim();
    if (!/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/.test(url)) {
      err.textContent = "Paste a public GitHub link, like https://github.com/your-name/your-project";
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

function shot(name, alt) {
  return `<figure class="shot"><div class="shot-bar" aria-hidden="true"><i></i><i></i><i></i></div>
    <img src="/img/${name}.webp" alt="${esc(alt)}" width="1600" height="1000" loading="lazy" decoding="async" /></figure>`;
}

export async function home(view) {
  const canTry = state.demo;
  view.innerHTML = `
  <section class="hero"><div class="l-wrap">
    <p class="hero-tag">${icon("sparkles")} AI code review for student projects</p>
    <h1>Get your code reviewed in&nbsp;<span class="hl">a minute</span>.</h1>
    <p class="hero-lead">Paste a GitHub link. Five AI reviewers check your project and tell you your score, what is wrong, and exactly how to fix it.</p>
    ${canTry ? tryForm("try-top") : `<div class="cta"><a class="btn lg" href="/signup">Create a free account</a><a class="ghost lg" href="/login">Sign in</a></div>`}
    <div class="hero-shot">${shot("feedback", "A review: score 58 out of 100, marks for each area and the top things to fix")}</div>
  </div></section>

  <section class="facts"><div class="l-wrap facts-row">
    <div><b>5</b><span>AI reviewers on every project</span></div>
    <div><b>~1 min</b><span>from link to full review</span></div>
    <div><b>100%</b><span>free for students</span></div>
    <div><b>5</b><span>hands-on labs to practise</span></div>
  </div></section>

  <section class="l-sec"><div class="l-wrap">
    <h2 class="l-h center">Three steps. That's it.</h2>
    <ol class="steps3">${STEPS.map(([ico, t, d], i) => `<li><span class="step-n">${i + 1}</span><span class="step-ico">${icon(ico)}</span>
      <h3>${t}</h3><p>${d}</p></li>`).join("")}</ol>
    <div class="areas" aria-label="What gets checked">${AREAS.map(([ico, t, cls]) => `<span class="area ${cls}">${icon(ico)}${t}</span>`).join("")}</div>
  </div></section>

  <section class="l-sec feature"><div class="l-wrap split">
    <div class="split-text">
      <p class="eyebrow a-code">For students</p>
      <h2 class="l-h">Know exactly what to fix next</h2>
      <ul class="ticks">
        <li>${icon("check")}A score out of 100 and a mark for each part of your project</li>
        <li>${icon("check")}The top problems first, with the file name and the fix</li>
        <li>${icon("check")}Topics to learn next, picked from your own code</li>
        <li>${icon("check")}Submit again as often as you like: your best score counts</li>
      </ul>
    </div>
    ${shot("student-dashboard", "Student dashboard with the next assignment, the last result and progress")}
  </div></section>

  <section class="l-sec feature alt"><div class="l-wrap split rev">
    <div class="split-text">
      <p class="eyebrow a-sec">For teachers</p>
      <h2 class="l-h">See the whole class at a glance</h2>
      <ul class="ticks red">
        <li>${icon("check")}Who needs help, who hasn't started, and who may have copied</li>
        <li>${icon("check")}A gradebook and statistics for every assignment</li>
        <li>${icon("check")}Change a grade with a reason, or grade a submission again</li>
        <li>${icon("check")}Set your own rubric and deadline; export grades to Excel</li>
      </ul>
    </div>
    ${shot("instructor-overview", "Teacher overview with the students who need attention and the grade distribution")}
  </div></section>

  <section class="l-sec feature"><div class="l-wrap split">
    <div class="split-text">
      <p class="eyebrow a-test">Practice</p>
      <h2 class="l-h">Practise every layer of a full-stack app</h2>
      <ul class="ticks green">
        <li>${icon("check")}Frontend: HTML, CSS and JavaScript with a live preview</li>
        <li>${icon("check")}Databases: write SQL and see how indexes speed it up</li>
        <li>${icon("check")}Networks, load balancers and Docker, hands-on</li>
        <li>${icon("check")}Everything runs in your browser. Nothing to install.</li>
      </ul>
      <div class="row-btns"><a class="ghost" href="/labs">Open the labs</a></div>
    </div>
    ${shot("lab-sql", "SQL lab with a query editor, the tables and tasks")}
  </div></section>

  <section class="l-end"><div class="l-wrap end-box">
    <h2>Find out your score in a minute.</h2>
    ${canTry ? tryForm("try-bottom") : `<div class="cta"><a class="btn lg" href="/signup">Create a free account</a></div>`}
  </div></section>

  <footer class="site-foot"><div class="l-wrap foot-grid">
    <div class="foot-brand"><a href="/" class="brand"><span class="logo">${icon("check")}</span><span>AutoGrader<i>+</i></span></a>
      <p>AI code review and grading for full-stack student projects.</p>
      <p class="made">Built by <a href="${GITHUB}" target="_blank" rel="noopener">Roshan Raj</a></p></div>
    <nav aria-label="Product"><b>Product</b>${canTry ? `<a href="#try-top">Review my code</a>` : ""}<a href="/labs">Labs</a><a href="/login">Sign in</a></nav>
    <nav aria-label="Project"><b>Project</b><a href="https://github.com/roshanraj9136/auto-grader" target="_blank" rel="noopener">Source code</a>
      <a href="/docs" target="_blank" rel="noopener">API</a></nav>
  </div><div class="l-wrap foot-base"><span>© ${new Date().getFullYear()} AutoGrader+</span></div></footer>`;
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

export async function login(view, _p, query) {
  authLayout(view, "Sign in", "Students see their assignments and feedback. Instructors see the class.", `
    <form id="login-form" class="form" novalidate>
      <label for="email">Email</label>
      <input id="email" type="email" autocomplete="username" required placeholder="you@college.edu" />
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password" required />
      <p class="error" id="err" role="alert"></p>
      <button class="btn block lg" type="submit">Sign in</button>
      ${state.demo ? "" : `<p class="hint" style="margin-top:16px">New here? <a href="/signup">Create a student account</a></p>`}
      ${state.demo ? `<div class="demo-box"><p>Or look around as a student, no account needed:</p><div class="demo-btns one">
        <button type="button" class="ghost" data-demo="student">${icon("user")} Open the student view</button></div></div>` : ""}
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
  if (state.demo) {
    authLayout(view, "Sign-up is off on this demo", "This public demo has ready-made accounts instead.",
      `<div class="row-btns" style="margin-top:18px"><a class="btn lg" href="/login">Open the demo accounts</a></div>`);
    return;
  }
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
