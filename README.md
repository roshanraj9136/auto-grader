# AutoGrader

Multi-agent grader for full-stack student projects. You give it a **GitHub repo URL**, optionally with a **Dockerfile**, and it returns a **full report**.

Five specialist LLM agents (Code Quality, Architecture, Security, Testing, DevOps & Docker) review the project in parallel. A **Judge agent** then cross-examines their reports, calibrates the scores and writes the verdict, top priorities and a learning path for the student. The pipeline is a latency-optimised DAG with live progress over Server-Sent Events.

Architecture and latency design are in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**. The slide deck is at `docs/AutoGrader.pptx`.

```
GitHub URL + Dockerfile ─► resolve ‖ speculative clone ─► index ─┬─► 4 code agents ──────────┐
                                                                 └─► docker lint/build/run ─► DevOps agent ─► Judge ─► Report
```

## Quick start (local)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt     # Linux/macOS: .venv/bin/pip
copy .env.example .env                              # add ANTHROPIC_API_KEY (optional)
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Open http://localhost:8000, paste a repo URL and click **Start grading**.
Without `ANTHROPIC_API_KEY` the system runs in **heuristic mode**: the same pipeline, with deterministic scorers in place of LLM calls.

## Docker Compose (API + Nginx)

```bash
docker compose up --build                     # http://localhost:8080, static Dockerfile analysis only
# opt-in build/run sandbox (mounts docker.sock; use a dedicated VM, see security notes):
docker compose -f docker-compose.yml -f docker-compose.sandbox.yml up --build
```

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/grade` | JSON submit `{repo_url, ref?, dockerfile_text?, weights?, rubric_notes?, force?}` returns `202 {job_id}` |
| POST | `/api/grade/upload` | multipart submit with a Dockerfile file |
| GET | `/api/jobs/{id}/events` | SSE stream: stage start/end, agent results, verdict |
| GET | `/api/jobs/{id}/report` | report JSON (`.html`, `.md`, `.json` variants for download) |
| GET | `/api/metrics` | rolling p50/p95/max latency per stage, cache-hit counters |
| GET | `/api/health` | mode, models, docker availability |

```bash
curl -F repo_url=https://github.com/dockersamples/example-voting-app \
     -F dockerfile=@Dockerfile http://localhost:8000/api/grade/upload
```

Interactive OpenAPI docs are served at `/docs`.

## Configuration (env / `.env`)

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Enables LLM mode |
| `AUTOGRADER_AGENT_MODEL` / `AUTOGRADER_JUDGE_MODEL` | `claude-sonnet-5-5` | Model tiering |
| `AUTOGRADER_AGENT_TIMEOUT` / `AUTOGRADER_JUDGE_TIMEOUT` | 120 / 150 s | Deadline, then heuristic fallback |
| `AUTOGRADER_LLM_CONCURRENCY` | 8 | Global in-flight LLM cap |
| `AUTOGRADER_MAX_CONCURRENT_JOBS` | 2 | Admission control |
| `AUTOGRADER_ENABLE_DOCKER` | 1 | 0 = static Dockerfile lint only |
| `AUTOGRADER_DOCKER_BUILD_TIMEOUT` | 600 s | |
| `AUTOGRADER_API_TOKEN` | — | If set, submissions require `Authorization: Bearer <token>` |

## Latency benchmark

```bash
python scripts/latency_benchmark.py https://github.com/dockersamples/example-voting-app
```

The benchmark runs the real pipeline with a **simulated** LLM latency model. Sample result: 27.5 s wall-clock vs 75.5 s sequential, a **2.74× speed-up**, and the measured critical path is `clone → index → agent:security → judge → report`.

## Project layout

```
app/
  main.py            REST + SSE API
  jobs.py            job store, admission control, single-flight, event fan-out
  pipeline.py        grading DAG
  tracing.py         stage timings, critical path, p50/p95 metrics
  models.py          typed contracts between stages
  ingest/            git_ops (safe clone), indexer (one-pass scan), context (prompt budgets)
  sandbox/           dockerfile_lint (20+ rules), docker_runner (build + locked-down smoke run)
  agents/            llm client, 5 specialists, judge
  report/            HTML/Markdown rendering, result cache, artifacts
web/                 single-page UI (live DAG, waterfall, embedded report)
deploy/nginx.conf    reverse proxy: rate limit, SSE passthrough, gzip
scripts/             latency benchmark
docs/                ARCHITECTURE.md, slide deck + generator
```

## Security notes

- Only public `https://github.com/<owner>/<repo>` URLs are accepted. No subprocess uses a shell.
- Secrets found in a repo are redacted before any content is sent to the LLM or written to a report.
- **Without `AUTOGRADER_API_TOKEN`, the submission API has no authentication.** Set a token (and keep the Nginx rate limit) before exposing it beyond localhost.
- Building student Dockerfiles runs untrusted code. Keep the sandbox on an isolated host.
