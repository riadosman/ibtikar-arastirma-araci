"""Regression tests for the production-hardening fixes (one test per defect where possible)."""

import csv
import io
import json
import socket
import threading
import time
import zipfile
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
import pytest
from conftest import TEST_PASSWORD
from openpyxl import load_workbook
from sqlalchemy import func, select
from test_collection import PROFILE, Discovery, Fetcher
from test_workflow import BASE, BRIEF, PERSON, add, request

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.core.security import new_session
from app.models import (
    Candidate,
    CollectionJob,
    ExportJob,
    IdempotencyRecord,
    LoginSession,
    ResearchRequest,
    SourceDocument,
    User,
    now,
)
from app.schemas import CandidateCreate
from app.services import fetching
from app.services.ai import AIServiceError, OpenAIProvider
from app.services.candidates import import_candidates
from app.services.collection import run_next
from app.services.deduplication import deduplicate_candidates
from app.services.discovery import SearchHit, canonical_url
from app.services.export import GoogleSheetsProvider, render_export
from app.services.extraction import extract_profiles
from app.services.fetching import FetchError, PageFetcher
from app.services.maintenance import run_maintenance

# --- export ------------------------------------------------------------------------------


def exported_candidate(**fields):
    base = dict(
        full_name="Ada", job_title=None, organization=None, field=None, location=None,
        website=None, linkedin_url=None, public_email=None, public_phone=None,
        relevance_score=1, confidence_score=1, status="APPROVED", notes="", is_demo=False,
        sources=[SimpleNamespace(name="S", url="https://example.com")],
    )
    return SimpleNamespace(**{**base, **fields})


def test_xlsx_export_survives_control_characters_and_never_writes_formulas():
    candidate = exported_candidate(full_name='=HYPERLINK("http://x")', notes="bio\x0b\x07end")
    content, _ = render_export([candidate], "xlsx")
    sheet = load_workbook(io.BytesIO(content)).active
    assert sheet["A2"].value == '=HYPERLINK("http://x")' and sheet["A2"].data_type == "s"
    assert sheet["M2"].value == "bioend"
    assert "<f>" not in zipfile.ZipFile(io.BytesIO(content)).read("xl/worksheets/sheet1.xml").decode()


@pytest.mark.parametrize("value", ["\t=1+1", "\r=1+1", " =1", "-2+3", "@SUM(A1)"])
def test_csv_export_neutralizes_formula_prefixes(value):
    content, _ = render_export([exported_candidate(full_name=value)], "csv")
    row = next(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    assert row["Name"].startswith("'")


# --- deduplication -----------------------------------------------------------------------


def existing(**fields):
    return Candidate(**{"full_name": "Ada Lovelace", "sources": [], **fields})


def incoming(**fields):
    return CandidateCreate(**{"full_name": "Ada Lovelace", "source_url": "https://e.org/a", **fields})


def test_shared_team_email_or_company_page_never_merges_different_people():
    team = existing(public_email="info@lab.org", linkedin_url="https://linkedin.com/company/lab")
    other = incoming(full_name="Grace Hopper", public_email="info@lab.org",
                     linkedin_url="https://www.linkedin.com/company/lab/")
    assert deduplicate_candidates([team], other) is None


def test_personal_identifiers_merge_variants_but_conflicts_split():
    person = existing(public_email="ada@lab.org", linkedin_url="https://tr.linkedin.com/in/ada/")
    assert deduplicate_candidates([person], incoming(
        full_name="Ada King Lovelace", linkedin_url="https://www.linkedin.com/in/ada?trk=x"
    )) is person
    assert deduplicate_candidates([person], incoming(full_name="ADA LOVELACE",
                                                     public_email="ADA@lab.org")) is person
    # Same name, different personal email: two people.
    assert deduplicate_candidates([person], incoming(public_email="ada@other.org",
                                                     organization="Lab")) is None


def test_turkish_dotless_i_and_middle_names_are_handled_conservatively():
    person = existing(full_name="Mehmet Yılmaz", organization="Örnek Üniversitesi")
    assert deduplicate_candidates([person], incoming(full_name="MEHMET YILMAZ",
                                                     organization="Ornek Universitesi")) is person
    # Middle name plus only an organization match is not enough for a merge.
    assert deduplicate_candidates([person], incoming(full_name="Mehmet Ali Yılmaz",
                                                     organization="Örnek Üniversitesi")) is None


def test_reviewed_candidates_only_gain_sources_never_field_changes(auth):
    rid = request(auth)
    c = add(auth, rid, {**PERSON, "public_email": None})
    auth.patch(f"{BASE}/candidates/{c['id']}", json={"status": "APPROVED"})
    auth.post(f"{BASE}/research-requests/{rid}/candidates",
              json={**PERSON, "public_email": "scraped@example.com",
                    "source_url": "https://example.org/again"})
    saved = auth.get(f"{BASE}/candidates/{c['id']}").json()
    assert saved["public_email"] is None and saved["status"] == "APPROVED"
    assert len(saved["sources"]) == 2


def test_worker_session_sees_reviewer_edits_made_meanwhile(auth):
    rid = request(auth)
    with SessionLocal() as worker:
        research = worker.get(ResearchRequest, rid)
        result = import_candidates(worker, research, [CandidateCreate(**PERSON)], None)
        worker.commit()
        cid = result["candidate_ids"][0]
        auth.patch(f"{BASE}/candidates/{cid}", json={"public_email": "reviewer@example.com"})
        import_candidates(worker, research, [CandidateCreate(
            **{**PERSON, "public_email": "scraped@example.com"})], None)
        worker.commit()
    assert auth.get(f"{BASE}/candidates/{cid}").json()["public_email"] == "reviewer@example.com"


def test_service_key_cannot_rewrite_reviewed_candidates(auth, client):
    rid = request(auth)
    c = add(auth, rid)
    auth.patch(f"{BASE}/candidates/{c['id']}", json={"status": "APPROVED"})
    import os
    service = {"Authorization": "Bearer " + os.environ["N8N_API_KEY"]}
    client.cookies.clear()
    assert client.patch(f"{BASE}/candidates/{c['id']}", headers=service,
                        json={"public_email": "x@example.com"}).status_code == 409
    assert client.patch(f"{BASE}/candidates/{c['id']}", headers=service,
                        json={"notes": "n8n note"}).status_code == 200


# --- idempotency -------------------------------------------------------------------------


def test_create_research_with_idempotency_key_is_created_once(auth):
    headers = {"Idempotency-Key": "create-research-0001"}
    first = auth.post(BASE + "/research-requests", json=BRIEF, headers=headers)
    second = auth.post(BASE + "/research-requests", json=BRIEF, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ResearchRequest)) == 1
    changed = auth.post(BASE + "/research-requests", json={**BRIEF, "title": "Other"},
                        headers=headers)
    assert changed.status_code == 422 and changed.json()["code"] == "validation_error"
    assert auth.post(BASE + "/research-requests", json=BRIEF,
                     headers={"Idempotency-Key": "bad key!"}).status_code == 422


def test_bulk_import_and_collect_replay_on_retry(auth):
    rid = request(auth)
    body = {"candidates": [PERSON]}
    headers = {"Idempotency-Key": "bulk-import-0001"}
    first = auth.post(f"{BASE}/research-requests/{rid}/candidates/bulk", json=body, headers=headers)
    again = auth.post(f"{BASE}/research-requests/{rid}/candidates/bulk", json=body, headers=headers)
    assert first.json() == again.json() and first.json()["created"] == 1
    collect = {"Idempotency-Key": "collect-0001"}
    job = auth.post(f"{BASE}/research-requests/{rid}/collect", headers=collect)
    retry = auth.post(f"{BASE}/research-requests/{rid}/collect", headers=collect)
    assert job.status_code == retry.status_code == 202 and job.json()["id"] == retry.json()["id"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CollectionJob)) == 1


# --- collection lifecycle ----------------------------------------------------------------


def test_cancel_queued_job_immediately(auth):
    rid = request(auth)
    endpoint = f"{BASE}/research-requests/{rid}"
    auth.post(endpoint + "/collect")
    cancelled = auth.post(endpoint + "/collection/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert auth.get(endpoint).json()["status"] == "CREATED"
    assert auth.post(endpoint + "/collection/cancel").status_code == 409
    assert not run_next(Discovery(), Fetcher())


def test_cancel_running_job_stops_after_current_source_and_keeps_candidates(auth):
    rid = request(auth)
    endpoint = f"{BASE}/research-requests/{rid}"

    class CancellingFetcher:
        def fetch(self, url):
            assert auth.post(endpoint + "/collection/cancel").status_code == 200
            return url, PROFILE

    class ThreeHits:
        def discover(self, query, limit, page=1):
            return [SearchHit(f"https://example.com/p{i}", "Ada Lovelace", "") for i in range(3)]

    auth.post(endpoint + "/collect")
    run_next(ThreeHits(), CancellingFetcher())
    state = auth.get(endpoint + "/collection").json()
    assert state["job"]["status"] == "CANCELLED"
    assert [s["status"] for s in state["sources"]].count("SKIPPED") == 2
    assert auth.get(endpoint).json()["status"] == "READY_FOR_REVIEW"
    assert auth.get(endpoint + "/candidates").json()["total"] == 1


def test_shutdown_requeues_and_resumes_without_duplicate_sources(auth):
    rid = request(auth)
    endpoint = f"{BASE}/research-requests/{rid}"
    stop = threading.Event()

    class StoppingFetcher:
        def fetch(self, url):
            stop.set()
            return url, PROFILE

    auth.post(endpoint + "/collect")
    run_next(Discovery(), StoppingFetcher(), stop_event=stop)
    with SessionLocal() as db:
        job = db.scalar(select(CollectionJob))
        assert job.status == "QUEUED" and job.attempts == 1
    run_next(Discovery(), Fetcher())
    with SessionLocal() as db:
        job = db.scalar(select(CollectionJob))
        urls = list(db.scalars(select(SourceDocument.url)))
        assert job.status in ("PARTIAL", "COMPLETED") and job.attempts == 2
        assert len(urls) == len(set(urls)) == 2


def test_duplicate_pages_and_tracking_urls_are_processed_once(auth):
    assert canonical_url("https://Example.com/a?utm_source=x&id=2#top") == "https://example.com/a?id=2"

    class Mirrors:
        def discover(self, query, limit, page=1):
            return [SearchHit("https://example.com/a", "A", ""),
                    SearchHit("https://example.com/a?utm_campaign=z", "A", ""),
                    SearchHit("https://mirror.example.org/a", "A", "")]

    rid = request(auth)
    auth.post(f"{BASE}/research-requests/{rid}/collect")
    run_next(Mirrors(), Fetcher())
    state = auth.get(f"{BASE}/research-requests/{rid}/collection").json()
    assert sorted(s["status"] for s in state["sources"]) == ["DUPLICATE", "EXTRACTED"]
    assert state["job"]["stats"]["duplicate_content"] == 1
    assert state["job"]["stats"]["duplicate_urls"] >= 1


def test_transient_discovery_failure_is_retried(auth):
    calls = []

    class Flaky:
        def discover(self, query, limit, page=1):
            calls.append(query)
            if len(calls) == 1:
                raise TimeoutError("temporary")
            return Discovery().discover(query, limit)

    rid = request(auth)
    auth.post(f"{BASE}/research-requests/{rid}/collect")
    run_next(Flaky(), Fetcher())
    job = auth.get(f"{BASE}/research-requests/{rid}/collection").json()["job"]
    assert job["stats"]["search_errors"] == 1 and job["created_count"] == 1


def test_page_fetcher_retries_retryable_status_then_gives_up(monkeypatch):
    responses = iter([("u", 503, "text/html", b"", {"retry_after": "0"}),
                      ("u", 200, "text/html", b"<html>ok</html>", {"retry_after": None})])
    monkeypatch.setattr(fetching, "fetch_public", lambda url, **kwargs: next(responses))
    fetcher = PageFetcher(retries=1, sleep=lambda seconds: None)
    assert fetcher.fetch("https://example.com") == ("u", b"<html>ok</html>")
    monkeypatch.setattr(fetching, "fetch_public",
                        lambda url, **kwargs: ("u", 404, "text/html", b"", {"retry_after": None}))
    with pytest.raises(FetchError) as error:
        fetcher.fetch("https://example.com")
    assert not error.value.retryable


def test_slow_drip_server_cannot_block_the_worker(monkeypatch):
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    stop = threading.Event()

    def drip():
        connection, _ = server.accept()
        connection.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
        while not stop.is_set():
            try:
                connection.sendall(b"a")
            except OSError:
                break
            time.sleep(0.2)
        connection.close()

    threading.Thread(target=drip, daemon=True).start()
    monkeypatch.setattr(fetching, "public_target",
                        lambda url: (urlsplit(url), "127.0.0.1", port))
    monkeypatch.setattr(get_settings(), "fetch_document_seconds", 1.0)
    started = time.monotonic()
    try:
        with pytest.raises(FetchError, match="time limit"):
            fetching.fetch_public("http://slow.test/")
    finally:
        stop.set()
        server.close()
    assert time.monotonic() - started < 5


def test_fetch_blocks_https_downgrade_and_nat64(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda *a, **k: [(10, 1, 6, "", ("64:ff9b::a00:1", 443, 0, 0))])
    with pytest.raises(FetchError, match="Non-public"):
        fetching.public_target("https://nat64.example/")
    monkeypatch.setattr(fetching, "public_target",
                        lambda url: (urlsplit(url), "93.184.216.34", 443))

    class Redirect:
        status = 302

        def getheader(self, name, default=None):
            return "http://example.com/plain" if name == "Location" else default

    class Connection:
        def __init__(self, *args):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Redirect()

        def close(self):
            pass

    monkeypatch.setattr(fetching, "PinnedHTTP", Connection)
    with pytest.raises(FetchError, match="Insecure redirect"):
        fetching.fetch_public("https://example.com/")


def test_extraction_cpu_is_bounded_on_deeply_nested_pages():
    nested = "<div>" * 1500 + "Chef Ada Lovelace " * 200 + "</div>" * 1500
    html = ("<html><body>" + nested + "<span>x</span>" * 20000 + "</body></html>").encode()
    started = time.monotonic()
    extract_profiles(html, "https://example.com/", "Page", budget_seconds=2)
    assert time.monotonic() - started < 20


def test_directory_links_store_evidence_not_invented_biography():
    html = b"""<title>Faculty members</title><h1>Faculty members</h1>
    <div class="profile-card"><a href="/faculty/ada-lovelace">Ada Lovelace</a></div>"""
    profile = extract_profiles(html, "https://example.com/people", "Faculty members")[1][0]
    assert profile.bio is None
    assert "ada-lovelace" in profile.sources[0].evidence


# --- quality information -----------------------------------------------------------------


def test_candidates_explain_score_sources_and_verification(auth):
    rid = request(auth)
    c = add(auth, rid, {**PERSON, "source_evidence": "Professor of computer vision"})
    assert c["quality"]["source_count"] == 1
    assert c["quality"]["verification_status"] == "UNVERIFIED"
    assert c["quality"]["first_seen_at"] and "kaynak" in c["quality"]["confidence_reason"]
    assert c["sources"][0]["evidence"] == "Professor of computer vision"
    assert "(+25)" in c["relevance_reason"]
    page = auth.get(f"/panel/candidates/{c['id']}").text
    assert "Professor of computer vision" in page and "Neden önerildi?" in page


def test_location_without_letters_never_matches_everything(auth):
    rid = auth.post(BASE + "/research-requests", json={**BRIEF, "location": "—"}).json()["id"]
    c = add(auth, rid, {**PERSON, "location": "Istanbul"})
    assert "konum" not in c["relevance_reason"]


# --- roles, sessions and HTTP hardening --------------------------------------------------


def login_as(client, email):
    client.headers["X-Requested-With"] = "RelationshipPlatform"
    assert client.post(BASE + "/auth/login",
                       json={"email": email, "password": TEST_PASSWORD}).status_code == 200


def test_viewer_role_is_read_only_but_can_export(auth, client):
    rid = request(auth)
    c = add(auth, rid)
    with SessionLocal() as db:
        viewer = User(email="viewer@example.com", name="Viewer", role="VIEWER",
                      password_hash=db.scalar(select(User.password_hash).limit(1)))
        db.add(viewer)
        db.commit()
    client.cookies.clear()
    login_as(client, "viewer@example.com")
    assert client.get(f"{BASE}/research-requests/{rid}").status_code == 200
    assert client.post(BASE + "/research-requests", json=BRIEF).status_code == 403
    assert client.patch(f"{BASE}/candidates/{c['id']}", json={"status": "APPROVED"}).status_code == 403
    assert client.post(f"{BASE}/research-requests/{rid}/collect").status_code == 403
    assert client.post(f"{BASE}/research-requests/{rid}/exports",
                       json={"format": "csv", "include_all": True}).status_code == 200
    page = client.get(f"/panel/research/{rid}")
    assert page.status_code == 200 and "Web'de ara" not in page.text
    assert client.get("/panel/research/new").status_code == 403


def test_admin_role_change_takes_effect_immediately(auth):
    with SessionLocal() as db:
        reviewer = db.scalar(select(User).where(User.email == "reviewer@example.com"))
        new_session(db, reviewer)
        db.commit()
        uid = reviewer.id
    changed = auth.post(f"{BASE}/admin/users/{uid}/role", json={"role": "VIEWER"})
    assert changed.status_code == 200 and changed.json()["role"] == "VIEWER"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(LoginSession)
                         .where(LoginSession.user_id == uid)) == 0
    me = auth.get(BASE + "/auth/me").json()["id"]
    assert auth.post(f"{BASE}/admin/users/{me}/role", json={"role": "USER"}).status_code == 409


def test_login_is_rate_limited_per_account(client):
    client.headers["X-Requested-With"] = "RelationshipPlatform"
    statuses = [client.post(BASE + "/auth/login",
                            json={"email": "admin@example.com", "password": "wrong-password"}
                            ).status_code for _ in range(11)]
    assert statuses[:10] == [401] * 10 and statuses[10] == 429
    other = client.post(BASE + "/auth/login",
                        json={"email": "reviewer@example.com", "password": TEST_PASSWORD})
    assert other.status_code == 200


def test_logout_with_expired_session_still_clears_cookie(client):
    client.headers["X-Requested-With"] = "RelationshipPlatform"
    client.cookies.set("rip_session", "expired")
    response = client.post(BASE + "/auth/logout")
    assert response.status_code == 200 and "rip_session" in response.headers.get("set-cookie", "")


def test_error_envelope_request_id_and_security_headers(auth, client):
    response = auth.get(f"{BASE}/research-requests/00000000-0000-0000-0000-000000000000",
                        headers={"X-Request-ID": "n8n-exec-12345"})
    body = response.json()
    assert response.status_code == 404 and body["code"] == "not_found"
    assert body["retryable"] is False and body["request_id"] == "n8n-exec-12345"
    assert response.headers["X-Request-ID"] == "n8n-exec-12345"
    page = auth.get("/panel")
    assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
    assert page.headers["X-Frame-Options"] == "DENY"
    missing = auth.get("/panel/research/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404 and "text/html" in missing.headers["content-type"]
    assert client.get("/health", headers={"Host": "attacker.example"}).status_code == 400
    assert client.get(BASE + "/dashboard",
                      headers={"Authorization": "Bearer ğğğ".encode()}).status_code == 401


def test_oversized_bodies_are_rejected(auth, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main.settings, "max_request_bytes", 20_000)
    big = {**BRIEF, "description": "x" * 9000, "notes": "y" * 9000, "title": "t" * 200}
    assert auth.post(BASE + "/research-requests", json=big).status_code == 201
    huge = {"candidates": [{**PERSON, "bio": "z" * 15000}] * 3}
    rid = request(auth)
    response = auth.post(f"{BASE}/research-requests/{rid}/candidates/bulk", json=huge)
    assert response.status_code == 413 and response.json()["code"] == "payload_too_large"

    def chunks():
        yield json.dumps(huge).encode()

    chunked = auth.post(f"{BASE}/research-requests/{rid}/candidates/bulk",
                        content=chunks(), headers={"Content-Type": "application/json"})
    assert chunked.status_code == 413


def test_production_configuration_is_validated():
    unsafe = Settings(app_env="production", secret_key="a" * 40, auth_required=False,
                      database_url="sqlite:///x.db", demo_mode=True, allowed_origins="*")
    problems = " ".join(unsafe.production_problems())
    for setting in ("AUTH_REQUIRED", "DATABASE_URL", "DEMO_MODE", "SECRET_KEY", "ALLOWED_ORIGINS"):
        assert setting in problems
    safe = Settings(app_env="production", secret_key="9f8e7d6c5b4a3210" * 4, auth_required=True,
                    database_url="postgresql+psycopg://u:p@db/x", demo_mode=False)
    assert safe.production_problems() == []


def test_panel_templates_never_receive_secrets(auth):
    from app.panel import panel_config

    assert set(panel_config()) == {"auth_required", "live_search_enabled", "sheets_enabled"}
    rid = request(auth)
    with SessionLocal() as db:
        db.get(ResearchRequest, rid).status = "NO_RESULTS"
        db.commit()
    form = auth.get(f"/panel/research/{rid}/edit").text
    assert 'value="NO_RESULTS" selected' in form


# --- integrations ------------------------------------------------------------------------


def sheets_transport(calls, fail_first_write=False):
    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "token"})
        if request.method == "POST" and request.url.path == "/v4/spreadsheets":
            return httpx.Response(200, json={"spreadsheetId": "sheet-1",
                                             "spreadsheetUrl": "https://docs.google.com/x"})
        if request.method == "PUT" and fail_first_write and \
                sum(1 for m, _ in calls if m == "PUT") == 1:
            return httpx.Response(400, json={"error": "bad"})
        return httpx.Response(200, json={})

    return httpx.MockTransport(handler)


def test_sheets_export_resumes_same_sheet_and_replays(auth, monkeypatch):
    import app.api as api

    calls = []
    transport = sheets_transport(calls, fail_first_write=True)
    monkeypatch.setattr(api, "get_sheets_service", lambda: GoogleSheetsProvider(
        client=httpx.Client(transport=transport), retries=0))
    rid = request(auth)
    c = add(auth, rid)
    auth.patch(f"{BASE}/candidates/{c['id']}", json={"status": "APPROVED"})
    endpoint = f"{BASE}/research-requests/{rid}/exports"
    headers = {"Idempotency-Key": "sheets-export-0001"}
    failed = auth.post(endpoint, json={"format": "sheets"}, headers=headers)
    assert failed.status_code == 502
    done = auth.post(endpoint, json={"format": "sheets"}, headers=headers)
    assert done.status_code == 200 and done.json()["row_count"] == 1
    replay = auth.post(endpoint, json={"format": "sheets"}, headers=headers)
    assert replay.json() == done.json()
    assert [c for c in calls if c == ("POST", "/v4/spreadsheets")] == [("POST", "/v4/spreadsheets")]
    with SessionLocal() as db:
        jobs = list(db.scalars(select(ExportJob).where(ExportJob.format == "sheets")))
        assert len(jobs) == 1 and jobs[0].status == "COMPLETED"


def test_sheets_values_are_written_raw_and_retried_on_busy():
    sent, attempts = [], []

    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "t"})
        if request.method == "PUT":
            attempts.append(1)
            if len(attempts) == 1:
                return httpx.Response(503)
            sent.append((dict(request.url.params), json.loads(request.content)))
        return httpx.Response(200, json={})

    provider = GoogleSheetsProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    provider.append_candidates({"id": "s"}, [exported_candidate(full_name="=1+1")])
    params, body = sent[0]
    assert params["valueInputOption"] == "RAW" and body["values"][1][0] == "=1+1"


def test_openai_provider_validates_and_falls_back():
    replies = iter([
        httpx.Response(429),
        httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(
            {"keywords": ["vision"], "summary": "ok"})}}], "usage": {"total_tokens": 9}}),
        httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]}),
    ])
    client = httpx.Client(transport=httpx.MockTransport(lambda request: next(replies)))
    provider = OpenAIProvider(client=client, retries=1)
    result = provider.interpret("AI", "")
    assert result["keywords"] == ["vision"] and result["prompt_version"]
    with pytest.raises(AIServiceError):
        provider.interpret("AI", "")


# --- maintenance -------------------------------------------------------------------------


def test_maintenance_purges_expired_sessions_keys_and_old_page_text(auth, monkeypatch):
    rid = request(auth)
    auth.post(f"{BASE}/research-requests/{rid}/collect")
    run_next(Discovery(), Fetcher())
    with SessionLocal() as db:
        user = db.scalar(select(User).limit(1))
        db.add(LoginSession(token_hash="x" * 64, user_id=user.id,
                            expires_at=now() - timedelta(hours=1)))
        db.add(IdempotencyRecord(scope="s", key="old-key-000", fingerprint="f", status_code=200,
                                 response={}, created_at=now() - timedelta(days=8)))
        for document in db.scalars(select(SourceDocument)):
            document.created_at = now() - timedelta(days=200)
        db.commit()
    run_maintenance()
    with SessionLocal() as db:
        assert db.get(LoginSession, "x" * 64) is None
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0
        assert all(d.text == "" for d in db.scalars(select(SourceDocument)))
        assert db.scalar(select(func.count()).select_from(Candidate)) == 1


# --- review follow-ups ---------------------------------------------------------------------


def test_job_interrupted_during_search_reruns_the_search_on_resume(auth):
    stop = threading.Event()
    calls = []

    class StopWhileSearching:
        def discover(self, query, limit, page=1):
            calls.append(query)
            stop.set()
            return Discovery().discover(query, limit)

    rid = request(auth)
    auth.post(f"{BASE}/research-requests/{rid}/collect")
    run_next(StopWhileSearching(), Fetcher(), stop_event=stop)
    with SessionLocal() as db:
        job = db.scalar(select(CollectionJob))
        assert job.status == "QUEUED" and job.stats.get("stage", "") == ""
    first_run = len(calls)
    run_next(StopWhileSearching(), Fetcher())
    assert len(calls) > first_run  # primary queries ran again instead of being skipped
    job = auth.get(f"{BASE}/research-requests/{rid}/collection").json()["job"]
    assert job["status"] in ("PARTIAL", "COMPLETED") and job["created_count"] == 1
    assert job["stats"]["candidate_ids"] and job["stats"]["stage"].startswith("round:")


def test_staff_pages_differing_by_query_are_different_people():
    ali = existing(full_name="Ali Can", website="https://uni.edu/personel.aspx?id=5")
    assert deduplicate_candidates([ali], incoming(
        full_name="Ali Rıza Can", website="https://uni.edu/personel.aspx?id=9")) is None
    assert deduplicate_candidates([ali], incoming(
        full_name="Ali Rıza Can", website="https://uni.edu/personel.aspx?id=5")) is None
    assert deduplicate_candidates([ali], incoming(
        full_name="ALI CAN", website="https://www.uni.edu/personel.aspx?id=5")) is ali


def test_linkedin_subpages_and_encoding_are_the_same_profile():
    person = existing(full_name="Gülşen Eryiğit", linkedin_url="https://www.linkedin.com/in/g%C3%BCl%C5%9Fen")
    for url in ("https://tr.linkedin.com/in/gülşen/details/experience/",
                "https://linkedin.com/in/G%C3%BCl%C5%9Fen?locale=en"):
        assert deduplicate_candidates([person], incoming(full_name="Gülşen Eryiğit",
                                                         linkedin_url=url)) is person


def test_junk_bearer_tokens_cannot_exhaust_the_integration_rate_limit(client, monkeypatch):
    import os

    import app.main as main

    monkeypatch.setattr(main.settings, "rate_limit_per_minute", 10)
    for _ in range(12):
        client.get(BASE + "/dashboard", headers={"Authorization": "Bearer junk"})
    service = client.get(BASE + "/research-requests",
                         headers={"Authorization": "Bearer " + os.environ["N8N_API_KEY"]})
    assert service.status_code == 200


def test_sheets_key_reused_for_another_research_never_touches_its_sheet(auth, monkeypatch):
    import app.api as api

    calls = []
    transport = sheets_transport(calls, fail_first_write=True)
    monkeypatch.setattr(api, "get_sheets_service", lambda: GoogleSheetsProvider(
        client=httpx.Client(transport=transport), retries=0))
    first, second = request(auth), request(auth)
    headers = {"Idempotency-Key": "shared-sheets-key-1"}
    assert auth.post(f"{BASE}/research-requests/{first}/exports", json={"format": "sheets"},
                     headers=headers).status_code == 502
    assert auth.post(f"{BASE}/research-requests/{second}/exports", json={"format": "sheets"},
                     headers=headers).status_code == 200
    with SessionLocal() as db:
        jobs = {j.research_request_id: j for j in db.scalars(select(ExportJob))}
    assert jobs[first].status == "FAILED" and jobs[second].status == "COMPLETED"
    assert calls.count(("POST", "/v4/spreadsheets")) == 2


def test_titles_in_names_do_not_hide_duplicates():
    person = existing(full_name="Leyla Haddad", public_email="leyla.haddad@example.org")
    for name in ("Dr. Leyla Haddad", "Doç. Dr. Leyla Haddad", "Prof. Dr. LEYLA HADDAD"):
        assert deduplicate_candidates([person], incoming(
            full_name=name, public_email="Leyla.Haddad@example.org")) is person
    # A title never makes two different people match.
    assert deduplicate_candidates([person], incoming(
        full_name="Dr. Selin Haddad", public_email="leyla.haddad@example.org")) is None
