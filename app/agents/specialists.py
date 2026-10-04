"""The five specialist agents. Each one owns a single dimension, picks its own evidence
slice from the shared RepoIndex, and has a deterministic heuristic fallback."""
from __future__ import annotations

import json
import posixpath
import re
from collections import Counter, defaultdict

from ..ingest.context import pack_files, ranked, truncate_middle
from ..ingest.indexer import FileInfo, RepoIndex, manifest_scripts
from ..models import AgentReport, DockerResult, Finding
from .base import SpecialistAgent


def _module_of(path: str) -> str:
    d = posixpath.dirname(path)
    return "/".join(d.split("/")[:2]) if d else "(root)"


def diverse(files: list[FileInfo], limit: int = 40) -> list[FileInfo]:
    """Round-robin across modules so evidence covers the whole codebase, not one folder."""
    buckets: dict[str, list[FileInfo]] = defaultdict(list)
    order: list[str] = []
    for f in files:
        m = _module_of(f.path)
        if m not in buckets:
            order.append(m)
        buckets[m].append(f)
    out: list[FileInfo] = []
    while len(out) < limit and any(buckets.values()):
        for m in order:
            if buckets[m]:
                out.append(buckets[m].pop(0))
                if len(out) >= limit:
                    break
    return out


_PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
_JS_IMPORT = re.compile(r"""(?:from\s+|require\(\s*|import\(\s*)['"](\.{1,2}/[^'"]+)['"]""")


def module_graph(idx: RepoIndex, max_edges: int = 25) -> tuple[list[tuple[str, str, int]], list[tuple[str, str]]]:
    """Coarse dependency graph between modules (first two directory levels) + 2-cycles."""
    dirs = {posixpath.dirname(f.path) for f in idx.files}
    edges: Counter = Counter()
    for f in idx.code_files:
        if not f.content:
            continue
        src = _module_of(f.path)
        targets: list[str] = []
        if f.lang == "Python":
            for a, b in _PY_IMPORT.findall(f.content):
                mod = (a or b).replace(".", "/")
                for cand in (mod, posixpath.dirname(mod)):
                    if cand in dirs:
                        targets.append(_module_of(cand + "/x"))
                        break
        elif f.lang in ("JavaScript", "TypeScript", "Vue", "Svelte"):
            for rel in _JS_IMPORT.findall(f.content):
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(f.path), rel))
                if not resolved.startswith(".."):
                    targets.append(_module_of(resolved if "." in posixpath.basename(resolved) else resolved + "/x"))
        for t in targets:
            if t != src:
                edges[(src, t)] += 1
    cycles = sorted({tuple(sorted((a, b))) for (a, b) in edges if (b, a) in edges})
    return [(a, b, n) for (a, b), n in edges.most_common(max_edges)], cycles


def _hits_block(hits, limit: int = 40) -> str:
    if not hits:
        return "(none)"
    return "\n".join(f"- [{h.severity}] {h.rule} @ {h.file}:{h.line}  `{h.snippet}`" for h in hits[:limit])


def _name_score(f: FileInfo, words: tuple[str, ...], weight: float) -> float:
    p = f.path.lower()
    return weight if any(w in p for w in words) else 0.0


# =========================================================================================
class CodeQualityAgent(SpecialistAgent):
    name = "Code Quality Agent"
    dimension = "code_quality"
    role_prompt = """Assess readability, naming, function/file size, cohesion, duplication, error handling,
consistency of style, use of linters/formatters/types, and dead or commented-out code.
Use the metrics (duplication_ratio, files_over_500_lines, comment_ratio, todo_count) as hints,
but base the score on the code you can read."""

    def evidence(self, idx: RepoIndex, docker: DockerResult | None) -> str:
        s = idx.stats()
        metrics = {k: s[k] for k in ("code_files", "source_lines", "avg_lines_per_code_file", "files_over_500_lines",
                                     "comment_ratio", "duplication_ratio", "todo_count", "lint_configs")}
        largest = sorted(idx.code_files, key=lambda f: -f.lines)[:3]
        core = ranked(idx, lambda f: (1 + min(f.lines, 400) / 100 + (3 if f.path in idx.entrypoints else 0))
                      if f.is_code and not f.is_test else 0)
        seen: set[str] = set()
        big = pack_files(largest, budget=14_000, per_file=4_500, seen=seen)
        rest = pack_files(diverse(core), budget=18_000, per_file=3_000, seen=seen)
        return (f"## Metrics\n{json.dumps(metrics, indent=1)}\n\n## Largest files\n{big}\n\n"
                f"## Representative files across modules\n{rest}")

    def heuristic(self, idx: RepoIndex, docker: DockerResult | None) -> AgentReport:
        s = idx.stats()
        score, strengths, findings = 6.0, [], []
        if idx.lint_configs:
            score += 0.8
            strengths.append(f"Linter configured ({', '.join(idx.lint_configs[:3])}).")
        else:
            score -= 0.5
            findings.append(Finding(severity="medium", title="No linter configuration",
                                    detail="No ESLint/Ruff/Pylint/etc. config found; style issues are not caught automatically.",
                                    recommendation="Add a linter (ESLint for JS/TS, Ruff for Python) and run it in CI."))
        if idx.format_configs:
            score += 0.4
            strengths.append("Formatter / editorconfig present.")
        big = [f for f in idx.code_files if f.lines > 500]
        if big:
            score -= min(2.0, 0.5 * len(big))
            findings.append(Finding(severity="medium" if len(big) < 4 else "high",
                                    title=f"{len(big)} oversized file(s) (>500 lines)",
                                    detail="Large files usually mix responsibilities and are hard to review.",
                                    file=big[0].path, recommendation="Split by responsibility into smaller modules."))
        dup = s["duplication_ratio"]
        if dup > 0.15:
            score -= min(1.5, dup * 5)
            findings.append(Finding(severity="medium", title=f"High code duplication (~{dup:.0%} of 6-line windows repeat)",
                                    detail="Copy-pasted blocks multiply bugs and maintenance cost.",
                                    recommendation="Extract shared helpers/components."))
        elif s["code_files"] >= 5:
            strengths.append(f"Low duplication ({dup:.0%}).")
        if idx.todo_count > 15:
            score -= 0.5
            findings.append(Finding(severity="low", title=f"{idx.todo_count} TODO/FIXME markers",
                                    detail="Many unfinished work markers.", recommendation="Resolve or track them as issues."))
        if s["code_files"] < 3:
            score -= 1.5
            findings.append(Finding(severity="medium", title="Very small codebase",
                                    detail="Too little code to demonstrate structure.", recommendation="Modularise the project."))
        if 0.03 <= s["comment_ratio"] <= 0.35:
            score += 0.3
        return self.make_report(score, f"Heuristic estimate from static metrics over {s['code_files']} code files "
                                       f"({s['source_lines']} lines).", strengths, findings)


# =========================================================================================
class ArchitectureAgent(SpecialistAgent):
    name = "Architecture Agent"
    dimension = "architecture"
    role_prompt = """Assess the system architecture of this full-stack project: separation of frontend/backend,
layering (routes/controllers -> services -> data access), modularity and coupling (use the module
dependency graph and cycles), API design (REST conventions, status codes, validation, versioning),
data modelling and DB access, configuration via environment, statelessness/scalability (could it run
behind a load balancer with multiple replicas?), and how services are composed (compose, proxy, queues).
Name the architectural style you observe (e.g. layered monolith, MVC, client-server SPA + REST API)."""

    def evidence(self, idx: RepoIndex, docker: DockerResult | None) -> str:
        edges, cycles = module_graph(idx)
        graph = "\n".join(f"- {a} -> {b} ({n} imports)" for a, b, n in edges) or "(no internal imports detected)"
        cyc = "\n".join(f"- {a} <-> {b}" for a, b in cycles) or "(none)"
        arch_words = ("route", "router", "controller", "service", "model", "schema", "repositor", "api", "view",
                      "urls", "store", "middleware", "config", "settings", "db", "database", "handler", "entity", "dto")
        files = ranked(idx, lambda f: 0 if (f.is_test or f.generated) else (
            (5 if f.path in idx.entrypoints else 0) + _name_score(f, arch_words, 3)
            + (4 if f.path in idx.compose_files else 0) + _name_score(f, ("nginx", "k8s", "helm", "kubernetes"), 4)
            + (1 if f.is_code else 0) - f.path.count("/") * 0.2))
        packed = pack_files(diverse(files, 50), per_file=2_400)
        return (f"## Detected stack\n{json.dumps(idx.stack, indent=1)}\n\n## Entrypoints\n{idx.entrypoints[:15]}\n\n"
                f"## Module dependency graph (top edges)\n{graph}\n\n## Bidirectional dependencies (cycles)\n{cyc}\n\n"
                f"## Structural files (heads)\n{packed}")

    def heuristic(self, idx: RepoIndex, docker: DockerResult | None) -> AgentReport:
        st = idx.stack
        score, strengths, findings = 5.0, [], []
        if st.get("frontend") and st.get("backend"):
            score += 1.2
            strengths.append(f"Full-stack split: {', '.join(st['frontend'][:2])} frontend + {', '.join(st['backend'][:2])} backend.")
        elif not st.get("backend"):
            findings.append(Finding(severity="medium", title="No backend framework detected",
                                    detail="Could not identify an API/server layer from the manifests.",
                                    recommendation="Expose a backend API (e.g. FastAPI/Express) separate from the UI."))
        if st.get("database"):
            score += 0.8
            strengths.append(f"Persistence layer: {', '.join(st['database'][:3])}.")
        else:
            findings.append(Finding(severity="low", title="No database detected",
                                    detail="No DB driver/ORM found in manifests or compose.",
                                    recommendation="Persist data in a real database with a data-access layer."))
        layer_words = {"routes", "controllers", "services", "models", "repositories", "views", "api", "schemas",
                       "middleware", "components", "pages", "store", "handlers"}
        layers = {seg for f in idx.files for seg in f.path.lower().split("/")[:-1] if seg in layer_words}
        if len(layers) >= 3:
            score += 1.0
            strengths.append(f"Layered structure ({', '.join(sorted(layers)[:6])}).")
        elif len(layers) <= 1:
            score -= 0.5
            findings.append(Finding(severity="medium", title="Little visible layering",
                                    detail="Routing, business logic and data access do not appear separated.",
                                    recommendation="Introduce routes/controllers -> services -> repositories layers."))
        _, cycles = module_graph(idx)
        if cycles:
            score -= min(1.0, 0.4 * len(cycles))
            findings.append(Finding(severity="medium", title=f"{len(cycles)} bidirectional module dependency(ies)",
                                    detail=f"e.g. {cycles[0][0]} <-> {cycles[0][1]}; cycles make layers hard to change independently.",
                                    recommendation="Invert the dependency (interfaces/events) so dependencies point one way."))
        if idx.env_examples:
            score += 0.4
            strengths.append("Configuration documented via env example file.")
        if len(idx.compose_files) and "Compose" in " ".join(st.get("orchestration", [])):
            score += 0.4
        if st.get("proxy_lb"):
            score += 0.5
            strengths.append(f"Reverse proxy / LB: {', '.join(st['proxy_lb'])}.")
        if len(idx.code_files) < 4:
            score -= 1.5
        return self.make_report(score, f"Heuristic estimate from structure ({len(layers)} layer folders, "
                                       f"{len(idx.code_files)} code files) and detected stack.", strengths, findings)


# =========================================================================================
class SecurityAgent(SpecialistAgent):
    name = "Security Agent"
    dimension = "security"
    role_prompt = """Assess security against the OWASP Top 10 as it applies to this stack: secrets in the repo,
injection (SQL/command/template), XSS, authentication & session/JWT handling, password storage,
authorization checks, input validation, CORS, TLS/verification, insecure deserialization, debug
settings, and dependency hygiene. The automated scanner hits below are leads, NOT proof: confirm
or dismiss them from the code shown. Secrets are already redacted as [REDACTED]."""

    def evidence(self, idx: RepoIndex, docker: DockerResult | None) -> str:
        gitignore = next((f.content for f in idx.files if f.path == ".gitignore"), None) or "(missing)"
        hit_files = {h.file for h in idx.risk_hits + idx.secret_hits}
        auth_words = ("auth", "login", "jwt", "session", "middleware", "security", "password", "permission", "user", "token")
        files = ranked(idx, lambda f: 0 if f.generated else (
            (6 if f.path in hit_files else 0) + _name_score(f, auth_words, 3)
            + (2 if f.content and re.search(r"bcrypt|argon2|jwt|session|csrf|helmet|cors", f.content, re.I) else 0)
            + (0.5 if f.is_code else 0)))
        return (f"## Secret scanner hits (redacted)\n{_hits_block(idx.secret_hits)}\n\n"
                f"## Committed env files\n{idx.committed_env_files or '(none)'}\n\n"
                f"## Risky-pattern scanner hits\n{_hits_block(idx.risk_hits)}\n\n"
                f"## .gitignore\n```\n{truncate_middle(gitignore, 1200)}\n```\n\n"
                f"## Security-relevant files\n{pack_files(files[:30], budget=26_000, per_file=3_500)}")

    def heuristic(self, idx: RepoIndex, docker: DockerResult | None) -> AgentReport:
        score, strengths, findings = 8.5, [], []
        if idx.secret_hits:
            crit = [h for h in idx.secret_hits if h.severity == "critical"]
            high = [h for h in idx.secret_hits if h.severity == "high"]
            score -= min(5.0, 2.5 * len(crit) + 1.0 * len(high) + 0.4 * (len(idx.secret_hits) - len(crit) - len(high)))
            h = (crit or high or idx.secret_hits)[0]
            findings.append(Finding(severity=h.severity,
                                    title=f"{len(idx.secret_hits)} hard-coded secret(s)/credential(s) committed",
                                    detail=f"e.g. {h.rule} at {h.file}:{h.line} ({h.snippet}).", file=h.file,
                                    recommendation="Rotate the credential, purge it from git history, load it from env/secret store."))
        if idx.committed_env_files:
            score -= 1.5
            findings.append(Finding(severity="high", title="Environment file committed",
                                    detail=f"{', '.join(idx.committed_env_files[:3])} is tracked in git.",
                                    file=idx.committed_env_files[0],
                                    recommendation="Remove it, add `.env*` to .gitignore, ship a `.env.example` instead."))
        by_rule: dict[str, list] = defaultdict(list)
        for h in idx.risk_hits:
            by_rule[h.rule].append(h)
        penalty = {"critical": 1.5, "high": 0.8, "medium": 0.4, "low": 0.15}
        total_pen = 0.0
        for rule, hits in by_rule.items():
            sev = hits[0].severity
            total_pen += penalty.get(sev, 0.2)
            findings.append(Finding(severity=sev, title=f"Risky pattern: {rule} ({len(hits)}x)",
                                    detail=f"First at {hits[0].file}:{hits[0].line}: `{hits[0].snippet[:120]}`",
                                    file=hits[0].file, recommendation=_RISK_FIX.get(rule, "Review and replace with a safe API.")))
        score -= min(3.5, total_pen)
        if not idx.has_gitignore:
            score -= 0.5
            findings.append(Finding(severity="low", title="No .gitignore",
                                    detail="Build output, dependencies or secrets can be committed by accident.",
                                    recommendation="Add a .gitignore for your stack."))
        corpus = "\n".join(idx.manifests.values()).lower()
        if any(k in corpus for k in ("bcrypt", "argon2", "passlib", "helmet", "jsonwebtoken", "pyjwt", "spring-boot-starter-security")):
            score += 0.5
            strengths.append("Uses established security libraries (hashing/JWT/headers).")
        if not idx.secret_hits and not idx.committed_env_files:
            strengths.append("No hard-coded secrets detected by the scanner.")
        return self.make_report(score, f"Heuristic estimate: {len(idx.secret_hits)} secret hit(s), "
                                       f"{len(idx.risk_hits)} risky pattern hit(s).", strengths, findings, confidence=0.4)


_RISK_FIX = {
    "eval-usage": "Remove eval; parse data with JSON.parse/ast.literal_eval or dispatch through a lookup table.",
    "python-exec": "Remove exec on dynamic input.",
    "subprocess-shell-true": "Pass an argument list with shell=False; never interpolate user input into commands.",
    "os-system": "Use subprocess.run([...], shell=False).",
    "child-process-interpolation": "Use execFile/spawn with an argument array instead of string interpolation.",
    "pickle-deserialization": "Never unpickle untrusted data; use JSON.",
    "yaml-unsafe-load": "Use yaml.safe_load.",
    "sql-fstring": "Use parameterized queries / ORM bind parameters.",
    "sql-concatenation": "Use parameterized queries / ORM bind parameters.",
    "sql-template-literal": "Use parameterized queries ($1/? placeholders).",
    "inner-html-assignment": "Use textContent or a sanitizer (DOMPurify).",
    "dangerously-set-inner-html": "Avoid it, or sanitize with DOMPurify first.",
    "tls-verification-disabled": "Keep certificate verification on; trust a custom CA bundle if needed.",
    "weak-hash": "Use bcrypt/argon2 for passwords and SHA-256+ elsewhere.",
    "debug-enabled": "Drive DEBUG from an env var and default it to False.",
    "cors-wildcard": "Restrict CORS to known frontend origins.",
    "jwt-verification-disabled": "Always verify JWT signatures with an explicit algorithm allow-list.",
}


# =========================================================================================
class TestingAgent(SpecialistAgent):
    name = "Testing Agent"
    dimension = "testing"
    role_prompt = """Assess automated testing: presence and quality of unit, integration/API and end-to-end tests,
what is actually asserted (meaningful assertions vs smoke tests), coverage of critical paths
(auth, data writes, error cases), test isolation (fixtures, mocks, test DB), test tooling config,
and whether CI runs the tests on every push/PR. Estimate rough coverage of important modules."""

    def evidence(self, idx: RepoIndex, docker: DockerResult | None) -> str:
        s = idx.stats()
        meta = {k: s[k] for k in ("test_files", "test_lines", "source_lines", "test_to_source_ratio", "test_configs", "ci")}
        meta["frameworks"] = idx.stack.get("testing", [])
        test_list = "\n".join(f"- {f.path} ({f.lines} lines)" for f in idx.test_files[:60]) or "(no test files found)"
        ci = pack_files([f for f in idx.files if f.path in idx.ci_files], budget=6_000, per_file=2_500)
        tests = pack_files(diverse(sorted(idx.test_files, key=lambda f: -f.lines), 20), budget=17_000, per_file=3_000)
        modules = Counter(_module_of(f.path) for f in idx.code_files)
        return (f"## Test metrics\n{json.dumps(meta, indent=1)}\n\n## package.json scripts\n"
                f"{json.dumps(manifest_scripts(idx), indent=1)[:2000]}\n\n## Source modules (files)\n{dict(modules.most_common(20))}\n\n"
                f"## Test files\n{test_list}\n\n## CI configuration\n{ci}\n\n## Test code samples\n{tests}")

    def heuristic(self, idx: RepoIndex, docker: DockerResult | None) -> AgentReport:
        s = idx.stats()
        strengths, findings = [], []
        if not idx.test_files:
            score = 1.5
            findings.append(Finding(severity="high", title="No automated tests",
                                    detail="No unit, integration or e2e test files were found.",
                                    recommendation="Start with API tests for the main endpoints (pytest+httpx / Jest+supertest)."))
        else:
            ratio = s["test_to_source_ratio"]
            score = 4.0 + min(3.0, ratio * 8)
            strengths.append(f"{len(idx.test_files)} test file(s), test/source line ratio {ratio:.2f}.")
            if ratio < 0.1:
                findings.append(Finding(severity="medium", title="Thin test suite",
                                        detail=f"Tests are only {ratio:.0%} of source size.",
                                        recommendation="Cover critical paths: auth, data writes, error handling."))
            if idx.test_configs:
                score += 0.5
            if any(k in " ".join(idx.stack.get("testing", [])) for k in ("Cypress", "Playwright")):
                score += 0.5
                strengths.append("End-to-end test tooling present.")
        if idx.ci_files:
            score += 1.5
            strengths.append(f"CI configured ({', '.join(idx.ci_files[:2])}).")
        else:
            findings.append(Finding(severity="medium", title="No CI pipeline",
                                    detail="Tests are not run automatically on push/PR.",
                                    recommendation="Add a GitHub Actions workflow that installs deps and runs tests."))
        return self.make_report(score, f"Heuristic estimate from {len(idx.test_files)} test files and CI presence.",
                                strengths, findings)


# =========================================================================================
class DevOpsAgent(SpecialistAgent):
    name = "DevOps & Docker Agent"
    dimension = "devops"
    needs_docker = True
    role_prompt = """Assess containerisation and delivery: Dockerfile quality (base image pinning, layer-cache
ordering, multi-stage, image size, non-root user, healthcheck, exec-form CMD), whether the image
actually BUILT and STARTED in the sandbox (use the build/run results; if the build failed, read the
log and name the root cause), .dockerignore, docker-compose topology (app + DB + cache + reverse
proxy/load balancer, networks, volumes, healthchecks/depends_on), environment configuration,
and CI/CD. Note: the smoke run uses --network none, so failing to reach a DB at startup is expected
and should be judged leniently."""

    def evidence(self, idx: RepoIndex, docker: DockerResult | None) -> str:
        d = docker or DockerResult(skipped_reason="docker stage unavailable")
        dockerfile_text = d.dockerfile_text
        result = d.model_dump(include={"dockerfile_source", "dockerfile_path", "other_dockerfiles", "attempted_build", "build_ok",
                                       "build_seconds", "attempted_run", "run_ok", "image_size_mb", "skipped_reason"})
        lint = "\n".join(f"- [{x.severity}] {x.title}: {x.detail}" for x in d.lint) or "(no lint findings)"
        deploy_words = ("procfile", "nginx", "k8s", "kubernetes", "helm", "vercel.json", "netlify.toml", "render.yaml",
                        "fly.toml", "app.json", "terraform", ".dockerignore", "compose")
        infra = [f for f in idx.files if f.path in idx.compose_files or f.path in idx.ci_files or f.path in idx.env_examples
                 or f.name == ".dockerignore" or (f.path in idx.docker_files and f.path != d.dockerfile_path)
                 or _name_score(f, deploy_words, 1)]
        return (f"## Dockerfile ({d.dockerfile_source}: {d.dockerfile_path})\n```dockerfile\n"
                f"{truncate_middle(dockerfile_text, 6000) or '(none)'}\n```\n\n## Sandbox result\n{json.dumps(result, indent=1)}\n\n"
                f"## Static Dockerfile lint\n{lint}\n\n## Build log (tail)\n```\n{d.build_log_tail or '(not built)'}\n```\n\n"
                f"## Run log (tail)\n```\n{d.run_log_tail or '(not run)'}\n```\n\n"
                f"## Infra / CI / deployment files\n{pack_files(infra[:25], budget=14_000, per_file=2_500)}")

    def heuristic(self, idx: RepoIndex, docker: DockerResult | None) -> AgentReport:
        d = docker or DockerResult()
        strengths, findings = [], list(d.lint)
        if d.dockerfile_source == "none":
            score = 2.5
            findings.append(Finding(severity="high", title="No Dockerfile",
                                    detail="The project cannot be containerised as submitted.",
                                    recommendation="Add a multi-stage Dockerfile and a docker-compose.yml (app + DB)."))
        else:
            pen = {"critical": 3.0, "high": 1.0, "medium": 0.5, "low": 0.2, "info": 0.0}
            score = 7.0 - min(4.0, sum(pen[f.severity] for f in d.lint))
            strengths.append(f"Dockerfile provided ({d.dockerfile_source}).")
            if d.build_ok is True:
                score += 1.5
                strengths.append(f"Image builds in the sandbox ({d.build_seconds}s, {d.image_size_mb} MB).")
            elif d.build_ok is False:
                score -= 2.5
                findings.insert(0, Finding(severity="critical", title="Docker build failed",
                                           detail="The image does not build; see build log tail in the report.",
                                           recommendation="Reproduce locally with `docker build .` and fix the failing step."))
            if d.run_ok is True:
                score += 0.5
                strengths.append("Container starts and stays up (smoke test).")
            elif d.run_ok is False:
                score -= 0.75
                findings.append(Finding(severity="medium", title="Container exits / crashes on start",
                                        detail="Smoke run (no network) did not stay up.",
                                        recommendation="Check CMD, required env vars and startup errors in the run log."))
        if idx.compose_files:
            score += 0.75
            strengths.append(f"Compose topology: {', '.join(idx.compose_files[:2])}.")
        if idx.ci_files:
            score += 0.5
        if idx.stack.get("proxy_lb"):
            score += 0.3
        return self.make_report(score, "Heuristic estimate from Dockerfile lint, sandbox result and infra files.",
                                strengths, findings, confidence=0.5 if d.attempted_build else 0.35)


SPECIALISTS: list[SpecialistAgent] = [CodeQualityAgent(), ArchitectureAgent(), SecurityAgent(), TestingAgent(), DevOpsAgent()]
