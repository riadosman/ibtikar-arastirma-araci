"""Real browser/API/worker/DB tests with deterministic external search fixtures.

Uses a disposable SQLite database and a private subprocess; never edits workspace data.
Run with .venv/Scripts/python.exe scripts/e2e_collection.py.
"""

import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def serve(port):
    sys.path.insert(0, str(ROOT / "backend"))
    import uvicorn
    from app.core.db import Base, engine
    from app.main import app
    from app.services.collection import run_next
    from app.services.discovery import SearchHit
    from app.services.fetching import FetchError

    fallback_calls = []

    class Discovery:
        def discover(self, query, limit, page=1):
            time.sleep(0.3)
            if page > 1:
                return []
            if "Blocked" in query:
                return [SearchHit("https://example.org/blocked", "Blocked source", "")]
            if "Empty" in query:
                return [SearchHit("https://example.org/empty", "Empty source", "")]
            if "Fallback" in query:
                # Round 1 (at most 4 queries) finds nothing; a later round finds the person.
                fallback_calls.append(query)
                return [SearchHit("https://example.org/chef" if len(fallback_calls) > 4 else
                                  "https://example.org/empty", "Fixture biography", "")]
            return [SearchHit(f"https://example.org/person/{i}", f"Fixture source {i}", "")
                    for i in range(3)]

    class Fetcher:
        def fetch(self, url):
            time.sleep(4 if "/person/" in url else 0.4)
            if url.endswith("blocked"):
                raise FetchError("Source returned HTTP 403")
            if url.endswith("empty"):
                return url, b"<h1>Services</h1><p>No person evidence on this page.</p>"
            name = "Ayşe Yılmaz" if url.endswith("chef") else ["Ada Lovelace", "Grace Hopper", "Alan Turing"][int(url[-1])]
            return url, (f"<article><h2>Chef {name}</h2><p>Chef {name} gastronomi alanında "
                         "çalışır. Yarışmalarda jüri olarak görev alır ve öğrencilere mutfak "
                         "eğitimi verir.</p></article>").encode()

    Base.metadata.create_all(engine)

    def worker():
        while True:
            run_next(Discovery(), Fetcher())
            time.sleep(0.1)

    threading.Thread(target=worker, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main():
    import httpx
    from playwright.sync_api import expect, sync_playwright

    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="research-e2e-") as directory:
        env = {**os.environ, "DATABASE_URL": "sqlite:///" + (Path(directory) / "test.db").as_posix(),
               "SECRET_KEY": secrets.token_hex(32), "AUTH_REQUIRED": "false", "DEMO_MODE": "false",
               "LIVE_SEARCH_ENABLED": "true", "N8N_API_KEY": "", "COOKIE_SECURE": "false"}
        with (artifacts / "e2e-collection.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, __file__, "--serve", str(port)],
                                       cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    try:
                        if httpx.get(base + "/health", timeout=1).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if process.poll() is not None:
                        raise RuntimeError("E2E server failed; see artifacts/e2e-collection.log")
                    time.sleep(0.1)
                else:
                    raise RuntimeError("E2E server did not start")
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    page = browser.new_page(base_url=base, viewport={"width": 1360, "height": 1000})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    header = {"X-Requested-With": "RelationshipPlatform"}

                    def create(field, quantity=3):
                        page.goto("/panel/research/new")
                        expect(page.get_by_label("Hedef profil", exact=True)).to_have_value("")
                        page.get_by_label("Başlık", exact=True).fill(field)
                        page.get_by_label("Alan", exact=True).fill(field)
                        page.get_by_label("Konum", exact=True).fill("Türkiye")
                        page.get_by_label("Hedef profil", exact=True).fill("Şef")
                        page.get_by_label("Hedef aday sayısı", exact=True).fill(str(quantity))
                        page.get_by_role("button", name="Kaydet", exact=True).click()
                        expect(page.get_by_role("heading", name=field, exact=True)).to_be_visible()
                        return page.url.rsplit("/", 1)[-1]

                    rid = create("E2E Slow")
                    # One failed status request must not permanently freeze the loader.
                    page.route("**/collection?summary=true", lambda route: route.fulfill(status=503, body="retry"), times=1)
                    page.get_by_role("button", name="Web'de ara", exact=True).click()
                    expect(page.locator("[data-collection]")).to_be_visible()
                    expect(page.locator("[data-connection]")).to_contain_text("Bağlantı yenileniyor")
                    assert page.request.post(f"/api/v1/research-requests/{rid}/collect", headers=header).status == 409
                    expect(page.locator("[data-live-candidates] a").first).to_be_visible(timeout=15000)
                    expect(page.locator("[data-collection]")).to_be_visible()
                    page.screenshot(path=artifacts / "search-progress-desktop.png", full_page=True)
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    page.screenshot(path=artifacts / "search-progress-mobile.png", full_page=True)
                    page.get_by_role("link", name="Diğer araştırmalara geç", exact=True).click()
                    page.goto(f"/panel/research/{rid}")
                    expect(page.locator("tbody tr")).to_have_count(3, timeout=25000)
                    expect(page.locator("[data-collection]")).to_have_count(0)
                    assert page.request.get(f"/api/v1/research-requests/{rid}/collection").json()["job"]["status"] == "COMPLETED"
                    assert not page.context.cookies()
                    print("PASS: browser form -> queue -> worker -> live candidates; duplicate prevention, transient polling failure, mobile, leave/return, completion", flush=True)

                    for field, quantity, expected in [("E2E Fallback", 1, "COMPLETED"),
                                                       ("E2E Empty", 3, "NO_RESULTS"),
                                                       ("E2E Blocked", 3, "FAILED")]:
                        rid = create(field, quantity)
                        page.get_by_role("button", name="Web'de ara", exact=True).click()
                        expect(page.locator("[data-collection]")).to_be_visible()
                        expect(page.locator("[data-collection]")).to_have_count(0, timeout=20000)
                        state = page.request.get(f"/api/v1/research-requests/{rid}/collection").json()
                        assert state["job"]["status"] == expected, state
                        if expected == "COMPLETED":
                            expect(page.get_by_role("link", name="Ayşe Yılmaz", exact=True)).to_be_visible()
                        elif expected == "NO_RESULTS":
                            expect(page.get_by_text("Aday bulunamadı", exact=True).first).to_be_visible()
                            assert "kaynakla doğrulanabilen kişi bulunamadı" in page.locator("main").inner_text()
                        else:
                            assert "erişilemedi" in page.locator("main").inner_text()
                        expect(page.get_by_role("button", name="Web'de ara", exact=True)).to_be_enabled()
                        print(f"PASS: {field} -> {expected}", flush=True)
                    assert not errors, errors
                    browser.close()
            finally:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--serve":
        serve(int(sys.argv[2]))
    else:
        main()
