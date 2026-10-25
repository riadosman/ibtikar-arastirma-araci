"""Acceptance check against a running Docker deployment (docker compose up).

Covers security boundaries, roles, idempotent n8n imports, review/export, cancellation and
worker-restart recovery. `--live` also runs one real public-web collection (sends search
terms to external search engines). Deletes only the research requests it created; the
viewer account it creates is deactivated at the end.

    .venv/Scripts/python.exe scripts/production_check.py [--live] [--restart-worker]
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
HEADER = {"X-Requested-With": "RelationshipPlatform"}
results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(("PASS " if condition else "FAIL ") + name + (f" — {detail}" if detail and not condition else ""),
          flush=True)
    return condition


def wait_for_job(client, rid, seconds=300):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job = client.get(f"/research-requests/{rid}/collection?summary=true").json()["job"]
        if job and job["status"] not in ("QUEUED", "RUNNING"):
            return job
        time.sleep(3)
    return None


def compose(project, *args):
    command = ["docker", "compose"] + (["-p", project] if project else []) + list(args)
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run one real web collection")
    parser.add_argument("--restart-worker", action="store_true",
                        help="Restart the worker during a live job and expect it to resume")
    parser.add_argument("--project-name", help="docker compose project to restart (-p)")
    args = parser.parse_args()
    config = dotenv_values(ROOT / ".env")
    panel = f"http://127.0.0.1:{config.get('WEB_PORT') or '3100'}"
    api = f"http://127.0.0.1:{config.get('API_PORT') or '8100'}/api/v1"
    created = []
    run = uuid4().hex[:8]
    brief = {"title": f"Production check {run}", "field": "Artificial Intelligence",
             "location": "Istanbul", "target_type": "Professor", "requested_quantity": 3,
             "keywords": ["computer vision"], "search_language": "en"}
    person = {"full_name": "Check Example", "organization": "Example Lab",
              "source_url": f"https://example.com/check/{run}",
              "source_evidence": "Example Lab lists Check Example as a researcher."}
    with (
        httpx.Client(base_url=api, timeout=30, headers=HEADER) as admin,
        httpx.Client(base_url=api, timeout=30,
                     headers={"Authorization": f"Bearer {config['N8N_API_KEY']}"}) as service,
        httpx.Client(base_url=api, timeout=30, headers=HEADER) as anonymous,
        httpx.Client(base_url=api, timeout=30, headers=HEADER) as viewer,
    ):
        try:
            check("health", httpx.get(panel + "/health").json()["status"] == "ok")
            check("unknown Host header rejected",
                  httpx.get(panel + "/health", headers={"Host": "rebind.example"}).status_code == 400)
            check("anonymous API access denied", anonymous.get("/research-requests").status_code == 401)
            check("panel redirects to login",
                  httpx.get(panel + "/panel", follow_redirects=False).status_code == 303)
            check("wrong API key denied", httpx.get(api + "/dashboard",
                  headers={"Authorization": "Bearer wrong"}).status_code == 401)
            login = admin.post("/auth/login", json={"email": config["ADMIN_EMAIL"],
                                                    "password": config["ADMIN_PASSWORD"]})
            check("admin login", login.status_code == 200, login.text[:200])
            page = admin.get(panel + "/panel")
            check("panel security headers", "frame-ancestors 'none'" in
                  page.headers.get("content-security-policy", ""))

            key = {"Idempotency-Key": f"check-create-{run}"}
            first = service.post("/research-requests", json=brief, headers=key)
            second = service.post("/research-requests", json=brief, headers=key)
            check("idempotent research creation", first.status_code == 201
                  and first.json()["id"] == second.json()["id"], first.text[:200])
            rid = first.json()["id"]
            created.append(rid)
            endpoint = f"/research-requests/{rid}"
            bulk = {"candidates": [person, {**person, "source_url": f"https://example.org/check/{run}"}]}
            imported = service.post(endpoint + "/candidates/bulk", json=bulk,
                                    headers={"Idempotency-Key": f"check-bulk-{run}"})
            replayed = service.post(endpoint + "/candidates/bulk", json=bulk,
                                    headers={"Idempotency-Key": f"check-bulk-{run}"})
            check("n8n bulk import deduplicates", imported.json().get("created") == 1
                  and imported.json().get("merged") == 1, imported.text[:200])
            check("n8n retry replays without duplicates", replayed.json() == imported.json())
            cid = imported.json()["candidate_ids"][0]
            check("service key cannot approve",
                  service.patch(f"/candidates/{cid}", json={"status": "APPROVED"}).status_code == 403)
            check("collection completion", service.post(endpoint + "/complete").json()["status"]
                  == "READY_FOR_REVIEW")
            candidate = admin.get(f"/candidates/{cid}").json()
            check("candidate quality and evidence", candidate["quality"]["source_count"] == 2
                  and candidate["sources"][0]["evidence"])
            check("human approval", admin.patch(f"/candidates/{cid}", json={
                "status": "APPROVED", "notes": "Production check"}).json()["status"] == "APPROVED")
            for format in ("csv", "xlsx", "json"):
                exported = admin.post(endpoint + "/exports", json={"format": format})
                check(f"{format} export", exported.status_code == 200 and len(exported.content) > 0)
            sheets = admin.post(endpoint + "/exports", json={"format": "sheets"})
            check("sheets export (mock or Google)", sheets.status_code == 200, sheets.text[:200])

            email = f"viewer-{run}@example.com"
            password = uuid4().hex + "Aa1!"
            made = admin.post("/admin/users", json={"email": email, "name": "Check Viewer",
                                                     "password": password, "role": "VIEWER"})
            check("admin creates viewer", made.status_code == 201, made.text[:200])
            viewer.post("/auth/login", json={"email": email, "password": password})
            check("viewer can read", viewer.get(endpoint).status_code == 200)
            check("viewer cannot write", viewer.post("/research-requests", json=brief).status_code == 403)
            admin.post(f"/admin/users/{made.json()['id']}/toggle")

            other = admin.post("/research-requests", json={**brief, "title": brief["title"] + " cancel"})
            created.append(other.json()["id"])
            other_endpoint = f"/research-requests/{other.json()['id']}"
            admin.post(other_endpoint + "/collect")
            cancelled = admin.post(other_endpoint + "/collection/cancel")
            job = wait_for_job(admin, other.json()["id"], 120)
            check("collection can be cancelled", cancelled.status_code == 200
                  and job and job["status"] == "CANCELLED", cancelled.text[:200])

            if args.live:
                live = admin.post("/research-requests", json={**brief, "title": brief["title"] + " live"})
                live_id = live.json()["id"]
                created.append(live_id)
                started = admin.post(f"/research-requests/{live_id}/collect")
                check("live collection queued", started.status_code == 202, started.text[:200])
                if args.restart_worker:
                    time.sleep(12)
                    restarted = compose(args.project_name, "restart", "worker")
                    check("worker restart", restarted.returncode == 0, restarted.stderr[-300:])
                job = wait_for_job(admin, live_id, 600)
                check("live collection finished", job is not None
                      and job["status"] in ("COMPLETED", "PARTIAL", "NO_RESULTS"),
                      str(job and {k: job[k] for k in ("status", "error", "attempts")}))
                if job:
                    print("  live job:", {k: job[k] for k in ("status", "attempts", "discovered",
                                                              "processed", "created_count")},
                          "stats:", job.get("stats"), flush=True)
                    names = [c["full_name"] for c in admin.get(
                        f"/research-requests/{live_id}/candidates").json()["items"]]
                    print("  unapproved candidates:", names, flush=True)
        finally:
            for rid in created:
                admin.delete(f"/research-requests/{rid}")
    failed = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed.", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
