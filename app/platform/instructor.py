"""Instructor workspace API: gradebook matrix, per-assignment analytics, student profiles and grade adjustments.

Every route here requires the instructor role. Reads are plain SQL over the shared tables; the only writes
are grade adjustments, which keep the original score in `grade_overrides` so they can be reverted.
"""
from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..agents.judge import letter_grade
from .api import (DIMENSIONS, GRADES, _sub_out, get_assignment, leaderboard_rows, overrides_map, pinned_grades,
                  with_overrides)
from .db import get_db, iso_ago, loads, now_iso
from .labs import user_progress
from .security import is_demo_account, require_instructor, require_instructor_write, visible_email

log = logging.getLogger("autograder.instructor")
router = APIRouter(prefix="/api/instructor", dependencies=[Depends(require_instructor)])
LOW_SCORE = 50  # best-try average below this marks a student as needing help


def _ts(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if iso else None
    except ValueError:
        return None


def _late(created_at: str | None, due_at: str | None) -> bool:
    c, d = _ts(created_at), _ts(due_at)
    return bool(c and d and c > d)


def _repo_key(url: str) -> str:
    return (url or "").strip().lower().rstrip("/").removesuffix(".git")


def _stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean": None, "median": None, "stdev": None, "min": None, "max": None}
    return {"count": len(values), "mean": round(statistics.fmean(values), 1), "median": round(statistics.median(values), 1),
            "stdev": round(statistics.pstdev(values), 1) if len(values) > 1 else 0.0,
            "min": round(min(values), 1), "max": round(max(values), 1)}


def _students() -> list[dict]:
    return get_db().all("SELECT id, name, email, entry_no, created_at FROM users WHERE role = 'student' ORDER BY name")


# ---------------------------------------------------------------------------- teaching team
class RoleIn(BaseModel):
    role: str = Field(pattern="^(instructor|student)$")


@router.get("/team")
def team(viewer: dict = Depends(require_instructor)):
    """Everyone who can see the instructor side."""
    rows = get_db().all("SELECT id, name, email, created_at FROM users WHERE role = 'instructor' ORDER BY id")
    return [{**r, "email": visible_email(viewer, r["email"]), "is_you": r["id"] == viewer["id"],
             "is_demo": is_demo_account(r)} for r in rows]


@router.post("/users/{user_id}/role")
def set_role(user_id: int, body: RoleIn, viewer: dict = Depends(require_instructor_write)):
    """Promote a student to instructor, or move an instructor back to being a student.

    Guards, in order: you cannot change your own role (so the last instructor cannot lock themselves out), the
    shared demo accounts can never be promoted (anyone can sign into those), and the final instructor cannot be
    demoted, which would leave the class with nobody who can grade.
    """
    db = get_db()
    target = db.one("SELECT id, name, email, role FROM users WHERE id = ?", (user_id,))
    if not target:
        raise HTTPException(status_code=404, detail="no such user")
    if target["id"] == viewer["id"]:
        raise HTTPException(status_code=400, detail="You cannot change your own role.")
    if is_demo_account(target):
        raise HTTPException(status_code=403, detail="Demo accounts are public, so they can never be made instructors.")
    if target["role"] == body.role:
        return {"id": target["id"], "name": target["name"], "role": target["role"], "changed": False}
    if body.role == "student" and db.scalar("SELECT COUNT(*) AS n FROM users WHERE role = 'instructor'") <= 1:
        raise HTTPException(status_code=400, detail="This is the last instructor: promote someone else first.")
    db.run("UPDATE users SET role = ? WHERE id = ?", (body.role, user_id))
    # Signing them out everywhere makes the new role take effect immediately, on every device.
    db.run("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    log.warning("role change: %s (id=%s) is now a %s, by %s", target["email"], user_id, body.role, viewer["email"])
    return {"id": target["id"], "name": target["name"], "role": body.role, "changed": True}


def _assignments() -> list[dict]:
    return get_db().all("SELECT id, title, track, due_at FROM assignments ORDER BY COALESCE(due_at, created_at), id")


# ---------------------------------------------------------------------------- gradebook
@router.get("/gradebook")
def gradebook(viewer: dict = Depends(require_instructor)):
    """Students x assignments matrix: best graded try per cell, attempts, lateness and adjustment flags."""
    assignments = _assignments()
    due = {a["id"]: a["due_at"] for a in assignments}
    rows = get_db().all(
        "SELECT s.id, s.user_id, s.assignment_id, s.status, s.final_score, s.grade, s.job_id, s.created_at "
        "FROM submissions s JOIN users u ON u.id = s.user_id AND u.role = 'student' "
        "WHERE s.assignment_id IS NOT NULL ORDER BY s.created_at, s.id")
    adjusted = set(overrides_map())
    cells: dict[int, dict[int, dict]] = defaultdict(dict)
    for r in rows:
        c = cells[r["user_id"]].setdefault(r["assignment_id"], {"attempts": 0, "best": None, "grade": None, "job_id": None,
                                                                "late": False, "status": None, "adjusted": False})
        c["attempts"] += 1
        c["status"] = r["status"]  # rows are in time order, so this ends as the latest status
        if r["status"] == "done" and r["final_score"] is not None and (c["best"] is None or r["final_score"] > c["best"]):
            c.update(best=r["final_score"], grade=r["grade"], job_id=r["job_id"],
                     late=_late(r["created_at"], due.get(r["assignment_id"])), adjusted=r["id"] in adjusted)
    for (uid, aid), pin in pinned_grades().items():  # an adjusted grade is the grade, whatever else was submitted
        c = cells.get(uid, {}).get(aid)
        if c is not None:
            c.update(best=pin["final_score"], grade=pin["grade"], job_id=pin["job_id"],
                     late=_late(pin["created_at"], due.get(aid)), adjusted=True)
    students = []
    for u in _students():
        mine = cells.get(u["id"], {})
        got = [c["best"] for c in mine.values() if c["best"] is not None]
        students.append({**u, "email": visible_email(viewer, u["email"]), "cells": {str(k): v for k, v in mine.items()}, "done": len(got),
                         "avg": round(statistics.fmean(got), 1) if got else None})
    columns = []
    for a in assignments:
        vals = [s["cells"][str(a["id"])]["best"] for s in students
                if str(a["id"]) in s["cells"] and s["cells"][str(a["id"])]["best"] is not None]
        columns.append({**a, **{k: v for k, v in _stats(vals).items() if k in ("count", "mean", "max")}})
    return {"assignments": columns, "students": students}


# ---------------------------------------------------------------------------- assignment analytics
def _sub_summary(s: dict, due_at: str | None, adjusted: dict) -> dict:
    details = loads(s["details"], {})
    o = adjusted.get(s["id"])
    return {"id": s["id"], "job_id": s["job_id"], "status": s["status"], "final_score": s["final_score"], "grade": s["grade"],
            "repo_url": s["repo_url"], "ref": s["ref"], "commit": (details.get("commit_sha") or "")[:12],
            "created_at": s["created_at"], "late": _late(s["created_at"], due_at), "total_ms": s["total_ms"],
            "error": s["error"], "dims": loads(s["dims"], {}),
            "override": None if not o else {"original_score": o["original_score"], "reason": o["reason"], "by_name": o["by_name"]}}


@router.get("/assignments/{assignment_id}")
def assignment_analytics(assignment_id: int):
    """Everything an instructor needs for one assignment: score statistics, distribution, per-area averages,
    who has not submitted, possible copying, and every student's best and latest attempt."""
    a = get_assignment(assignment_id)
    subs = get_db().all(
        "SELECT s.*, u.name AS student_name, u.entry_no FROM submissions s JOIN users u ON u.id = s.user_id "
        "AND u.role = 'student' WHERE s.assignment_id = ? ORDER BY s.created_at, s.id", (assignment_id,))
    students = _students()
    adjusted = overrides_map()
    per: dict[int, dict] = {}
    by_day: dict[str, int] = defaultdict(int)
    for s in subs:
        p = per.setdefault(s["user_id"], {"user_id": s["user_id"], "name": s["student_name"], "entry_no": s["entry_no"],
                                         "attempts": 0, "best": None, "latest": None})
        p["attempts"] += 1
        summary = _sub_summary(s, a["due_at"], adjusted)
        p["latest"] = summary
        if s["status"] == "done" and s["final_score"] is not None and (p["best"] is None or s["final_score"] > p["best"]["final_score"]):
            p["best"] = summary
        by_day[(s["created_at"] or "")[:10]] += 1
    by_id = {s["id"]: s for s in subs}
    for (uid, aid), pin in pinned_grades().items():
        if aid == assignment_id and uid in per and pin["id"] in by_id:
            per[uid]["best"] = _sub_summary(by_id[pin["id"]], a["due_at"], adjusted)

    bests = [p["best"] for p in per.values() if p["best"]]
    scores = [b["final_score"] for b in bests]
    histogram = [0] * 10  # 0-9, 10-19, ... 90-100
    for v in scores:
        histogram[min(9, int(v // 10))] += 1
    grades = {g: 0 for g in GRADES}
    for b in bests:
        grades[letter_grade(b["final_score"])] += 1
    dims = {d: [b["dims"][d] for b in bests if b["dims"].get(d) is not None] for d in DIMENSIONS}

    # Possible copying: one repository (or one exact commit, e.g. an unchanged fork) used by several students.
    by_repo: dict[str, set] = defaultdict(set)
    by_commit: dict[str, set] = defaultdict(set)
    repo_names: dict[str, str] = {}
    for s in subs:
        key = _repo_key(s["repo_url"])
        by_repo[key].add(s["user_id"])
        repo_names[key] = s["repo_url"]
        sha = (loads(s["details"], {}).get("commit_sha") or "")
        if sha:
            by_commit[sha].add((s["user_id"], key))
    names = {p["user_id"]: p["name"] for p in per.values()}
    similar = [{"kind": "same repository", "repo_url": repo_names[k], "students": sorted(names[u] for u in uids)}
               for k, uids in by_repo.items() if len(uids) > 1]
    for sha, pairs in by_commit.items():
        uids = {u for u, _ in pairs}
        repos = {r for _, r in pairs}
        if len(uids) > 1 and len(repos) > 1:  # same code pushed to different repositories
            similar.append({"kind": "same commit in different repositories", "commit": sha[:12],
                            "repos": sorted(repo_names[r] for r in repos), "students": sorted(names[u] for u in uids)})

    submitted = set(per)
    rows = sorted(per.values(), key=lambda p: (p["best"] is None, -(p["best"]["final_score"] if p["best"] else 0), p["name"]))
    return {
        "assignment": a,
        "class_size": len(students),
        "submitted": len(submitted),
        "graded": len(bests),
        "attempts": len(subs),
        "late": sum(1 for s in subs if _late(s["created_at"], a["due_at"])),
        "stats": _stats(scores),
        "below_low": sum(1 for v in scores if v < LOW_SCORE),
        "histogram": histogram,
        "grades": grades,
        "dimension_avg": {d: round(statistics.fmean(v), 1) if v else None for d, v in dims.items()},
        "by_day": [{"day": d, "n": n} for d, n in sorted(by_day.items()) if d],
        "not_submitted": [{"id": u["id"], "name": u["name"], "entry_no": u["entry_no"]} for u in students if u["id"] not in submitted],
        "similar": similar,
        "students": rows,
    }


# ---------------------------------------------------------------------------- student profile
@router.get("/students/{user_id}")
def student_profile(user_id: int, viewer: dict = Depends(require_instructor)):
    db = get_db()
    u = db.one("SELECT id, name, email, entry_no, role, created_at FROM users WHERE id = ?", (user_id,))
    if not u or u["role"] != "student":
        raise HTTPException(status_code=404, detail="student not found")
    subs = db.all("SELECT s.*, a.title AS assignment_title, a.due_at FROM submissions s "
                  "LEFT JOIN assignments a ON a.id = s.assignment_id WHERE s.user_id = ? "
                  "ORDER BY s.created_at DESC, s.id DESC LIMIT 300", (user_id,))
    done = [s for s in subs if s["status"] == "done" and s["final_score"] is not None]
    skills: dict[str, list[float]] = defaultdict(list)
    for s in done[:10]:
        for d, v in loads(s["dims"], {}).items():
            skills[d].append(v)
    per_assignment = []
    pins = pinned_grades(user_id)
    adjusted = overrides_map()
    for a in _assignments():
        mine = [s for s in subs if s["assignment_id"] == a["id"]]
        graded = [s for s in mine if s["status"] == "done" and s["final_score"] is not None]
        best = pins.get((user_id, a["id"])) or (max(graded, key=lambda s: s["final_score"]) if graded else None)
        o = adjusted.get(best["id"]) if best else None
        per_assignment.append({**a, "attempts": len(mine), "best": best["final_score"] if best else None,
                               "grade": best["grade"] if best else None, "job_id": best["job_id"] if best else None,
                               "submission_id": best["id"] if best else None,
                               "late": _late(best["created_at"], a["due_at"]) if best else False,
                               "last_at": mine[0]["created_at"] if mine else None,
                               "override": None if not o else {"original_score": o["original_score"], "reason": o["reason"],
                                                               "by_name": o["by_name"]}})
    lb = next((r for r in leaderboard_rows(10_000) if r["user_id"] == user_id), {})
    progress = user_progress(user_id)
    best_scores = [p["best"] for p in per_assignment if p["best"] is not None]
    return {
        "user": {**{k: u[k] for k in ("id", "name", "entry_no", "created_at")}, "email": visible_email(viewer, u["email"])},
        "stats": {"xp": lb.get("xp", 0), "rank": lb.get("rank"), "submissions": len(subs), "graded": len(done),
                  "avg_best": round(statistics.fmean(best_scores), 1) if best_scores else None,
                  "assignments_done": len(best_scores), "labs_done": sum(len(v) for v in progress.values()),
                  "last_active": subs[0]["created_at"] if subs else None},
        "skills": {d: round(statistics.fmean(skills[d]), 1) if skills.get(d) else None for d in DIMENSIONS},
        "timeline": [{"t": s["created_at"], "score": s["final_score"], "grade": s["grade"],
                      "label": s["assignment_title"] or "Practice"} for s in reversed(done[:30])],
        "assignments": per_assignment,
        "submissions": with_overrides([_sub_out(s) for s in subs]),
        "labs": progress,
    }


# ---------------------------------------------------------------------------- grade adjustments
class OverrideIn(BaseModel):
    score: float = Field(ge=0, le=100)
    reason: str = Field(min_length=3, max_length=500)


@router.post("/submissions/{submission_id}/override")
def override_grade(submission_id: int, body: OverrideIn, user: dict = Depends(require_instructor_write)):
    """Set a graded submission's score by hand (e.g. after reviewing it). The original is kept for revert."""
    score = round(body.score, 1)
    grade = letter_grade(score)
    reason = body.reason.strip()
    with get_db().tx() as t:
        s = t.one("SELECT id, status, final_score, grade FROM submissions WHERE id = ?", (submission_id,))
        if not s:
            raise HTTPException(status_code=404, detail="submission not found")
        if s["status"] != "done" or s["final_score"] is None:
            raise HTTPException(status_code=409, detail="only graded submissions can be adjusted")
        # Upsert in one statement: a concurrent second save updates the row instead of failing on the primary key,
        # and the original score recorded by the first adjustment is never overwritten.
        t.run("INSERT INTO grade_overrides (submission_id, original_score, original_grade, score, grade, reason, by_user, "
              "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (submission_id) DO UPDATE SET score = excluded.score, "
              "grade = excluded.grade, reason = excluded.reason, by_user = excluded.by_user, created_at = excluded.created_at",
              (submission_id, s["final_score"], s["grade"], score, grade, reason, user["id"], now_iso()))
        o = t.one("SELECT original_score, original_grade FROM grade_overrides WHERE submission_id = ?", (submission_id,))
        t.run("UPDATE submissions SET final_score = ?, grade = ? WHERE id = ?", (score, grade, submission_id))
    return {"ok": True, "submission_id": submission_id, "score": score, "grade": grade,
            "original_score": o["original_score"], "original_grade": o["original_grade"]}


@router.delete("/submissions/{submission_id}/override")
def revert_grade(submission_id: int, _: dict = Depends(require_instructor_write)):
    db = get_db()
    with db.tx() as t:
        o = t.one("SELECT original_score, original_grade FROM grade_overrides WHERE submission_id = ?", (submission_id,))
        if not o:
            raise HTTPException(status_code=404, detail="this grade was not adjusted")
        t.run("UPDATE submissions SET final_score = ?, grade = ? WHERE id = ?", (o["original_score"], o["original_grade"], submission_id))
        t.run("DELETE FROM grade_overrides WHERE submission_id = ?", (submission_id,))
    return {"ok": True, "score": o["original_score"], "grade": o["original_grade"]}
