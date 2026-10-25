"""Load the fictional test set (test-data/ornek-adaylar.json) into the running app.

Uses the n8n service key from .env, like an integration would. Safe to run twice: the
Idempotency-Key replays the first result instead of creating a second request.
Delete the "TEST — ..." research from the panel when you are done.

    .venv/Scripts/python.exe scripts/load_test_data.py
"""

import hashlib
import json
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = dotenv_values(ROOT / ".env")
    data_file = ROOT / "test-data" / "ornek-adaylar.json"
    data = json.loads(data_file.read_text(encoding="utf-8"))
    version = hashlib.sha256(data_file.read_bytes()).hexdigest()[:12]
    panel = f"http://127.0.0.1:{config.get('WEB_PORT') or '3100'}"
    headers = {"Authorization": f"Bearer {config['N8N_API_KEY']}"}
    with httpx.Client(base_url=panel + "/api/v1", timeout=60, headers=headers) as api:
        created = api.post("/research-requests", json=data["research"],
                           headers={"Idempotency-Key": f"test-data-{version}-research"})
        if created.status_code != 201:
            sys.exit(f"Research could not be created: {created.status_code} {created.text[:300]}")
        rid = created.json()["id"]
        imported = api.post(f"/research-requests/{rid}/candidates/bulk",
                            json={"candidates": data["candidates"]},
                            headers={"Idempotency-Key": f"test-data-{version}-candidates"})
        if imported.status_code != 200:
            sys.exit(f"Candidates could not be imported: {imported.status_code} {imported.text[:300]}")
        result = imported.json()
        api.post(f"/research-requests/{rid}/complete")
        rows = api.get(f"/research-requests/{rid}/candidates", params={"page_size": 100}).json()
    print(f"Gönderilen kayıt: {len(data['candidates'])}")
    print(f"Yeni aday: {result['created']}  ·  Mevcut adayla birleştirilen: {result['merged']}")
    for row in rows["items"]:
        print(f"  {row['relevance_score']:>3}/100  {row['quality']['source_count']} kaynak  "
              f"{row['full_name']}")
    print(f"\nPanel: {panel}/panel/research/{rid}")


if __name__ == "__main__":
    main()
