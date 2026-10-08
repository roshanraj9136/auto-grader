"""Security and access-control checks against a running AutoGrader+ in demo mode. Prints PASS/FAIL per check.

    AUTOGRADER_DEMO_SEED=1 AUTOGRADER_INSTRUCTOR_EMAIL=teacher@college.edu AUTOGRADER_INSTRUCTOR_PASSWORD=... \
        uvicorn app.main:app --port 8000          # wait until the demo class has been graded, then:
    REAL_EMAIL=teacher@college.edu REAL_PASSWORD=... python scripts/security_check.py http://127.0.0.1:8000

Use a local or staging server: the brute-force check locks the caller's IP out of sign-in for 15 minutes,
and the signup checks create two student accounts.
"""
import http.cookiejar
import json
import os
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
REAL = (os.environ.get("REAL_EMAIL", "teacher@college.edu"), os.environ.get("REAL_PASSWORD", ""))
results = []


def client():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def call(method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        h = {"Content-Type": "application/json"} if data else {}
        h.update(headers or {})
        req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
        try:
            with op.open(req, timeout=60) as r:
                t = r.read().decode()
                return r.status, (json.loads(t) if t and t[0] in "[{" else t)
        except urllib.error.HTTPError as e:
            t = e.read().decode()
            try:
                return e.code, json.loads(t)
            except ValueError:
                return e.code, t
    return call


def check(name, ok, info=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{info}]" if info and not ok else ""))


anon = client()
st = client(); st("POST", "/api/auth/login", {"email": "student@autograder.local", "password": "student123"})
demo_i = client(); demo_i("POST", "/api/auth/login", {"email": "instructor@autograder.local", "password": "instructor123"})
real = client(); code, r = real("POST", "/api/auth/login", {"email": REAL[0], "password": REAL[1]})
check("real instructor can sign in", code == 200, f"{code} {r}")

# --- students and anonymous users cannot reach instructor data or actions
for path in ("/api/instructor/gradebook", "/api/instructor/overview", "/api/instructor/students", "/api/instructor/assignments/1",
             "/api/instructor/students/3", "/api/instructor/gradebook.csv"):
    c1, _ = st("GET", path)
    c2, _ = anon("GET", path)
    check(f"student blocked from {path}", c1 == 403, c1)
    check(f"anonymous blocked from {path}", c2 == 401, c2)

subs_code, subs = real("GET", "/api/instructor/assignments/1")
sid = next((p["best"]["id"] for p in subs.get("students", []) if p.get("best")), None) if subs_code == 200 else None
check("analytics endpoint works for the real instructor", subs_code == 200 and sid, subs_code)

c, _ = st("POST", f"/api/instructor/submissions/{sid}/override", {"score": 100, "reason": "hack"})
check("student cannot override a grade", c == 403, c)
c, _ = anon("POST", f"/api/instructor/submissions/{sid}/override", {"score": 100, "reason": "hack"})
check("anonymous cannot override a grade", c == 401, c)
c, _ = st("POST", f"/api/instructor/submissions/{sid}/regrade")
check("student cannot trigger regrade", c == 403, c)
c, _ = st("POST", "/api/assignments", {"title": "hack assignment"})
check("student cannot create assignments", c == 403, c)
c, _ = st("DELETE", "/api/assignments/1")
check("student cannot delete assignments", c == 403, c)

# --- the public demo instructor is read-only
c, _ = demo_i("GET", "/api/instructor/gradebook")
check("demo instructor can read the gradebook", c == 200, c)
c, r = demo_i("POST", f"/api/instructor/submissions/{sid}/override", {"score": 100, "reason": "demo vandal"})
check("demo instructor cannot override grades", c == 403, f"{c} {r}")
c, _ = demo_i("DELETE", f"/api/instructor/submissions/{sid}/override")
check("demo instructor cannot revert grades", c == 403, c)
c, _ = demo_i("POST", f"/api/instructor/submissions/{sid}/regrade")
check("demo instructor cannot regrade", c == 403, c)
c, _ = demo_i("POST", "/api/instructor/assignments/1/regrade")
check("demo instructor cannot regrade an assignment", c == 403, c)
c, _ = demo_i("POST", "/api/assignments", {"title": "vandal assignment"})
check("demo instructor cannot create assignments", c == 403, c)
c, _ = demo_i("PUT", "/api/assignments/1", {"title": "vandalised"})
check("demo instructor cannot edit assignments", c == 403, c)
c, _ = demo_i("DELETE", "/api/assignments/1")
check("demo instructor cannot delete assignments", c == 403, c)
c, _ = demo_i("POST", "/api/me/password", {"current": "instructor123", "new": "takeover123"})
check("demo instructor cannot change its password", c == 403, c)
c, _ = st("PUT", "/api/me", {"name": "Hacked Name"})
check("demo student cannot rename itself", c == 403, c)
c, gb = demo_i("GET", "/api/instructor/gradebook")
real_emails = [s["email"] for s in gb["students"] if not s["email"].endswith("autograder.local")]
check("real student emails hidden from the demo instructor", all(e == "hidden in the demo" for e in real_emails), real_emails[:3])

# --- the real instructor can adjust and revert
c, r = real("POST", f"/api/instructor/submissions/{sid}/override", {"score": 91.5, "reason": "Manual review: tests exist in CI"})
check("real instructor can override", c == 200 and r.get("grade") == "A", f"{c} {r}")
c, r = real("GET", f"/api/instructor/assignments/1")
best = next(p["best"] for p in r["students"] if p.get("best") and p["best"]["id"] == sid)
check("override is reflected in analytics", best["final_score"] == 91.5 and best["override"]["reason"].startswith("Manual"), best)
c, r = real("POST", f"/api/instructor/submissions/{sid}/override", {"score": 150, "reason": "too high"})
check("override rejects scores above 100", c == 422, c)
c, r = real("POST", f"/api/instructor/submissions/{sid}/override", {"score": 50, "reason": ""})
check("override requires a reason", c == 422, c)
c, r = real("DELETE", f"/api/instructor/submissions/{sid}/override")
check("real instructor can revert", c == 200, f"{c} {r}")

# --- students only see their own work
c, mine = st("GET", "/api/student/submissions")
own_jobs = {s["job_id"] for s in mine}
other = next((p["best"]["job_id"] for p in subs["students"] if p.get("best") and p["best"]["job_id"] not in own_jobs), None)
if other:
    c, _ = st("GET", f"/api/jobs/{other}/report.json")
    check("student cannot read another student's report", c in (403, 404), c)
    c, _ = st("GET", f"/api/submissions/by-job/{other}")
    check("student cannot read another student's submission", c == 404, c)

# --- signup and login hardening
c, _ = anon("POST", "/api/auth/signup", {"name": "Fake Admin", "email": "instructor@autograder.local", "password": "password123"})
check("cannot sign up with a reserved demo email", c in (409, 422), c)
c, _ = anon("POST", "/api/auth/signup", {"name": "Fake", "email": "x@demo.autograder.local", "password": "password123"})
check("cannot sign up under the demo domain", c == 422, c)
c, r = anon("POST", "/api/auth/signup", {"name": "New Student", "email": f"new{int(time.time())}@college.edu", "password": "password123"})
check("signup creates a student, never an instructor", c == 201 and r["user"]["role"] == "student", f"{c} {r}")
c, _ = anon("POST", "/api/auth/signup", {"name": "Role Inject", "email": f"r{int(time.time())}@college.edu", "password": "password123", "role": "instructor"})
codes = []
brute = client()
for i in range(12):
    c, _ = brute("POST", "/api/auth/login", {"email": REAL[0], "password": f"guess{i}"})
    codes.append(c)
check("login brute force is throttled", codes[-1] == 429 and codes[0] == 401, codes)
c, _ = brute("POST", "/api/auth/login", {"email": REAL[0], "password": REAL[1]})
check("throttled account stays locked for the window even with the right password", c == 429, c)

# --- cross-site request protection
c, _ = st("POST", "/api/labs/progress", {"lab": "frontend", "task": "heading"}, headers={"Sec-Fetch-Site": "cross-site"})
check("cross-site POST is blocked", c == 403, c)
c, _ = st("POST", "/api/labs/progress", {"lab": "database", "task": "select"})
check("server-verified lab task cannot be self-reported", c in (400, 403, 422), c)

# --- headers
req = urllib.request.Request(BASE + "/")
with urllib.request.urlopen(req, timeout=30) as resp:
    h = {k.lower(): v for k, v in resp.headers.items()}
check("CSP header present", "default-src 'self'" in h.get("content-security-policy", ""), h.get("content-security-policy"))
check("nosniff header present", h.get("x-content-type-options") == "nosniff")
check("frame protection present", h.get("x-frame-options") == "SAMEORIGIN")

print(f"\n{sum(results)}/{len(results)} checks passed")
