"""Run one real public-web collection and retain its unapproved results for review."""
import argparse
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-id", help="Retry a previously created live validation request")
    args = parser.parse_args()
    config = dotenv_values(ROOT / ".env")
    base = f"http://127.0.0.1:{config.get('WEB_PORT') or '3100'}"
    with httpx.Client(base_url=base + "/api/v1", timeout=30,
                      headers={"X-Requested-With": "RelationshipPlatform"}) as client:
        response = client.post("/auth/login", json={"email": config["ADMIN_EMAIL"], "password": config["ADMIN_PASSWORD"]})
        response.raise_for_status()
        if args.research_id:
            rid = args.research_id
        else:
            created = client.post("/research-requests", json={
            "title": "Canlı arama denemesi — İstanbul bilgisayarlı görü uzmanları",
            "description": "Gerçek web aramasının kontrolü. Bulunan adaylar ve kaynaklar henüz insan tarafından doğrulanmadı.",
            "field": "Computer Vision", "location": "Istanbul", "target_type": "Professor",
            "requested_quantity": 10, "keywords": ["faculty", "profile"],
            })
            created.raise_for_status()
            rid = created.json()["id"]
        response = client.post(f"/research-requests/{rid}/collect")
        response.raise_for_status()
        print(f"Live research: {base}/panel/research/{rid}", flush=True)
        for _ in range(60):
            status = client.get(f"/research-requests/{rid}/collection")
            status.raise_for_status()
            state = status.json()
            job = state["job"]
            if job["status"] not in ("QUEUED", "RUNNING"):
                print({key: job[key] for key in ("status", "discovered", "processed", "created_count", "merged_count", "error")}, flush=True)
                print("Source outcomes:", [(source["url"], source["status"], source["error"]) for source in state["sources"]], flush=True)
                candidates = client.get(f"/research-requests/{rid}/candidates").json()["items"]
                assert all(c["status"] == "NEW" and not c["is_demo"] for c in candidates)
                print("Unapproved candidate names:", [c["full_name"] for c in candidates], flush=True)
                if job["status"] == "FAILED":
                    raise RuntimeError("Live collection failed; evidence retained for diagnosis")
                return
            time.sleep(4)
        raise RuntimeError("Collection did not finish within 240 seconds")


if __name__ == "__main__":
    main()
