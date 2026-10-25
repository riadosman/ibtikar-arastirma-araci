"""Browser validation of the Python panel; cleans up only its own request."""
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = dotenv_values(ROOT / ".env")
    auth_required = config.get("AUTH_REQUIRED", "false").lower() == "true"
    base = f"http://127.0.0.1:{config.get('WEB_PORT') or '3100'}"
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    rid = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(base_url=base)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto("/")
            if auth_required:
                page.get_by_label("E-posta", exact=True).fill(config["ADMIN_EMAIL"])
                page.get_by_label("Parola", exact=True).fill(config["ADMIN_PASSWORD"])
                page.get_by_role("button", name="Giriş yap").click()
            else:
                expect(page.get_by_role("link", name="Hesabım", exact=True)).to_have_count(0)
                expect(page.get_by_role("link", name="Kullanıcılar", exact=True)).to_have_count(0)
            expect(page.get_by_role("heading", name="Araştırmalar", exact=True)).to_be_visible()
            page.get_by_role("link", name="Yeni araştırma", exact=True).first.click()
            title = "Panel validation " + uuid4().hex[:8]
            page.get_by_label("Başlık", exact=True).fill(title)
            page.get_by_label("Alan", exact=True).fill("Computer Vision")
            page.get_by_label("Konum", exact=True).fill("Istanbul")
            page.get_by_label("Hedef profil", exact=True).fill("Professor")
            page.get_by_label("Arama dili", exact=True).select_option("en")
            page.get_by_role("button", name="Kaydet", exact=True).click()
            expect(page.get_by_role("heading", name=title)).to_be_visible()
            rid = page.url.rsplit("/", 1)[-1]
            page.get_by_role("link", name="Düzenle", exact=True).click()
            expect(page.get_by_label("Arama dili", exact=True)).to_have_value("en")
            page.get_by_role("button", name="Kaydet", exact=True).click()
            expect(page.get_by_role("heading", name=title)).to_be_visible()
            page.get_by_text("Kaynaklı aday ekle", exact=True).click()
            page.get_by_label("Ad soyad", exact=True).fill("Browser Test Person")
            page.get_by_label("Kurum", exact=True).fill("Test Organization")
            page.get_by_label("Kaynak adı", exact=True).fill("Test fixture")
            page.get_by_label("Kaynak adresi", exact=True).fill("https://example.com/test")
            page.get_by_role("button", name="Aday ekle", exact=True).click()
            page.get_by_role("link", name="Browser Test Person", exact=True).click()
            page.get_by_label("Durum", exact=True).select_option("APPROVED")
            page.get_by_label("Değerlendirme notları", exact=True).fill("Browser test only")
            with page.expect_navigation():
                page.get_by_role("button", name="Değerlendirmeyi kaydet").click()
            expect(page.get_by_label("Durum", exact=True)).to_have_value("APPROVED")
            page.goto(f"/panel/research/{rid}")
            with page.expect_download() as download:
                page.get_by_role("button", name="İndir", exact=True).click()
            assert download.value.suggested_filename.endswith(".csv")
            download.value.save_as(artifacts / "panel-export.csv")
            assert "Browser Test Person" in (artifacts / "panel-export.csv").read_text(encoding="utf-8-sig")
            page.screenshot(path=artifacts / "python-panel.png", full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=artifacts / "python-panel-mobile.png", full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            if auth_required:
                page.goto("/panel/settings")
                expect(page.get_by_role("heading", name="Hesabım", exact=True)).to_be_visible()
                page.goto("/panel/users")
                expect(page.get_by_role("heading", name="Kullanıcılar", exact=True)).to_be_visible()
            else:
                assert not page.context.cookies(), "Open tool should not require a session"
            assert not errors, errors
            print(f"Python panel browser workflow passed (auth_required={auth_required}): create, sourced candidate, review, export, mobile")
        finally:
            if rid:
                response = page.request.delete(f"/api/v1/research-requests/{rid}", headers={"X-Requested-With": "RelationshipPlatform"})
                assert response.status == 204, "Browser test request cleanup failed"
            browser.close()


if __name__ == "__main__":
    main()
