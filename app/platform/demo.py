"""Demo class for a public showcase (AUTOGRADER_DEMO_SEED=1).

Creates a handful of sample classmates and queues *real* gradings of small public repositories for them,
so the instructor views have something to show. Nothing is faked: scores come from the normal pipeline.
The plan is idempotent and resumable: on every start, items that never finished (for example because a
free host went to sleep mid-grading) are queued again; finished ones are left alone.
"""
from __future__ import annotations

import logging
import secrets

from datetime import datetime, timedelta, timezone

from .. import config
from .db import get_db, iso_ago, now_iso
from .security import DEMO_CLASS_DOMAIN, hash_password

log = logging.getLogger("autograder.demo")

VOTING = "https://github.com/dockersamples/example-voting-app"
GETTING_STARTED = "https://github.com/docker/getting-started-app"
WELCOME = "https://github.com/docker/welcome-to-docker"
REALWORLD = "https://github.com/gothinkster/node-express-realworld-example-app"
FASTAPI = "https://github.com/fastapi/full-stack-fastapi-template"

# name, entry number, {assignment title prefix: repository}, browser-checked lab tasks
CLASS = [
    ("Aarav Sharma", "2024CS10011", {"Lab 1": GETTING_STARTED, "Lab 2": VOTING}, ["frontend:heading", "frontend:flex", "network:rtt"]),
    ("Diya Patel", "2024CS10042", {"Lab 1": REALWORLD, "Lab 2": FASTAPI}, ["frontend:heading", "frontend:counter", "network:rtt",
                                                                          "network:headers", "loadbalancer:burst"]),
    ("Kabir Singh", "2024CS10077", {"Lab 1": WELCOME}, ["network:rtt"]),
    ("Meera Iyer", "2024CS10103", {"Lab 1": GETTING_STARTED}, ["frontend:heading"]),  # same repository as Aarav
    ("Rohan Gupta", "2024CS10150", {}, []),                                            # has not started
    ("Ananya Rao", "2024CS10168", {"Lab 1": VOTING, "Lab 2": REALWORLD}, ["frontend:heading", "frontend:flex", "frontend:a11y",
                                                                         "network:timing"]),
    ("Vikram Nair", "2024CS10191", {"Lab 2": WELCOME}, []),
]
DEMO_STUDENT_PLAN = {"Lab 1": VOTING}  # the public demo student, so its dashboard is not empty either


def _email(name: str) -> str:
    return f"{name.split()[0].lower()}@{DEMO_CLASS_DOMAIN}"


def prepare_demo_class() -> list[tuple[int, dict, str]]:
    """Make sure the sample classmates exist and return the gradings still to run: (user_id, assignment, repo)."""
    if not config.DEMO_SEED:
        return []
    db = get_db()
    assignments = db.all("SELECT * FROM assignments ORDER BY id")
    by_prefix = {p: next((a for a in assignments if a["title"].startswith(p)), None) for p in ("Lab 1", "Lab 2")}
    plan: list[tuple[int, dict, str]] = []
    with db.tx() as t:
        if db.kind == "postgres":  # replicas start together: only one plans and queues the demo gradings
            t.run("SELECT pg_advisory_xact_lock(4242002)")
        last = t.one("SELECT value FROM meta WHERE key = 'demo_class_queued'")
        if last and last["value"] > (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="seconds"):
            return []  # another replica queued them moments ago
        t.run("INSERT INTO meta (key, value) VALUES ('demo_class_queued', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
              (now_iso(),))
        live = {r["id"] for r in t.all("SELECT id FROM instances WHERE last_seen >= ?", (iso_ago(config.INSTANCE_DEAD_S),))}
        live.add(config.INSTANCE_ID)
        for name, entry, picks, labs in CLASS:
            email = _email(name)
            # random password: these accounts are data, nobody signs in as them
            t.run("INSERT INTO users (email, name, entry_no, password_hash, role, created_at) VALUES (?, ?, ?, ?, 'student', ?) "
                  "ON CONFLICT (email) DO NOTHING", (email, name, entry, hash_password(secrets.token_urlsafe(24)), now_iso()))
            uid = t.one("SELECT id FROM users WHERE email = ?", (email,))["id"]
            for item in labs:
                lab, task = item.split(":")
                t.run("INSERT INTO lab_progress (user_id, lab, task, completed_at) VALUES (?, ?, ?, ?) "
                      "ON CONFLICT (user_id, lab, task) DO NOTHING", (uid, lab, task, now_iso()))
            plan += [(uid, by_prefix[p], repo) for p, repo in picks.items() if by_prefix.get(p)]
        demo = t.one("SELECT id FROM users WHERE email = 'student@autograder.local'")
        if demo:
            plan += [(demo["id"], by_prefix[p], repo) for p, repo in DEMO_STUDENT_PLAN.items() if by_prefix.get(p)]
        pending = []
        for uid, a, repo in plan:
            rows = t.all("SELECT id, status, instance FROM submissions WHERE user_id = ? AND assignment_id = ? AND repo_url = ?",
                         (uid, a["id"], repo))
            # Still in progress on a replica that is alive, or already graded: leave it alone.
            if any(r["status"] == "done" or (r["status"] in ("queued", "running") and r["instance"] in live) for r in rows):
                continue
            # Interrupted earlier (host restarted or slept mid-grading): drop those rows and grade again.
            for r in rows:
                t.run("DELETE FROM submissions WHERE id = ?", (r["id"],))
            pending.append((uid, a, repo))
    if pending:
        log.info("demo class: queueing %d real grading(s) of sample repositories", len(pending))
    return pending
