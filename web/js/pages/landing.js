import { $, api, esc, homePath, state, toast } from "../core.js";

const FEATURES = [
  ["5 AI specialists + judge", "Code quality, architecture, security, testing and DevOps agents review your GitHub repo in parallel; a judge calibrates the verdict.", "acc"],
  ["Real Docker sandbox", "Your Dockerfile is linted with 20+ rules, built and smoke-run in a locked-down container.", "cyan"],
  ["Hands-on labs", "Frontend editor, SQL playground, load-balancer and network labs: learn the whole stack in one place.", "green"],
  ["Explainable grades", "Every point comes with findings, file paths, fixes and a personal learning path.", "amber"],
  ["Live pipeline", "Watch the grading DAG run in real time over Server-Sent Events with a latency waterfall.", "acc"],
  ["Runs on containers", "Nginx load balancer → N stateless API replicas → PostgreSQL, all with docker compose.", "cyan"],
];

export async function home(view) {
  if (!state.health) state.health = await api("/api/health").catch(() => null);
  const h = state.health;
  view.innerHTML = `
  <section class="hero">
    <div class="hero-copy">
      <p class="kicker">CSL100 · Autograder, next version</p>
      <h1>Learn full-stack development.<br/><span class="grad">Graded by a team of AI agents.</span></h1>
      <p class="lead">Submit a GitHub repository and get a full, explainable review of the whole system (frontend, API,
      database, Docker, tests and security) in under a minute. Then practise each layer in interactive labs.</p>
      <div class="cta">
        <a class="btn lg" href="/signup">Create a student account</a>
        <a class="btn ghost lg" href="/login">Sign in</a>
        <a class="btn ghost lg" href="/labs">Try the labs</a>
      </div>
      ${state.demo ? `<p class="hint demo">Demo accounts: <code>student@autograder.local</code> / <code>student123</code> ·
        <code>instructor@autograder.local</code> / <code>instructor123</code></p>` : ""}
    </div>
    <div class="hero-art" aria-hidden="true">
      <div class="stack">
        <div class="layer l1"><b>Browser / mobile</b><span>HTML · CSS · JS · PWA</span></div>
        <div class="layer l2"><b>Nginx load balancer</b><span>round-robin · least-conn · sticky</span></div>
        <div class="layer l3"><b>API replicas ×3</b><span>FastAPI · SSE · containers</span></div>
        <div class="layer l4"><b>PostgreSQL</b><span>private network</span></div>
      </div>
    </div>
  </section>
  <section class="features">
    ${FEATURES.map(([t, d, c]) => `<article class="feature ${c}"><h3>${esc(t)}</h3><p>${esc(d)}</p></article>`).join("")}
  </section>
  <section class="panel flow">
    <h2>How grading works</h2>
    <ol class="steps">
      <li><b>Submit</b><span>GitHub URL (+ optional Dockerfile) for an assignment</span></li>
      <li><b>Clone & index</b><span>speculative shallow clone, one-pass index, secret redaction</span></li>
      <li><b>5 agents in parallel</b><span>each with its own evidence slice; Docker builds alongside</span></li>
      <li><b>Judge</b><span>cross-examines reports, bounded ±1.5 calibration</span></li>
      <li><b>Report & dashboard</b><span>score, findings, learning path, skill radar, leaderboard</span></li>
    </ol>
    <p class="hint">Engine: ${h ? `${h.llm_mode ? "LLM agents (" + esc(h.agent_model) + ")" : "deterministic heuristic agents (no API key configured)"} · ${esc(h.database.engine)} · replica ${esc(h.instance)}` : "…"}</p>
  </section>`;
}

function authLayout(view, title, sub, form) {
  view.innerHTML = `<section class="auth">
    <div class="auth-card panel">
      <span class="logo lg" aria-hidden="true">AG</span>
      <h1>${esc(title)}</h1><p class="hint">${sub}</p>
      ${form}
    </div></section>`;
}

function nextPath(query) {
  const n = query.get("next");
  return n && n.startsWith("/") && !n.startsWith("//") ? n : null;
}

export async function login(view, _p, query) {
  authLayout(view, "Welcome back", "Sign in to your AutoGrader+ account.", `
    <form id="login-form" class="form" novalidate>
      <label for="email">Email</label>
      <input id="email" type="email" autocomplete="username" required />
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password" required />
      <p class="error" id="err" role="alert"></p>
      <button class="btn block" type="submit">Sign in</button>
      ${state.demo ? `<div class="demo-btns"><span class="hint">Quick demo:</span>
        <button type="button" class="ghost sm" data-demo="student">Student</button>
        <button type="button" class="ghost sm" data-demo="instructor">Instructor</button></div>` : ""}
      <p class="hint center">New here? <a href="/signup">Create an account</a></p>
    </form>`);
  const submit = async (email, password) => {
    $("#err").textContent = "";
    try {
      const res = await api("/api/auth/login", { method: "POST", body: { email, password } });
      state.user = res.user;
      toast(`Signed in as ${res.user.name}`, "ok");
      window.__nav(nextPath(query) || homePath(), { replace: true });
    } catch (e) {
      $("#err").textContent = e.message;
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
  authLayout(view, "Create your account", "Student accounts can submit assignments, use the labs and join the leaderboard.", `
    <form id="signup-form" class="form" novalidate>
      <label for="name">Full name</label>
      <input id="name" autocomplete="name" required minlength="2" />
      <label for="entry">Entry number <span class="hint">(optional)</span></label>
      <input id="entry" placeholder="2024CS10001" autocomplete="off" />
      <label for="email">Email</label>
      <input id="email" type="email" autocomplete="email" required />
      <label for="password">Password <span class="hint">(min 8 characters)</span></label>
      <input id="password" type="password" autocomplete="new-password" required minlength="8" />
      ${state.signupCode ? `<label for="code">Class join code</label><input id="code" required autocomplete="off" />` : ""}
      <p class="error" id="err" role="alert"></p>
      <button class="btn block" type="submit">Create account</button>
      <p class="hint center">Already registered? <a href="/login">Sign in</a></p>
    </form>`);
  $("#signup-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    if ($("#password").value.length < 8) { $("#err").textContent = "Password must be at least 8 characters."; return; }
    try {
      const res = await api("/api/auth/signup", { method: "POST", body: {
        name: $("#name").value.trim(), entry_no: $("#entry").value.trim() || null, email: $("#email").value.trim(),
        password: $("#password").value, code: $("#code")?.value || null } });
      state.user = res.user;
      toast("Account created. Welcome!", "ok");
      window.__nav("/student/dashboard", { replace: true });
    } catch (err) {
      $("#err").textContent = err.message;
    }
  });
  $("#name").focus();
}
