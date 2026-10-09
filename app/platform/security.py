"""Accounts and sessions: scrypt password hashes, opaque session tokens in HttpOnly cookies.

* Passwords: hashlib.scrypt (memory-hard, stdlib) with a per-user random salt.
* Sessions: 256-bit random token in the cookie; only its SHA-256 is stored, so a leaked DB
  cannot be replayed as sessions. Cookies are HttpOnly + SameSite=Lax (blocks cross-site POSTs).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, Response

from .. import config
from .db import get_db, iso_in, now_iso

COOKIE = "ag_session"
_N, _R, _P = 2**14, 8, 1  # ~16 MB, ~50 ms per hash


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=64 * 1024 * 1024, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p),
                            maxmem=64 * 1024 * 1024, dklen=32)
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


# A real hash of a random password: login for unknown emails costs the same as a wrong password,
# so response time does not reveal which emails are registered.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(row: dict) -> dict:
    return {"id": row["id"], "email": row["email"], "name": row["name"], "entry_no": row.get("entry_no"),
            "role": row["role"], "created_at": row["created_at"]}


def authenticate(email: str, password: str) -> dict | None:
    row = get_db().one("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    if not row:
        verify_password(password, _DUMMY_HASH)
        return None
    return row if verify_password(password, row["password_hash"]) else None


def start_session(response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    db = get_db()
    with db.tx() as t:
        t.run("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))  # opportunistic cleanup
        t.run("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
              (_token_hash(token), user_id, now_iso(), iso_in(config.SESSION_TTL_HOURS)))
    response.set_cookie(COOKIE, token, max_age=config.SESSION_TTL_HOURS * 3600, httponly=True,
                        samesite="lax", secure=config.COOKIE_SECURE, path="/")


def end_session(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        get_db().run("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    response.delete_cookie(COOKIE, path="/")


def session_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 200:
        return None
    row = get_db().one(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?",
        (_token_hash(token), now_iso()))
    return row


# ---- FastAPI dependencies ------------------------------------------------------------
def optional_user(request: Request) -> dict | None:
    return session_user(request)


def require_user(user: dict | None = Depends(optional_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    return user


def require_instructor(user: dict = Depends(require_user)) -> dict:
    if user["role"] != "instructor":
        raise HTTPException(status_code=403, detail="instructor role required")
    return user


# ---- public demo accounts ----------------------------------------------------------------
# With AUTOGRADER_DEMO_SEED=1 anyone may sign in as the demo student, so demo logins are read-only where it
# matters: none can change its own password or name, and none may act as an instructor. The old demo instructor
# login is retired (deleted at start-up) but stays reserved and read-only here as a second line of defence.
# Sample classmates live under DEMO_CLASS_DOMAIN.
DEMO_LOGINS = frozenset({"instructor@autograder.local", "student@autograder.local"})
DEMO_CLASS_DOMAIN = "demo.autograder.local"


def is_demo_account(user: dict | None) -> bool:
    email = ((user or {}).get("email") or "").lower()
    return email in DEMO_LOGINS or email.endswith("@" + DEMO_CLASS_DOMAIN)


def require_instructor_write(user: dict = Depends(require_instructor)) -> dict:
    """Instructor actions that change data (grades, assignments, regrading)."""
    if is_demo_account(user):
        raise HTTPException(status_code=403, detail="Demo accounts are read-only. "
                                                    "Sign in with the instructor account to make changes.")
    return user


def visible_email(viewer: dict | None, email: str | None) -> str | None:
    """Real students' email addresses are never shown to a demo account."""
    if not email or not is_demo_account(viewer) or email.lower().endswith("@" + DEMO_CLASS_DOMAIN)             or email.lower() in DEMO_LOGINS:
        return email
    return "hidden in the demo"


# ---- brute-force throttle ----------------------------------------------------------------
class Throttle:
    """Sliding-window counter of failed attempts per key (client IP, account email, ...), in memory.
    Each replica counts on its own, which is enough to make online password guessing impractical."""

    def __init__(self, limit: int, window_s: float) -> None:
        self.limit, self.window = limit, window_s
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, q: deque, now: float) -> None:
        while q and now - q[0] > self.window:
            q.popleft()

    def blocked(self, *keys: str) -> bool:
        now = time.monotonic()
        with self._lock:
            for k in keys:
                q = self._hits.get(k)
                if q is not None:
                    self._trim(q, now)
                    if len(q) >= self.limit:
                        return True
            return False

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 50_000:  # bound memory under a flood of distinct keys
                self._hits.clear()
            for k in keys:
                q = self._hits[k]
                self._trim(q, now)
                q.append(now)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._hits.pop(k, None)


# Failed sign-ins: tight per client IP; looser per account, so a stranger cannot lock the instructor out
# with a handful of guesses, yet a distributed guesser still gets only ~80 tries an hour per account.
LOGIN_IP_THROTTLE = Throttle(limit=10, window_s=15 * 60)
LOGIN_ACCOUNT_THROTTLE = Throttle(limit=100, window_s=15 * 60)
SIGNUP_THROTTLE = Throttle(limit=8, window_s=60 * 60)    # failed join-code attempts per IP...
SIGNUP_GLOBAL_THROTTLE = Throttle(limit=200, window_s=60 * 60)  # ...and in total, however many IPs are used
# Free reviews from the landing page (public demo only): a few per visitor and a cap for everyone together,
# so one person cannot use up the grading capacity or the free model quota.
TRY_IP_THROTTLE = Throttle(limit=4, window_s=60 * 60)
TRY_GLOBAL_THROTTLE = Throttle(limit=60, window_s=60 * 60)


def client_ip(request: Request) -> str:
    """The caller's address for throttling. Never the left-most X-Forwarded-For entry: the client writes that one."""
    if config.CLIENT_IP_HEADER:  # set by the edge proxy on every request; never fall back to client-written headers
        v = (request.headers.get(config.CLIENT_IP_HEADER) or "").strip()
        return v[:64] if v else (request.client.host if request.client else "unknown")
    hops = [h.strip() for h in (request.headers.get("x-forwarded-for") or "").split(",") if h.strip()]
    if hops:
        return hops[-1][:64]
    return request.client.host if request.client else "unknown"
