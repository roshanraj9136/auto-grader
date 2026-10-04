"""Single-pass repository indexer.

Walks the clone once and extracts every signal the agents need (languages, LOC, tests, CI,
stack detection, secret/risk scans, duplication) so no agent has to touch the filesystem.
Secrets are redacted *here*, before any content can reach an LLM prompt or a report.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .. import config

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build", ".next", ".nuxt",
    "target", "vendor", ".idea", ".vscode", "coverage", ".pytest_cache", ".mypy_cache", ".gradle",
    "bin", "obj", ".terraform", "bower_components", ".cache", "out", "site-packages", ".turbo",
    ".expo", "Pods", ".dart_tool", ".svelte-kit", "htmlcov", ".tox", "migrations_backup",
}

LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".rs": "Rust",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".cs": "C#", ".php": "PHP",
    ".rb": "Ruby", ".swift": "Swift", ".dart": "Dart", ".scala": "Scala", ".vue": "Vue", ".svelte": "Svelte",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".sql": "SQL", ".sh": "Shell", ".ps1": "PowerShell",
}
CODE_LANGS = set(LANG_BY_EXT.values()) - {"HTML", "CSS", "SCSS"}
TEXT_EXTS = set(LANG_BY_EXT) | {
    ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".xml", ".gradle", ".kts",
    ".env", ".properties", ".lock", ".mod", ".sum", ".rst", ".prisma", ".graphql", ".proto", ".tf",
}
TEXT_NAMES = {"Dockerfile", "Makefile", "Procfile", "Jenkinsfile", "Gemfile", "Pipfile", ".gitignore",
              ".dockerignore", ".editorconfig", ".prettierrc", ".eslintrc", ".babelrc", ".nvmrc"}
LOCK_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "go.sum",
              "composer.lock", "Gemfile.lock", "Pipfile.lock", "uv.lock", "bun.lockb"}
MANIFEST_NAMES = {"package.json", "requirements.txt", "requirements-dev.txt", "pyproject.toml", "Pipfile",
                  "setup.py", "setup.cfg", "pom.xml", "build.gradle", "build.gradle.kts", "go.mod",
                  "Cargo.toml", "composer.json", "Gemfile", "pubspec.yaml", "Makefile", "Procfile"}
LINT_CONFIGS = {".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml",
                "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts",
                ".flake8", ".pylintrc", "ruff.toml", ".ruff.toml", "mypy.ini", "tslint.json", "biome.json",
                ".golangci.yml", ".golangci.yaml", "checkstyle.xml", ".rubocop.yml", "phpcs.xml", "analysis_options.yaml"}
FORMAT_CONFIGS = {".prettierrc", ".prettierrc.json", ".prettierrc.js", ".prettierrc.cjs", "prettier.config.js",
                  ".editorconfig", "rustfmt.toml", ".clang-format", ".black"}
TEST_CONFIGS = {"pytest.ini", "conftest.py", "tox.ini", "jest.config.js", "jest.config.ts", "jest.config.cjs",
                "jest.config.mjs", "vitest.config.ts", "vitest.config.js", "vitest.config.mts", "karma.conf.js",
                "cypress.config.js", "cypress.config.ts", "playwright.config.ts", "playwright.config.js",
                "phpunit.xml", ".coveragerc", "codecov.yml", ".nycrc", ".mocharc.json", ".mocharc.yml"}
CI_FILES = {".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml", "azure-pipelines.yml", ".travis.yml",
            "bitbucket-pipelines.yml"}
ENTRYPOINT_NAMES = {"main.py", "app.py", "server.py", "manage.py", "wsgi.py", "asgi.py", "index.js", "server.js",
                    "app.js", "main.ts", "index.ts", "server.ts", "app.ts", "main.go", "Main.java", "main.rs",
                    "Program.cs", "App.tsx", "App.jsx", "App.vue", "main.tsx", "main.jsx", "index.tsx",
                    "index.php", "main.dart", "App.js", "routes.py", "urls.py"}
ENV_EXAMPLES = {".env.example", ".env.sample", ".env.template", "example.env", ".env.dist"}

TEST_DIR_RE = re.compile(r"(^|/)(tests?|__tests__|spec|specs|e2e|cypress|playwright|src/test)(/|$)", re.I)
TEST_FILE_RE = re.compile(
    r"(^test_.*\.py$|.*_test\.(py|go|rb|dart)$|.*\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs)$"
    r"|.*Tests?\.(java|kt|cs|swift)$|.*_spec\.rb$|^test.*\.php$|.*Test\.php$)"
)

# ---- secret scanning (value captured in the "secret" group, then redacted) -------------
SECRET_RULES: list[tuple[str, re.Pattern]] = [
    ("aws-access-key", re.compile(r"(?P<secret>\b(?:AKIA|ASIA)[0-9A-Z]{16}\b)")),
    ("github-token", re.compile(r"(?P<secret>\bgh[pousr]_[A-Za-z0-9]{36,}\b)")),
    ("llm-api-key", re.compile(r"(?P<secret>\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,})")),
    ("slack-token", re.compile(r"(?P<secret>\bxox[abprs]-[A-Za-z0-9-]{10,})")),
    ("google-api-key", re.compile(r"(?P<secret>\bAIza[0-9A-Za-z_-]{35})")),
    ("stripe-live-key", re.compile(r"(?P<secret>\b[sr]k_live_[0-9A-Za-z]{20,})")),
    ("private-key", re.compile(r"(?P<secret>-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----)")),
    ("hardcoded-credential", re.compile(
        r"""(?i)\b(?:password|passwd|pwd|secret|secret_key|api[_-]?key|access[_-]?token|auth[_-]?token|"""
        r"""client[_-]?secret|jwt[_-]?secret)\b["']?\s*[:=]\s*["'](?P<secret>[^"'\s]{8,})["']""")),
    ("db-connection-string", re.compile(
        r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:\s/@]+:(?P<secret>[^@\s/]{4,})@")),
]
PLACEHOLDER_HINTS = ("your", "example", "changeme", "change_me", "xxxx", "<", "${", "{{", "placeholder", "dummy",
                     "process.env", "os.environ", "getenv", "replace", "here", "secret123", "password123", "****")
# Well-known local-dev defaults (e.g. postgres:postgres in compose demos): still reported, lower severity.
COMMON_DEV_PASSWORDS = {"postgres", "password", "root", "admin", "mysql", "secret", "pass", "test", "guest", "mongo",
                        "redis", "user", "docker"}

# ---- risky code patterns ---------------------------------------------------------------
_JS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}
RISK_RULES: list[tuple[str, str, re.Pattern, set[str] | None]] = [
    ("eval-usage", "high", re.compile(r"(?<![\w.])eval\s*\("), {".py", ".php"} | _JS),
    ("python-exec", "high", re.compile(r"(?<![\w.])exec\s*\("), {".py"}),
    ("subprocess-shell-true", "high", re.compile(r"shell\s*=\s*True"), {".py"}),
    ("os-system", "medium", re.compile(r"\bos\.system\s*\("), {".py"}),
    ("child-process-interpolation", "high", re.compile(r"\bexec(?:Sync)?\s*\(\s*`[^`]*\$\{"), _JS),
    ("pickle-deserialization", "medium", re.compile(r"\bpickle\.loads?\s*\("), {".py"}),
    ("yaml-unsafe-load", "medium", re.compile(r"\byaml\.load\s*\((?![^)]*SafeLoader)"), {".py"}),
    ("sql-fstring", "high", re.compile(r"(?i)\b(?:execute|executemany|raw|query|text)\s*\(\s*f[\"'][^\"']*\b(?:select|insert|update|delete)\b"), {".py"}),
    ("sql-concatenation", "high", re.compile(r"(?i)[\"'][^\"']*\b(?:select\s.+\sfrom|insert\s+into|update\s+\w+\s+set|delete\s+from)\b[^\"']*[\"']\s*(?:\+|%\s*[\w(])"), None),
    ("sql-template-literal", "high", re.compile(r"(?i)`[^`]*\b(?:select\s.+\sfrom|insert\s+into|update\s+\w+\s+set|delete\s+from)\b[^`]*\$\{"), _JS),
    ("inner-html-assignment", "medium", re.compile(r"\.innerHTML\s*=(?!=)"), _JS | {".html"}),
    ("dangerously-set-inner-html", "medium", re.compile(r"dangerouslySetInnerHTML"), _JS),
    ("tls-verification-disabled", "medium", re.compile(r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true"), None),
    ("weak-hash", "low", re.compile(r"hashlib\.(?:md5|sha1)\b|createHash\(\s*['\"](?:md5|sha1)['\"]|MessageDigest\.getInstance\(\s*\"(?:MD5|SHA-?1)\""), None),
    ("debug-enabled", "low", re.compile(r"^\s*DEBUG\s*=\s*True\b|\.run\([^)]*debug\s*=\s*True"), {".py"}),
    ("cors-wildcard", "low", re.compile(r"allow_origins\s*=\s*\[\s*[\"']\*[\"']|origin\s*:\s*[\"']\*[\"']|Access-Control-Allow-Origin[\"']?\s*[,:]\s*[\"']\*"), None),
    ("jwt-verification-disabled", "high", re.compile(r"verify_signature[\"']?\s*:\s*False|jwt\.decode\([^)]*verify\s*=\s*False|algorithms\s*=\s*\[\s*[\"']none[\"']", re.I), None),
]
MAX_HITS_PER_RULE_FILE = 3
MAX_TOTAL_HITS = 80
TOTAL_READ_BUDGET = 40_000_000
DUP_WINDOW = 6


@dataclass(slots=True)
class FileInfo:
    path: str
    size: int
    ext: str
    lang: str | None
    lines: int = 0
    comment_lines: int = 0
    is_test: bool = False
    generated: bool = False
    content: str | None = None  # redacted text; None when not read (binary / too big / budget)

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def is_code(self) -> bool:
        return self.lang in CODE_LANGS and not self.generated


@dataclass(slots=True)
class Hit:
    rule: str
    severity: str
    file: str
    line: int
    snippet: str


@dataclass
class RepoIndex:
    root: Path
    files: list[FileInfo] = field(default_factory=list)
    truncated: bool = False
    languages: Counter = field(default_factory=Counter)  # code lines per language
    readme: str = ""
    readme_path: str | None = None
    manifests: dict[str, str] = field(default_factory=dict)
    lint_configs: list[str] = field(default_factory=list)
    format_configs: list[str] = field(default_factory=list)
    test_configs: list[str] = field(default_factory=list)
    ci_files: list[str] = field(default_factory=list)
    docker_files: list[str] = field(default_factory=list)
    compose_files: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    env_examples: list[str] = field(default_factory=list)
    committed_env_files: list[str] = field(default_factory=list)
    has_gitignore: bool = False
    has_license: bool = False
    secret_hits: list[Hit] = field(default_factory=list)
    risk_hits: list[Hit] = field(default_factory=list)
    todo_count: int = 0
    duplication_ratio: float = 0.0
    stack: dict[str, list[str]] = field(default_factory=dict)
    top_dirs: list[str] = field(default_factory=list)

    # ---- derived views ------------------------------------------------------------
    def by_path(self) -> dict[str, FileInfo]:
        return {f.path: f for f in self.files}

    @property
    def code_files(self) -> list[FileInfo]:
        return [f for f in self.files if f.is_code and not f.is_test]

    @property
    def test_files(self) -> list[FileInfo]:
        return [f for f in self.files if f.is_test and f.lang in CODE_LANGS]

    @property
    def source_lines(self) -> int:
        return sum(f.lines for f in self.code_files)

    @property
    def test_lines(self) -> int:
        return sum(f.lines for f in self.test_files)

    def stats(self) -> dict:
        code = self.code_files
        return {
            "files_indexed": len(self.files),
            "truncated": self.truncated,
            "code_files": len(code),
            "source_lines": self.source_lines,
            "test_files": len(self.test_files),
            "test_lines": self.test_lines,
            "test_to_source_ratio": round(self.test_lines / self.source_lines, 3) if self.source_lines else 0.0,
            "languages": dict(self.languages.most_common(8)),
            "avg_lines_per_code_file": round(self.source_lines / len(code), 1) if code else 0,
            "files_over_500_lines": sum(1 for f in code if f.lines > 500),
            "comment_ratio": round(sum(f.comment_lines for f in code) / max(1, self.source_lines), 3),
            "duplication_ratio": self.duplication_ratio,
            "todo_count": self.todo_count,
            "stack": self.stack,
            "ci": self.ci_files,
            "docker_files": self.docker_files,
            "compose_files": self.compose_files,
            "lint_configs": self.lint_configs + self.format_configs,
            "test_configs": self.test_configs,
            "has_readme": bool(self.readme),
            "readme_chars": len(self.readme),
            "has_gitignore": self.has_gitignore,
            "has_license": self.has_license,
            "env_examples": self.env_examples,
            "committed_env_files": self.committed_env_files,
            "secret_findings": len(self.secret_hits),
            "risky_patterns": len(self.risk_hits),
            "top_level_dirs": self.top_dirs,
        }


# ---------------------------------------------------------------------------------------
def build_index(root: Path) -> RepoIndex:
    idx = RepoIndex(root=root)
    read_budget = TOTAL_READ_BUDGET
    root_str = str(root)

    for dirpath, dirnames, filenames in os.walk(root_str):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        rel_dir = os.path.relpath(dirpath, root_str).replace("\\", "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        if rel_dir == "":
            idx.top_dirs = list(dirnames)
        for fname in sorted(filenames):
            if fname == ".autograder.Dockerfile":  # uploaded by the sandbox stage running in parallel
                continue
            if len(idx.files) >= config.MAX_INDEXED_FILES:
                idx.truncated = True
                break
            rel = f"{rel_dir}/{fname}" if rel_dir else fname
            full = os.path.join(dirpath, fname)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            ext = os.path.splitext(fname)[1].lower()
            info = FileInfo(path=rel, size=size, ext=ext, lang=LANG_BY_EXT.get(ext))
            info.is_test = bool(TEST_DIR_RE.search(rel_dir) or TEST_FILE_RE.match(fname))
            info.generated = fname in LOCK_FILES or fname.endswith((".min.js", ".min.css", ".map", ".bundle.js"))
            _classify(idx, info, rel_dir)

            readable = (ext in TEXT_EXTS or fname in TEXT_NAMES or fname.startswith((".env", "Dockerfile"))
                        or fname.lower().startswith(("readme", "license")))
            if readable and not info.generated and size <= config.MAX_READ_BYTES and read_budget > 0:
                text = _read_text(full)
                if text is not None:
                    read_budget -= size
                    _analyze_content(idx, info, text)
            idx.files.append(info)

    idx.duplication_ratio = _duplication_ratio(idx.code_files)
    idx.stack = _detect_stack(idx)
    return idx


def _read_text(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", errors="replace")


def _classify(idx: RepoIndex, f: FileInfo, rel_dir: str) -> None:
    name, path = f.name, f.path
    lname = name.lower()
    if rel_dir == "" and lname.startswith("license"):
        idx.has_license = True
    if name == ".gitignore" and rel_dir == "":
        idx.has_gitignore = True
    if name in MANIFEST_NAMES or (lname.startswith("requirements") and lname.endswith(".txt")):
        idx.manifests[path] = ""
    if name in LINT_CONFIGS:
        idx.lint_configs.append(path)
    if name in FORMAT_CONFIGS:
        idx.format_configs.append(path)
    if name in TEST_CONFIGS:
        idx.test_configs.append(path)
    if path.startswith(".github/workflows/") and f.ext in (".yml", ".yaml") or path in CI_FILES:
        idx.ci_files.append(path)
    if name == "Dockerfile" or name.startswith("Dockerfile.") or lname.endswith(".dockerfile"):
        idx.docker_files.append(path)
    if re.match(r"^(docker-)?compose(\.[\w-]+)?\.ya?ml$", lname):
        idx.compose_files.append(path)
    if name in ENTRYPOINT_NAMES or re.match(r"^\w+Application\.(java|kt)$", name):
        idx.entrypoints.append(path)
    if name in ENV_EXAMPLES:
        idx.env_examples.append(path)
    elif lname == ".env" or (lname.startswith(".env.") and not lname.endswith((".example", ".sample", ".template"))):
        idx.committed_env_files.append(path)


_COMMENT_PREFIXES = ("#", "//", "/*", "*", "--", "<!--", '"""', "'''")


def _analyze_content(idx: RepoIndex, f: FileInfo, text: str) -> None:
    lines = text.splitlines()
    f.lines = len(lines)
    if f.lines and len(text) / f.lines > 400:  # minified / generated
        f.generated = True

    if f.is_code:
        f.comment_lines = sum(1 for ln in lines if ln.lstrip().startswith(_COMMENT_PREFIXES))
        idx.todo_count += len(re.findall(r"\b(?:TODO|FIXME|HACK|XXX)\b", text))
        if not f.is_test:
            idx.languages[f.lang] += f.lines

    text = _scan_secrets(idx, f, text)
    if f.lang is not None and not f.generated:
        _scan_risks(idx, f, text.splitlines())

    if f.path in idx.manifests:
        idx.manifests[f.path] = text
    if f.name.lower().startswith("readme") and (idx.readme_path is None or f.path.count("/") < idx.readme_path.count("/")):
        idx.readme, idx.readme_path = text, f.path
    f.content = text


def _is_placeholder(value: str) -> bool:
    low = value.lower()
    return any(h in low for h in PLACEHOLDER_HINTS) or len(set(value)) <= 3


def _scan_secrets(idx: RepoIndex, f: FileInfo, text: str) -> str:
    example_file = f.name in ENV_EXAMPLES or f.name.endswith((".example", ".sample", ".template"))
    for rule, pattern in SECRET_RULES:
        def _redact(m: re.Match) -> str:
            secret = m.group("secret")
            if rule in ("hardcoded-credential", "db-connection-string") and (example_file or _is_placeholder(secret)):
                return m.group(0)
            if len(idx.secret_hits) < MAX_TOTAL_HITS:
                line_no = text.count("\n", 0, m.start()) + 1
                if rule == "db-connection-string":
                    sev = "medium" if secret.lower() in COMMON_DEV_PASSWORDS else "high"
                else:
                    sev = "critical" if rule != "hardcoded-credential" else "high"
                idx.secret_hits.append(Hit(rule, sev, f.path, line_no, f"{secret[:4]}…[REDACTED]"))
            s, e = m.span("secret")
            return m.group(0)[: s - m.start()] + "[REDACTED]" + m.group(0)[e - m.start():]
        text = pattern.sub(_redact, text)
    return text


def _scan_risks(idx: RepoIndex, f: FileInfo, lines: list[str]) -> None:
    per_rule: Counter = Counter()
    for i, line in enumerate(lines, 1):
        if len(line) > 600:
            continue
        stripped = line.lstrip()
        if stripped.startswith(("#", "//", "*")):
            continue
        for rule, sev, pattern, exts in RISK_RULES:
            if exts is not None and f.ext not in exts:
                continue
            if per_rule[rule] >= MAX_HITS_PER_RULE_FILE or len(idx.risk_hits) >= MAX_TOTAL_HITS:
                continue
            if pattern.search(line):
                per_rule[rule] += 1
                sev_eff = "low" if f.is_test and sev != "low" else sev  # test code: lower blast radius
                idx.risk_hits.append(Hit(rule, sev_eff, f.path, i, stripped[:200]))


def _duplication_ratio(files: list[FileInfo]) -> float:
    """Share of 6-line windows (normalised) that appear more than once across the codebase."""
    seen: dict[bytes, int] = defaultdict(int)
    total = 0
    for f in files:
        if not f.content or f.lines > 5000:
            continue
        norm = [re.sub(r"\s+", "", ln) for ln in f.content.splitlines()]
        norm = [ln for ln in norm if len(ln) > 8 and ln not in ("{", "}", "});", "end")]
        for i in range(len(norm) - DUP_WINDOW + 1):
            h = hashlib.blake2b("\n".join(norm[i:i + DUP_WINDOW]).encode(), digest_size=8).digest()
            seen[h] += 1
            total += 1
            if total > 400_000:
                break
    if not total:
        return 0.0
    dup = sum(c for c in seen.values() if c > 1)
    return round(dup / total, 3)


# ---- full-stack detection (frontend / backend / DB / cache / LB / orchestration / mobile) ----
_STACK_SIGNATURES: dict[str, dict[str, tuple[str, ...]]] = {
    "frontend": {
        "React": ("react-dom", '"react"'), "Next.js": ('"next"',), "Vue": ('"vue"',), "Angular": ("@angular/core",),
        "Svelte": ('"svelte"',), "Vite": ('"vite"',), "Tailwind CSS": ("tailwindcss",), "Redux": ("redux",),
    },
    "backend": {
        "Express": ('"express"',), "NestJS": ("@nestjs/core",), "Fastify": ('"fastify"',), "Koa": ('"koa"',),
        "Django": ("django",), "Flask": ("flask",), "FastAPI": ("fastapi",), "Spring Boot": ("spring-boot",),
        "Gin": ("gin-gonic",), "Echo": ("labstack/echo",), "Fiber": ("gofiber",), "Laravel": ("laravel/framework",),
        "Rails": ("'rails'", '"rails"'), "ASP.NET": ("microsoft.aspnetcore",), "Actix": ("actix-web",),
        "GraphQL": ("graphql",), "Socket.IO": ("socket.io",),
    },
    "database": {
        "PostgreSQL": ("psycopg", '"pg"', "postgres", "asyncpg"), "MySQL": ("mysql",), "MongoDB": ("mongo",),
        "SQLite": ("sqlite",), "Prisma": ("prisma",), "SQLAlchemy": ("sqlalchemy",), "Sequelize": ("sequelize",),
        "TypeORM": ("typeorm",), "Hibernate/JPA": ("spring-boot-starter-data-jpa", "hibernate"),
        "Firebase": ("firebase",), "Supabase": ("supabase",),
    },
    "cache_queue": {
        "Redis": ("redis",), "Celery": ("celery",), "RabbitMQ": ("rabbitmq", "amqp", "pika"),
        "Kafka": ("kafka",), "BullMQ": ("bullmq",),
    },
    "mobile": {
        "React Native": ("react-native",), "Expo": ('"expo"',), "Flutter": ("flutter:",),
        "Android": ("com.android.application",), "Ionic": ("@ionic/",),
    },
    "testing": {
        "pytest": ("pytest",), "Jest": ('"jest"',), "Vitest": ("vitest",), "Mocha": ('"mocha"',),
        "Cypress": ("cypress",), "Playwright": ("playwright",), "JUnit": ("junit",), "Testing Library": ("@testing-library",),
    },
}


def _detect_stack(idx: RepoIndex) -> dict[str, list[str]]:
    corpus = "\n".join(idx.manifests.values()).lower()
    compose_text = "\n".join((idx.by_path()[p].content or "") for p in idx.compose_files).lower()
    found: dict[str, set[str]] = defaultdict(set)
    for category, techs in _STACK_SIGNATURES.items():
        for tech, needles in techs.items():
            if any(n.lower() in corpus for n in needles):
                found[category].add(tech)
    if 'flutter' in corpus and "sdk: flutter" in corpus:
        found["mobile"].add("Flutter")

    # Infra signals from compose / config files.
    infra_images = {
        "database": {"postgres": "PostgreSQL", "mysql": "MySQL", "mariadb": "MariaDB", "mongo": "MongoDB"},
        "cache_queue": {"redis": "Redis", "rabbitmq": "RabbitMQ", "kafka": "Kafka"},
        "proxy_lb": {"nginx": "Nginx", "traefik": "Traefik", "haproxy": "HAProxy", "caddy": "Caddy", "envoy": "Envoy"},
    }
    for category, images in infra_images.items():
        for needle, tech in images.items():
            if re.search(rf"image:\s*['\"]?[\w./-]*{needle}", compose_text):
                found[category].add(tech)

    for f in idx.files:
        n = f.name.lower()
        content = (f.content or "")
        if n.endswith(".conf") and "nginx" in f.path.lower() or n == "nginx.conf":
            found["proxy_lb"].add("Nginx")
            if "upstream" in content:
                found["proxy_lb"].add("Load balancing (nginx upstream)")
        if n in ("haproxy.cfg",):
            found["proxy_lb"].add("HAProxy")
        if f.ext in (".yml", ".yaml") and re.search(r"^kind:\s*(Deployment|Service|Ingress|StatefulSet)", content, re.M):
            found["orchestration"].add("Kubernetes")
        if n == "chart.yaml":
            found["orchestration"].add("Helm")
        if f.ext == ".tf":
            found["orchestration"].add("Terraform")
    if idx.compose_files:
        services = len(re.findall(r"^\s{2}[\w.-]+:\s*$", compose_text, re.M))
        found["orchestration"].add(f"Docker Compose ({services} services)" if services else "Docker Compose")
    if idx.docker_files:
        found["orchestration"].add("Docker")
    return {k: sorted(v) for k, v in sorted(found.items()) if v}


def manifest_scripts(idx: RepoIndex) -> dict[str, dict]:
    """package.json scripts (used by testing/devops agents)."""
    out = {}
    for path, text in idx.manifests.items():
        if path.endswith("package.json") and text:
            try:
                out[path] = json.loads(text).get("scripts", {}) or {}
            except (json.JSONDecodeError, AttributeError):
                continue
    return out
