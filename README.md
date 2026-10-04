# AutoGrader+

A **full-stack learning platform** built around a multi-agent grader. Students submit a **GitHub repo** (optionally with a **Dockerfile**) for an assignment and get a full, explainable report. Then they practise each layer of the stack in hands-on labs that run on the platform's own infrastructure.

- **Grading engine**: five specialist LLM agents (Code Quality, Architecture, Security, Testing, DevOps & Docker) review the project in parallel. A **Judge agent** cross-examines their reports, calibrates the scores and writes the verdict, top priorities and a learning path. It runs as a latency-optimised DAG with live progress over Server-Sent Events.
- **Students**: dashboard (score history, five-dimension skill radar, XP and level, deadlines, learning path), assignments, submission history, leaderboard, profile.
- **Labs**:
  - Frontend: live HTML/CSS/JS editor in a sandboxed preview, with DOM checks.
  - Databases: SQL playground with query plans and indexes.
  - Load balancers: round-robin vs least-connections vs sticky routing, across real replicas.
  - Networks: RTT and jitter, proxy headers, Server-Timing breakdown.
  - Containers: Dockerfile linter.
- **Instructors**: publish assignments with rubric weights and deadlines, see class overview analytics (grade distribution, weakest dimensions, completion), flag shared repos, export the gradebook as CSV.
- **Runs on containers**: Nginx load balancer → 3 stateless API replicas → PostgreSQL on a private network. The web app is responsive and installs as a mobile app (PWA).

Design details are in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**. The slide deck is `docs/AutoGrader.pptx`, regenerated with `python docs/build_slides.py`.

## Quick start: Windows, no Docker

```powershell
.\scripts\start.ps1            # creates .venv, installs deps, serves http://localhost:8000
.\scripts\start.ps1 -Lan       # also reachable by classmates on the same network
```

Manual equivalent (any OS):

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # Windows: .\.venv\Scripts\pip
cp .env.example .env                                                # optional: add ANTHROPIC_API_KEY
.venv/bin/python -m uvicorn app.main:app --port 8000
```

On the first run the server creates the demo accounts below plus four sample assignments, and stores data in SQLite.

| Role | Email | Password |
|---|---|---|
| Student | `student@autograder.local` | `student123` |
| Instructor | `instructor@autograder.local` | `instructor123` |

Without `ANTHROPIC_API_KEY` the system runs in **heuristic mode**: the same pipeline, with deterministic scorers in place of LLM calls.

## Full stack with Docker Compose (load balancer + 3 replicas + PostgreSQL)

```bash
docker compose up --build                     # http://localhost:8080
docker compose up -d --scale api=5            # scale the API tier; nginx re-resolves replicas by itself
# opt-in build/run sandbox (mounts docker.sock; use a dedicated VM, see security notes):
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml up --build
```

```
browser ──► nginx :8080 ──┬─► api replica 1 ─┐
  (sticky / rr / least)   ├─► api replica 2 ─┼─► postgres (internal network, no internet)
                          └─► api replica 3 ─┘    + shared /data volume (reports, cache)
```

The port is published on `127.0.0.1` only. To share it on your LAN, set `AUTOGRADER_BIND=0.0.0.0` **and** `AUTOGRADER_DEMO_SEED=0` with a real `AUTOGRADER_INSTRUCTOR_EMAIL`/`AUTOGRADER_INSTRUCTOR_PASSWORD` in `.env`.

On Windows, Docker Desktop needs WSL 2 (`wsl --install`, then reboot) and CPU virtualisation enabled.

## Pages

| Path | Who | What |
|---|---|---|
| `/student/dashboard` | student | stats, score history, skill radar, deadlines, learning path |
| `/student/assignments`, `/student/assignment/:id` | student | brief, rubric, submit, live grading, attempts |
| `/student/submissions`, `/student/leaderboard`, `/student/profile` | student | history, class ranking, account |
| `/labs`, `/labs/{frontend,database,loadbalancer,network,docker}` | everyone | hands-on labs (sign in to save progress) |
| `/grader`, `/jobs/:id` | signed in | free-form practice grading with a custom rubric |
| `/instructor/dashboard`, `/instructor/assignments`, `/instructor/students` | instructor | analytics, assignment management, gradebook |
| `/system` | everyone | health, replica, DB, per-stage p50/p95 latency |

## API (selected)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/signup`, `/api/auth/login`, `/api/auth/logout` | accounts (HttpOnly session cookie) |
| GET | `/api/student/dashboard` | everything the dashboard shows |
| GET/POST/PUT/DELETE | `/api/assignments[/{id}]` | list/detail (all), create/update/delete (instructor) |
| POST | `/api/assignments/{id}/submit` | grade a repo with the assignment's rubric, returns `202 {job_id}` |
| POST | `/api/grade`, `/api/grade/upload` | practice grading (JSON / multipart with Dockerfile) |
| GET | `/api/jobs/{id}/events` | SSE stream: stage start/end, agent results, verdict |
| GET | `/api/jobs/{id}/report[.html,.md,.json]` | report (owner, instructor or API token) |
| GET | `/api/leaderboard`, `/api/instructor/overview`, `/api/instructor/gradebook.csv` | rankings and analytics |
| POST | `/api/lab/sql`, `/api/lab/dockerfile` | server-verified lab tasks |
| GET | `/lb/{rr,least,hash}/whoami`, `/api/lab/network` | load-balancer and network labs |
| GET | `/api/health`, `/api/metrics` | health (replica, DB, mode) and latency metrics |

For scripts and CI, set `AUTOGRADER_API_TOKEN` and send `Authorization: Bearer <token>`:

```bash
curl -H "Authorization: Bearer $TOKEN" -F repo_url=https://github.com/dockersamples/example-voting-app \
     -F dockerfile=@Dockerfile http://localhost:8000/api/grade/upload
```

Interactive OpenAPI docs are served at `/docs`.

## Configuration (env / `.env`)

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Enables LLM mode |
| `AUTOGRADER_AGENT_MODEL` / `AUTOGRADER_JUDGE_MODEL` | `claude-sonnet-5-5` | Model tiering |
| `AUTOGRADER_DATABASE_URL` | SQLite in the work dir | `postgresql://user:pass@host:5432/db` for PostgreSQL |
| `AUTOGRADER_REQUIRE_LOGIN` | 1 | Grading needs a session (or the API token) |
| `AUTOGRADER_DEMO_SEED` | 1 | Demo accounts + sample assignments. Setting 0 also **removes** the demo accounts |
| `AUTOGRADER_INSTRUCTOR_EMAIL` / `_PASSWORD` | none | Real instructor account created at startup |
| `AUTOGRADER_SIGNUP_CODE` | none | Class join code required for self sign-up |
| `AUTOGRADER_COOKIE_SECURE` | 0 | Set to 1 behind HTTPS |
| `AUTOGRADER_API_TOKEN` | none | Bearer token for API/CI submissions |
| `AUTOGRADER_AGENT_TIMEOUT` / `AUTOGRADER_JUDGE_TIMEOUT` | 120 / 150 s | Deadline, then heuristic fallback |
| `AUTOGRADER_MAX_CONCURRENT_JOBS` | 2 | Admission control per replica |
| `AUTOGRADER_ENABLE_DOCKER` | 1 | 0 = static Dockerfile lint only |

## Latency benchmark

```bash
python scripts/latency_benchmark.py https://github.com/dockersamples/example-voting-app
```

The benchmark runs the real pipeline with a **simulated** LLM latency model. Sample result: 27.5 s wall-clock vs 75.5 s sequential, a **2.74× speed-up**. The measured critical path is `clone → index → agent:security → judge → report`.

## Project layout

```
app/
  main.py            REST + SSE API, auth guards, CSRF/CSP headers, SPA fallback, replica heartbeat loop
  jobs.py            job store, admission control, single-flight, event fan-out, state listeners
  pipeline.py        grading DAG
  platform/          learning platform: db (SQLite/PostgreSQL), security (accounts, sessions),
                     api (assignments, dashboards, leaderboard, gradebook), labs, seed
  ingest/ sandbox/ agents/ report/ tracing.py models.py   grading engine (unchanged contracts)
web/                 single-page app (no build step): app.js router, js/core.js, js/pages/*, sandbox.html, PWA
deploy/nginx.conf    load balancer: sticky / round-robin / least-conn upstreams, rate limits, SSE passthrough
scripts/             start.ps1 launcher, latency benchmark, PWA icon generator
docs/                ARCHITECTURE.md, slide deck + generator
```

## Security notes

- Only public `https://github.com/<owner>/<repo>` URLs are accepted. No subprocess uses a shell.
- Secrets found in a repo are redacted before any content is sent to the LLM or written to a report.
- Passwords use scrypt. Sessions are random tokens stored only as SHA-256 and sent in HttpOnly, SameSite=Lax cookies. Cross-site writes are refused (Fetch Metadata / Origin check). A strict CSP applies everywhere.
- Reports and live streams are visible only to the submitting student, instructors, or the API token holder.
- The SQL lab runs each query on a fresh, read-only, in-memory copy with an authorizer (reads only), value-size caps and a 0.5 s CPU deadline. The frontend lab runs student code in an opaque-origin sandboxed iframe.
- **Demo accounts are public knowledge.** Set `AUTOGRADER_DEMO_SEED=0` and a real instructor before exposing the server beyond your machine. Use HTTPS (`AUTOGRADER_COOKIE_SECURE=1`) for anything beyond a classroom LAN.
- Building student Dockerfiles runs untrusted code. Keep the sandbox on an isolated host.
