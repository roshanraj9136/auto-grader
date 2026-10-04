"""Static Dockerfile linter (hadolint-style rules, zero dependencies, ~1 ms).

Runs even when no Docker daemon is available, so the DevOps agent always has evidence.
Several rules are about *build latency* (layer-cache ordering, .dockerignore, multi-stage).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Finding


@dataclass
class Instruction:
    op: str
    args: str
    line: int


def parse(text: str) -> list[Instruction]:
    text = text.lstrip("\ufeff")  # UTF-8 BOM (common from Windows editors) would hide the first instruction
    out: list[Instruction] = []
    buf, start = "", 0
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not buf and (not line.strip() or line.lstrip().startswith("#")):
            continue
        if not buf:
            start = i
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        buf += line
        parts = buf.strip().split(None, 1)
        if parts:
            out.append(Instruction(parts[0].upper(), parts[1] if len(parts) > 1 else "", start))
        buf = ""
    if buf.strip():
        parts = buf.strip().split(None, 1)
        out.append(Instruction(parts[0].upper(), parts[1] if len(parts) > 1 else "", start))
    return out


_DEP_INSTALL = re.compile(
    r"(pip3?\s+install\s+.*-r|pip3?\s+install\s+\.|poetry\s+install|uv\s+sync|npm\s+(ci|install)|yarn(\s+install)?\b|"
    r"pnpm\s+install|mvn\s|gradle\s|go\s+mod\s+download|bundle\s+install|composer\s+install|cargo\s+build)"
)
_BUILD_TOOLS = re.compile(r"(npm\s+run\s+build|yarn\s+build|mvn\s+(package|install)|gradle\s+build|go\s+build|cargo\s+build|gcc|tsc\b|ng\s+build)")
_SECRET_KEY = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|private[_-]?key|access[_-]?key)")


def lint(text: str, has_dockerignore: bool) -> list[Finding]:
    ins = parse(text)
    f: list[Finding] = []
    path = "Dockerfile"

    def add(sev, title, detail, rec, line=None):
        f.append(Finding(severity=sev, title=title, detail=detail + (f" (line {line})" if line else ""),
                         file=path, recommendation=rec))

    froms = [i for i in ins if i.op == "FROM"]
    if not froms:
        add("critical", "No FROM instruction", "The Dockerfile has no base image and cannot build.",
            "Start with a pinned base image, e.g. `FROM python:3.12-slim`.")
        return f

    stage_names = {m.group(1).lower() for i in froms if (m := re.search(r"\s+AS\s+(\S+)", i.args, re.I))}
    for i in froms:
        image = re.sub(r"--platform=\S+\s*", "", i.args).split()[0]
        if image.lower() in stage_names or image.lower() == "scratch" or image.startswith("$"):
            continue
        if "@sha256:" in image:
            continue
        if ":" not in image.split("/")[-1] or image.endswith(":latest"):
            add("medium", "Unpinned base image", f"`FROM {image}` floats with upstream changes; builds are not reproducible.",
                "Pin a specific tag (and ideally a digest), e.g. `node:20.11-alpine`.", i.line)

    users = [i for i in ins if i.op == "USER"]
    if not users or users[-1].args.strip().split(":")[0] in ("root", "0"):
        add("high", "Container runs as root", "No non-root USER is set for the final stage.",
            "Create an unprivileged user and switch to it: `RUN adduser -D app` then `USER app`.")

    runs = [i for i in ins if i.op == "RUN"]
    for r in runs:
        a = r.args
        if re.search(r"apt-get\s+install", a):
            if not re.search(r"apt-get\s+update", a):
                add("medium", "apt-get install without update in the same layer",
                    "A cached `apt-get update` layer causes stale or failing installs.",
                    "Combine: `RUN apt-get update && apt-get install -y --no-install-recommends … && rm -rf /var/lib/apt/lists/*`.", r.line)
            if "--no-install-recommends" not in a:
                add("low", "apt-get without --no-install-recommends", "Installs unnecessary packages, inflating image size.",
                    "Add `--no-install-recommends`.", r.line)
            if "/var/lib/apt/lists" not in a:
                add("low", "apt cache not cleaned", "Package lists remain in the layer.",
                    "Append `&& rm -rf /var/lib/apt/lists/*` in the same RUN.", r.line)
        if re.search(r"\bapk\s+add\b", a) and "--no-cache" not in a:
            add("low", "apk add without --no-cache", "Leaves the apk index in the image.", "Use `apk add --no-cache …`.", r.line)
        if re.search(r"\bpip3?\s+install\b", a) and "--no-cache-dir" not in a:
            add("low", "pip install without --no-cache-dir", "pip's wheel cache bloats the layer.",
                "Use `pip install --no-cache-dir …`.", r.line)
        if re.search(r"\bnpm\s+install\b", a) and not re.search(r"npm\s+install\s+-g", a):
            add("low", "npm install instead of npm ci", "`npm install` can mutate the lockfile and is slower in CI.",
                "Use `npm ci` (with a committed package-lock.json).", r.line)
        if re.search(r"\bsudo\b", a):
            add("medium", "sudo used in RUN", "RUN already executes as the current user; sudo adds attack surface.",
                "Remove sudo; switch USER explicitly where needed.", r.line)
        if re.search(r"(curl|wget)[^|]*\|\s*(ba|z)?sh", a):
            add("medium", "Remote script piped to shell", "Executing unverified remote scripts is a supply-chain risk.",
                "Download, verify a checksum/signature, then execute.", r.line)
    if sum(1 for r in runs if re.search(r"apt-get\s+update", r.args)) > 1:
        add("low", "Multiple apt-get update layers", "Repeated package index downloads slow the build.",
            "Consolidate package installation into one RUN.")

    for i in ins:
        if i.op == "ADD" and not re.search(r"https?://|\.tar(\.\w+)?\b|\.tgz\b", i.args):
            add("low", "ADD used for local files", "ADD has implicit tar-extraction/URL semantics.",
                "Use COPY for plain files.", i.line)
        if i.op in ("ENV", "ARG"):
            keys = re.findall(r"(\w+)\s*=", i.args)
            if not keys and i.op == "ENV" and len(i.args.split()) >= 2:  # legacy `ENV KEY value`
                keys = [i.args.split()[0]]
            for key in keys:
                if _SECRET_KEY.search(key):
                    add("high", f"Secret-like value baked into image ({i.op} {key})",
                        "ENV/ARG values are visible in `docker history` and image metadata.",
                        "Inject secrets at runtime (env vars, Docker secrets, BuildKit `--mount=type=secret`).", i.line)

    # Layer-cache ordering: COPY of the whole context before dependency install => every code
    # change re-installs all dependencies (the #1 cause of slow student builds).
    copy_all_line = None
    for i in ins:
        if i.op == "FROM":
            copy_all_line = None
        if i.op == "COPY" and copy_all_line is None and re.match(r"^(--\S+\s+)*\.\s+", i.args):
            copy_all_line = i.line
        if i.op == "RUN" and copy_all_line is not None and _DEP_INSTALL.search(i.args):
            add("medium", "Dependency install after `COPY . .` (layer cache busted)",
                "Any source change invalidates the dependency layer, so every build reinstalls everything.",
                "Copy only manifests first (e.g. `COPY package*.json ./` → `RUN npm ci`), then `COPY . .`.", i.line)
            break

    if len(froms) == 1 and any(_BUILD_TOOLS.search(r.args) for r in runs):
        add("low", "Single-stage build with build tooling", "Compilers/dev dependencies ship in the runtime image.",
            "Use a multi-stage build: compile in a builder stage, copy artifacts into a slim runtime stage.")
    if not any(i.op == "HEALTHCHECK" for i in ins):
        add("low", "No HEALTHCHECK", "Orchestrators/load balancers cannot detect an unhealthy container.",
            "Add `HEALTHCHECK CMD curl -f http://localhost:PORT/health || exit 1` (or equivalent).")
    if not any(i.op == "EXPOSE" for i in ins):
        add("info", "No EXPOSE", "The listening port is undocumented.", "Add `EXPOSE <port>`.")
    cmds = [i for i in ins if i.op in ("CMD", "ENTRYPOINT")]
    if not cmds:
        add("medium", "No CMD/ENTRYPOINT", "The container has no default process.", "Add an exec-form CMD.")
    elif not cmds[-1].args.strip().startswith("["):
        add("info", "Shell-form CMD/ENTRYPOINT", "Signals (SIGTERM) are not forwarded to the app; graceful shutdown breaks.",
            'Use exec form: `CMD ["node", "server.js"]`.', cmds[-1].line)
    if not has_dockerignore:
        add("medium", "No .dockerignore", "The whole repo (incl. .git, node_modules, .env) is sent as build context: slower builds and leaked secrets.",
            "Add a .dockerignore excluding .git, node_modules, venv, build output and .env files.")
    return f
