"""Exercise the running deployment. Delete only the request created by this run."""

from pathlib import Path
from uuid import uuid4
import httpx
from dotenv import dotenv_values

config = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
base = f"http://127.0.0.1:{config.get('API_PORT') or '8100'}/api/v1"
brief = {
    "title": f"Integration smoke {uuid4()}",
    "field": "AI",
    "location": "Istanbul",
    "target_type": "Speaker",
    "requested_quantity": 2,
    "keywords": ["Vision"],
}
person = {
    "full_name": "Smoke Example",
    "organization": "Example Lab",
    "field": "AI",
    "location": "Istanbul",
    "source_url": "https://example.com/smoke",
}
request_id = None
with (
    httpx.Client(
        base_url=base, timeout=30, headers={"X-Requested-With": "RelationshipPlatform"}
    ) as human,
    httpx.Client(
        base_url=base,
        timeout=30,
        headers={"Authorization": f"Bearer {config['N8N_API_KEY']}"},
    ) as service,
):
    login = human.post(
        "/auth/login",
        json={"email": config["ADMIN_EMAIL"], "password": config["ADMIN_PASSWORD"]},
    )
    login.raise_for_status()
    try:
        created = service.post("/research-requests", json=brief)
        created.raise_for_status()
        request_id = created.json()["id"]
        endpoint = f"/research-requests/{request_id}"
        imported = service.post(
            endpoint + "/candidates/bulk",
            json={
                "candidates": [
                    person,
                    {**person, "source_url": "https://example.org/smoke"},
                ]
            },
        )
        imported.raise_for_status()
        assert imported.json()["created"] == 1 and imported.json()["merged"] == 1
        cid = imported.json()["candidate_ids"][0]
        assert (
            service.patch(f"/candidates/{cid}", json={"status": "APPROVED"}).status_code
            == 403
        )
        assert (
            service.post(endpoint + "/complete").json()["status"] == "READY_FOR_REVIEW"
        )
        rows = human.get(endpoint + "/candidates").json()
        assert rows["total"] == 1 and len(rows["items"][0]["sources"]) == 2
        assert human.post(endpoint + "/exports", json={"format": "json"}).json() == []
        approved = human.patch(
            f"/candidates/{cid}", json={"status": "APPROVED", "notes": "Smoke review"}
        )
        approved.raise_for_status()
        for format in ("csv", "xlsx", "json"):
            exported = human.post(endpoint + "/exports", json={"format": format})
            exported.raise_for_status()
            assert len(exported.content) > 0
        print(
            "PASS: login, n8n import, deduplication, sources, human-only approval, completion, and CSV/XLSX/JSON exports."
        )
    finally:
        if request_id:
            human.delete(f"/research-requests/{request_id}").raise_for_status()
        human.post("/auth/logout").raise_for_status()
