"""Safe GitHub access: URL validation, cheap commit resolution, shallow clone."""
from __future__ import annotations

import os
import re
import shutil
import stat
from pathlib import Path

from .. import config
from ..proc import arun

# Only public https://github.com/<owner>/<repo> URLs. This blocks file://, ssh, ext:: transports
# and arbitrary hosts (SSRF), and guarantees the URL can never be parsed as a git option.
_GITHUB_RE = re.compile(r"^https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$")
_REF_RE = re.compile(r"^(?!-)(?!.*\.\.)[A-Za-z0-9._/-]{1,120}$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

_GIT_ENV = {
    "GIT_TERMINAL_PROMPT": "0",   # never block waiting for credentials
    "GCM_INTERACTIVE": "Never",   # Git Credential Manager on Windows: no popups
    "GIT_LFS_SKIP_SMUDGE": "1",   # don't download LFS blobs
}
_GIT_BASE = ["git", "-c", "credential.helper=", "-c", "core.longpaths=true", "-c", "advice.detachedHead=false"]


class GitError(RuntimeError):
    pass


def normalize_repo_url(url: str) -> str:
    m = _GITHUB_RE.match((url or "").strip())
    if not m:
        raise ValueError("repo_url must look like https://github.com/OWNER/REPO (public GitHub repositories only)")
    owner, repo = m.group(1), m.group(2)
    if repo in (".", ".."):
        raise ValueError("invalid repository name")
    return f"https://github.com/{owner}/{repo}"


def validate_ref(ref: str | None) -> str | None:
    if ref is None or ref.strip() == "":
        return None
    ref = ref.strip()
    if not _REF_RE.match(ref):
        raise ValueError("ref may only contain letters, digits, '.', '_', '-', '/'")
    return ref


async def resolve_commit(url: str, ref: str | None) -> str:
    """Resolve ref -> commit SHA with `git ls-remote` (~0.3-1 s, no object transfer).

    This is what lets a cache hit return without cloning anything.
    """
    if ref and _SHA_RE.match(ref) and len(ref) == 40:
        return ref
    target = ref or "HEAD"
    res = await arun(_GIT_BASE + ["ls-remote", "--", f"{url}.git", target], timeout=30, env=_GIT_ENV)
    if not res.ok:
        raise GitError(_friendly(res.stderr) or "git ls-remote failed")
    rows = [line.split("\t") for line in res.stdout.splitlines() if "\t" in line]
    if not rows:
        if ref and _SHA_RE.match(ref):
            return ref  # abbreviated SHA: resolved after clone
        raise GitError(f"ref '{target}' not found in repository")
    # Prefer exact branch, then tag (peeled ^{} first), then whatever came back.
    prefs = [f"refs/heads/{target}", f"refs/tags/{target}^{{}}", f"refs/tags/{target}", target]
    for p in prefs:
        for sha, name in rows:
            if name == p:
                return sha
    return rows[0][0]


async def shallow_clone(url: str, ref: str | None, dest: Path) -> str:
    """Depth-1, single-branch, tagless clone. Returns the checked-out commit SHA."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    remove_tree(dest)
    timeout = config.CLONE_TIMEOUT_S
    if ref and _SHA_RE.match(ref):
        # Fetch a specific commit (GitHub allows fetching reachable SHAs directly).
        dest.mkdir(parents=True)
        for args in (
            ["init", "-q"],
            ["remote", "add", "origin", f"{url}.git"],
            ["fetch", "-q", "--depth", "1", "--no-tags", "origin", ref],
            ["checkout", "-q", "FETCH_HEAD"],
        ):
            res = await arun(_GIT_BASE + args, cwd=dest, timeout=timeout, env=_GIT_ENV)
            if not res.ok:
                raise GitError(_friendly(res.stderr) or f"git {args[0]} failed")
    else:
        args = ["clone", "-q", "--depth", "1", "--single-branch", "--no-tags"]
        if ref:
            args += ["--branch", ref]
        args += ["--", f"{url}.git", str(dest)]
        res = await arun(_GIT_BASE + args, timeout=timeout, env=_GIT_ENV)
        if res.timed_out:
            raise GitError(f"clone exceeded {timeout}s")
        if not res.ok:
            raise GitError(_friendly(res.stderr) or "git clone failed")
    head = await arun(_GIT_BASE + ["rev-parse", "HEAD"], cwd=dest, timeout=15, env=_GIT_ENV)
    if not head.ok:
        raise GitError("could not read HEAD of cloned repository")
    return head.stdout.strip()


def _friendly(stderr: str) -> str:
    s = (stderr or "").strip()
    low = s.lower()
    if "could not read username" in low or "authentication failed" in low or "repository not found" in low:
        return "repository not found or not public"
    if "remote branch" in low and "not found" in low:
        return "branch/tag not found"
    return s.splitlines()[-1][:300] if s else ""


def remove_tree(path: Path) -> None:
    """rmtree that also handles read-only git object files on Windows."""
    if not path.exists():
        return

    def _onexc(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    shutil.rmtree(path, onexc=_onexc)
