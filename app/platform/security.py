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
