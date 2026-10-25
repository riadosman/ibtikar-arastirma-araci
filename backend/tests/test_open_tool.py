from app.core.config import get_settings

BASE = "/api/v1"
HEADER = {"X-Requested-With": "RelationshipPlatform"}


def test_open_tool_workflow_without_account(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_required", False)
    page = client.get("/")
    assert page.status_code == 200
    assert "/panel/login" not in str(page.url)
    assert 'href="/panel/research/new"' in page.text
    assert "Hesabım" not in page.text and "Çıkış" not in page.text
    response = client.post(
        BASE + "/research-requests",
        headers=HEADER,
        json={"title": "Open tool", "field": "AI", "location": "Istanbul",
              "target_type": "Expert", "requested_quantity": 3},
    )
    assert response.status_code == 201
    rid = response.json()["id"]
    endpoint = BASE + f"/research-requests/{rid}"
    assert client.get(f"/panel/research/{rid}").status_code == 200
    added = client.post(endpoint + "/candidates", headers=HEADER, json={
        "full_name": "Tool Test Person", "source_url": "https://example.com/profile",
    })
    assert added.status_code == 201
    cid = added.json()["candidate_ids"][0]
    assert client.patch(BASE + f"/candidates/{cid}", headers=HEADER,
                        json={"status": "APPROVED"}).status_code == 200
    exported = client.post(endpoint + "/exports", headers=HEADER, json={"format": "csv"})
    assert exported.status_code == 200 and "Tool Test Person" in exported.text
    assert client.delete(BASE + f"/candidates/{cid}", headers=HEADER).status_code == 204
    assert client.delete(endpoint, headers=HEADER).status_code == 204
    response = client.post(BASE + "/research-requests", headers=HEADER, json={
        "title": "Open collection", "field": "AI", "location": "Istanbul",
        "target_type": "Expert", "requested_quantity": 3,
    })
    endpoint = BASE + "/research-requests/" + response.json()["id"]
    assert client.post(endpoint + "/collect", headers=HEADER).status_code == 202
    assert not client.cookies.get("rip_session")


def test_open_tool_preserves_account_and_request_boundaries(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_required", False)
    assert client.get(BASE + "/auth/me").status_code == 401
    assert client.get(BASE + "/admin/audit").status_code == 403
    assert client.get("/panel/users").status_code == 403
    assert client.get("/panel/settings", follow_redirects=False).status_code == 303
    assert client.post(BASE + "/auth/logout").status_code == 403
    assert client.post(BASE + "/auth/logout", headers=HEADER).status_code == 200
    assert client.get(BASE + "/dashboard", headers={"Authorization": "Bearer invalid"}).status_code == 401
    client.cookies.set("rip_session", "expired-or-removed-session")
    assert client.get("/panel").status_code == 200


def test_brand_assets_are_self_hosted(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_required", False)
    page = client.get("/panel")
    # The CSP allows only 'self': fonts and logos must not come from Google Fonts or the public site.
    assert "/static/brand/white_long_logo.svg" in page.text and "/static/brand/square_logo.svg" in page.text
    assert "fonts.googleapis" not in page.text and "ibtikar.org.tr" not in page.text
    css = client.get("/static/panel.css").text
    assert "fonts.googleapis" not in css and "/static/fonts/space-grotesk-latin.woff2" in css
    font = client.get("/static/fonts/space-grotesk-latin.woff2")
    assert font.status_code == 200 and font.headers["content-type"] == "font/woff2"
    assert client.get("/static/brand/square_logo.svg").headers["content-type"] == "image/svg+xml"
