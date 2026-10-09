"""First-run data: optional instructor from env, demo accounts and a starter set of assignments."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from .. import config
from .db import Tx, now_iso
from .security import DEMO_CLASS_DOMAIN, hash_password

log = logging.getLogger("autograder.seed")

DEMO_USERS = [
    ("student@autograder.local", "Demo Student", "2024CS10001", "student", "student123"),
]
# The public demo no longer has an instructor login: the instructor side is shown by the course instructor with
# their own account. Remove the old one wherever it was created.
RETIRED_DEMO_LOGINS = ["instructor@autograder.local"]

ASSIGNMENTS = [
    {
        "title": "Lab 1 - Responsive portfolio site",
        "track": "frontend",
        "days": 7,
        "weights": {"code_quality": 0.35, "architecture": 0.25, "security": 0.1, "testing": 0.15, "devops": 0.15},
        "description": "Build a personal portfolio page with semantic HTML, responsive CSS (flexbox/grid) and a little "
                       "JavaScript. Serve it from a small Nginx container.",
        "rubric_notes": "Semantic HTML5 landmarks; responsive layout with flexbox or grid; accessible (alt text, labels, "
                        "contrast); no inline secrets; static files served by an nginx container with a pinned base image.",
    },
    {
        "title": "Lab 2 - REST API + PostgreSQL",
        "track": "backend",
        "days": 14,
        "weights": {"code_quality": 0.2, "architecture": 0.3, "security": 0.15, "testing": 0.25, "devops": 0.1},
        "description": "Design a CRUD REST API (any language) backed by PostgreSQL. Separate routes, services and data "
                       "access, and test it against a real test database.",
        "rubric_notes": "Layered structure (routes -> services -> repositories); schema migrations; parameterised queries "
                        "only; input validation; integration tests that run against a disposable test database.",
    },
    {
        "title": "Lab 3 - Containers, networks & load balancing",
        "track": "devops",
        "days": 21,
        "weights": {"code_quality": 0.1, "architecture": 0.25, "security": 0.15, "testing": 0.1, "devops": 0.4},
        "description": "Containerise your API and put an Nginx load balancer in front of at least two stateless replicas. "
                       "Keep the database on a private network.",
        "rubric_notes": "docker-compose with nginx upstream (>= 2 API replicas), database not published to the host, "
                        "healthchecks, multi-stage non-root images, .dockerignore, config via environment variables.",
    },
    {
        "title": "Project - Full-stack app with authentication",
        "track": "fullstack",
        "days": 35,
        "weights": dict(config.DEFAULT_WEIGHTS),
        "description": "End-to-end application: web frontend, authenticated API, database, Docker Compose deployment and "
                       "CI that runs your tests on every push.",
        "rubric_notes": "Frontend (React/Vue/Svelte or vanilla) talking to a REST API; hashed passwords and session/JWT auth "
                        "with authorisation checks; relational DB; docker-compose; CI pipeline running tests.",
    },
]


def _add_user(t: Tx, email: str, name: str, entry_no: str | None, role: str, password: str) -> None:
    t.run("INSERT INTO users (email, name, entry_no, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?, ?) "
          "ON CONFLICT (email) DO NOTHING", (email, name, entry_no, hash_password(password), role, now_iso()))


def seed(t: Tx) -> None:
    t.run(f"DELETE FROM users WHERE email IN ({', '.join('?' for _ in RETIRED_DEMO_LOGINS)})", RETIRED_DEMO_LOGINS)
    if config.INSTRUCTOR_EMAIL and config.INSTRUCTOR_PASSWORD:
        _add_user(t, config.INSTRUCTOR_EMAIL, "Instructor", None, "instructor", config.INSTRUCTOR_PASSWORD)
    demo_emails = [u[0] for u in DEMO_USERS]
    if config.DEMO_SEED:
        existing = {r["email"] for r in t.all("SELECT email FROM users")}
        for email, name, entry, role, pw in DEMO_USERS:
            if email not in existing:
                _add_user(t, email, name, entry, role, pw)
        log.warning("Demo mode (AUTOGRADER_DEMO_SEED=1): public student login student@autograder.local / student123, "
                    "sign-up closed. Set AUTOGRADER_INSTRUCTOR_EMAIL/PASSWORD for the instructor account.")
    else:
        # Turning the flag off must also revoke the well-known demo logins created earlier.
        removed = t.run(f"DELETE FROM users WHERE email IN ({', '.join('?' for _ in demo_emails)}) OR email LIKE ?",
                        [*demo_emails, f"%@{DEMO_CLASS_DOMAIN}"])
        if removed:
            log.warning("Removed %d demo account(s) because AUTOGRADER_DEMO_SEED=0", removed)
    seeded = t.scalar("SELECT value FROM meta WHERE key = 'sample_assignments'")
    if not seeded and (config.DEMO_SEED or config.INSTRUCTOR_EMAIL):
        if t.scalar("SELECT COUNT(*) AS n FROM assignments") == 0:
            owner = t.scalar("SELECT id FROM users WHERE role = 'instructor' ORDER BY id LIMIT 1")
            base = datetime.now(timezone.utc).replace(hour=18, minute=29, second=0, microsecond=0)  # 23:59 IST
            for a in ASSIGNMENTS:
                t.insert("INSERT INTO assignments (title, description, track, weights, rubric_notes, due_at, created_by, "
                         "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (a["title"], a["description"], a["track"], json.dumps(a["weights"]), a["rubric_notes"],
                          (base + timedelta(days=a["days"])).isoformat(timespec="seconds"), owner, now_iso()))
        # Only ever seed once: an instructor who deletes the samples should not see them come back.
        t.run("INSERT INTO meta (key, value) VALUES ('sample_assignments', ?) ON CONFLICT (key) DO NOTHING", (now_iso(),))
