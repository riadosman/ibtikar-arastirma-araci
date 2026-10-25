import socket
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_workflow import BASE, BRIEF, request

from app.core.db import SessionLocal
from app.models import CollectionJob, ResearchRequest, now
from app.services import fetching
from app.services.collection import recover_jobs, run_next
from app.services.discovery import SearchHit, build_queries
from app.services.extraction import extract_profiles, person_name
from app.services.fetching import FetchError, public_target
from app.services.recovery import recover_interrupted_research

PROFILE = b"""<html><head><title>Ada Lovelace</title><script type="application/ld+json">
{"@type":"Person","name":"Ada Lovelace","jobTitle":"Researcher","worksFor":{"name":"Example Lab"}}
</script></head><body><h1>Ada Lovelace</h1><p>Computer Vision researcher.</p></body></html>"""


class Discovery:
    def discover(self, query, limit, page=1):
        return [
            SearchHit("https://example.com/profile", "Ada Lovelace", "Researcher"),
            SearchHit("https://example.org/failure", "Unavailable profile", ""),
        ]


class Fetcher:
    def fetch(self, url):
        if "failure" in url:
            raise FetchError("Source returned HTTP 403")
        return url, PROFILE


def test_query_uses_academic_brief_and_cleans_copied_keywords():
    research = SimpleNamespace(field="AI", location="istanbul", target_type="Expert",
                               description="Konuşabilecek akademisyenleri bul",
                               notes="Üniversite profil sayfası",
                               keywords=[SimpleNamespace(value="&#32;machine learning")])
    queries = build_queries(research)
    # An academic brief for a Turkish city: staff lists in Turkish, the keyword in round 1.
    assert queries[0] == "yapay zekâ İstanbul akademik kadro"
    assert "makine öğrenmesi İstanbul akademisyen" in queries
    assert not any("&#" in query for query in queries)


def test_readable_sources_without_people_do_not_report_ready(auth):
    class EmptyFetcher:
        def fetch(self, url):
            return url, b"<title>AI consulting</title><h1>Our services</h1>"

    rid = request(auth)
    endpoint = f"{BASE}/research-requests/{rid}"
    auth.post(endpoint + "/collect")
    run_next(Discovery(), EmptyFetcher())
    state = auth.get(endpoint + "/collection").json()
    assert state["job"]["status"] == "NO_RESULTS"
    assert "Aranacak yeni kaynak kalmadı" in state["job"]["error"]
    assert "kaynakla doğrulanabilen kişi bulunamadı" in state["job"]["error"]
    assert auth.get(endpoint).json()["status"] == "NO_RESULTS"


def test_duplicate_profiles_do_not_consume_unique_target(auth):
    class RepeatedDiscovery:
        def discover(self, query, limit, page=1):
            return [SearchHit(f"https://example.com/{i}", "Profile", "") for i in range(3)]

    class RepeatedFetcher:
        def fetch(self, url):
            return url, PROFILE if not url.endswith("2") else PROFILE.replace(b"Ada Lovelace", b"Grace Hopper")

    rid = request(auth)
    endpoint = f"{BASE}/research-requests/{rid}"
    assert auth.patch(endpoint, json={**BRIEF, "requested_quantity": 2, "status": "CREATED"}).status_code == 200
    auth.post(endpoint + "/collect")
    run_next(RepeatedDiscovery(), RepeatedFetcher())
    rows = auth.get(endpoint + "/candidates").json()["items"]
    assert {row["full_name"] for row in rows} == {"Ada Lovelace", "Grace Hopper"}


def test_collection_queue_partial_results_and_retry(auth):
    rid = request(auth)
    endpoint = f"{BASE}/research-requests/{rid}"
    queued = auth.post(endpoint + "/collect")
    assert queued.status_code == 202
    assert auth.post(endpoint + "/collect").status_code == 409
    assert auth.post(endpoint + "/complete").status_code == 409
    with SessionLocal() as db:
        assert recover_interrupted_research(db) == 0  # API restart must not kill worker jobs.
    assert run_next(Discovery(), Fetcher())
    state = auth.get(endpoint + "/collection").json()
    assert state["job"]["status"] == "PARTIAL"
    assert state["job"]["processed"] == 2
    assert {s["status"] for s in state["sources"]} == {"EXTRACTED", "FAILED"}
    candidates = auth.get(endpoint + "/candidates").json()["items"]
    assert len(candidates) == 1 and candidates[0]["status"] == "NEW"
    assert candidates[0]["is_demo"] is False
    cid = candidates[0]["id"]
    assert auth.get(f"/panel/candidates/{cid}").status_code == 200
    assert (
        auth.patch(
            f"{BASE}/candidates/{cid}", json={"status": "APPROVED", "notes": "Reviewed"}
        ).status_code
        == 200
    )
    assert auth.post(endpoint + "/collect").status_code == 202
    assert run_next(Discovery(), Fetcher())
    candidate = auth.get(f"{BASE}/candidates/{cid}").json()
    assert candidate["status"] == "APPROVED" and candidate["notes"] == "Reviewed"
    assert auth.get(endpoint + "/collection").json()["job"]["merged_count"] == 1
    assert not run_next(Discovery(), Fetcher())


def test_failed_discovery_and_stale_jobs(auth):
    class Unavailable:
        def discover(self, query, limit, page=1):
            raise RuntimeError("provider secret must not escape")

    rid = request(auth)
    endpoint = f"{BASE}/research-requests/{rid}"
    auth.post(endpoint + "/collect")
    run_next(Unavailable(), Fetcher())
    state = auth.get(endpoint + "/collection").json()
    assert state["job"]["status"] == "FAILED"
    assert "secret" not in state["job"]["error"]
    auth.post(endpoint + "/collect")
    with SessionLocal() as db:
        job = db.scalar(select(CollectionJob).where(CollectionJob.status == "QUEUED"))
        # A worker crash: RUNNING without a recent heartbeat is requeued, not lost.
        job.status, job.attempts = "RUNNING", 1
        job.updated_at = now() - timedelta(minutes=11)
        db.commit()
        recover_jobs(db)
        assert db.get(CollectionJob, job.id).status == "QUEUED"
        # After the last allowed attempt it fails and the request becomes retryable.
        job.status, job.attempts = "RUNNING", 2
        job.heartbeat_at = now() - timedelta(minutes=11)
        db.commit()
        recover_jobs(db)
        assert db.get(ResearchRequest, rid).status == "FAILED"
        assert db.get(CollectionJob, job.id).status == "FAILED"
    assert auth.post(endpoint + "/collect").status_code == 202


def test_extraction_does_not_invent_people_or_fields():
    text, profiles = extract_profiles(PROFILE, "https://example.com", "Profile")
    assert len(profiles) == 1
    assert profiles[0].organization == "Example Lab"
    assert profiles[0].location is None and profiles[0].public_email is None
    assert person_name("Computer Vision") is None
    assert person_name("Faculty Members") is None
    assert person_name("Program Structure") is None
    assert person_name("A EuroHPC Success Story") is None
    assert person_name("Prof. Dr. Ayşe Yılmaz") == "Ayşe Yılmaz"
    _, profiles = extract_profiles(
        b"<title>Faculty</title><h1>Ada Lovelace</h1>", "https://example.com"
    )
    assert profiles == []
    html = PROFILE.replace(
        b"</head>",
        b"""<script type="application/ld+json">{"@type":"Person","name":"Kate Lakin","jobTitle":"Editor"}</script></head>""",
    )
    assert [p.full_name for p in extract_profiles(html, "https://example.com/ada-lovelace")[1]] == [
        "Ada Lovelace"
    ]


def test_directory_extraction_requires_name_in_profile_url():
    html = b"""<title>Faculty members</title><h1>Faculty members</h1>
    <div class="profile-card"><a href="/faculty/ada-lovelace">Ada Lovelace</a></div>
    <a href="/news">Random Heading</a><a href="/department/computer-vision">Computer Vision</a>
    <a href="/people/support-staff">Support Staff</a><a href="/academic/program-structure">Program Structure</a>
    <a href="/staff/former-academics">Former Academics</a>
    <a href="javascript:alert(1)">Grace Hopper</a>"""
    _, profiles = extract_profiles(html, "https://example.com/people", "Faculty members")
    assert [p.full_name for p in profiles] == ["Ada Lovelace"]
    assert profiles[0].sources[0].url == "https://example.com/people"
    assert profiles[0].website == "https://example.com/faculty/ada-lovelace"
    assert profiles[0].organization is None


def test_staff_cards_require_name_role_and_profile_in_same_card():
    html = b'''<title>Staff</title><h1>Staff</h1>
    <div class="team-member"><div class="team-desc"><h3>Ada Lovelace</h3>
    <span>Prof. Dr.</span><a href="/u/al123">Profil</a></div></div>
    <div class="team-member"><h3>Random Heading</h3><a href="/news">Profile</a></div>
    <nav><div class="team-member"><h3>Grace Hopper</h3><span>Professor</span>
    <a href="/u/gh">Profile</a></div></nav>'''
    profiles = extract_profiles(html, "https://example.com/staff")[1]
    assert len(profiles) == 1
    assert profiles[0].full_name == "Ada Lovelace"
    assert profiles[0].job_title == "Prof. Dr."
    assert profiles[0].website == "https://example.com/u/al123"
    assert profiles[0].source_url == "https://example.com/staff"
    assert profiles[0].organization is None and profiles[0].field is None


def test_source_backed_name_dedup_without_organization(auth):
    rid = request(auth)
    endpoint = f"{BASE}/research-requests/{rid}/candidates"
    person = {"full_name": "Ada Lovelace", "source_url": "https://example.com/ada"}
    first = auth.post(endpoint, json=person).json()
    second = auth.post(endpoint, json=person).json()
    assert first["created"] == 1 and second["merged"] == 1
    different = auth.post(
        endpoint, json={**person, "source_url": "https://example.org/other-ada"}
    ).json()
    assert different["created"] == 1


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.1.2"]
)
def test_fetch_blocks_nonpublic_dns(monkeypatch, address):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", (address, 443))]
    )
    with pytest.raises(FetchError):
        public_target("https://public-looking.example/profile")


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "http://user:pass@example.com", "http://example.com:8080"]
)
def test_fetch_rejects_unsupported_urls(url):
    with pytest.raises(FetchError):
        public_target(url)


def test_redirect_rechecks_destination_before_connecting(monkeypatch):
    connected = []
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *args, **kwargs: [
            (2, 1, 6, "", ("127.0.0.1" if host == "private.test" else "93.184.216.34", 443))
        ],
    )

    class Redirect:
        status = 302

        def getheader(self, name, default=None):
            return "https://private.test/" if name == "Location" else default

    class Connection:
        def __init__(self, host, *args):
            connected.append(host)

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Redirect()

        def close(self):
            pass

    monkeypatch.setattr(fetching, "PinnedHTTP", Connection)
    with pytest.raises(FetchError, match="Non-public"):
        fetching.fetch_public("https://public.test/")
    assert connected == ["public.test"]


def test_response_size_is_bounded(monkeypatch):
    monkeypatch.setattr(
        fetching, "public_target", lambda url: (fetching.urlsplit(url), "93.184.216.34", 443)
    )

    class Response:
        status = 200

        def read(self, size):
            return b"x" * size

        def getheader(self, name, default=None):
            return default

    class Connection:
        def __init__(self, *args):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(fetching, "PinnedHTTP", Connection)
    with pytest.raises(FetchError, match="size limit"):
        fetching.fetch_public("https://public.test/", limit=10)


def test_panel_auth_and_safe_rendering(auth, client):
    rid = request(auth)
    for path in [
        "/panel",
        f"/panel/research/{rid}",
        "/panel/research/new",
        "/panel/settings",
        "/panel/users",
    ]:
        response = auth.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    auth.post(
        f"{BASE}/research-requests/{rid}/candidates",
        json={"full_name": "<script>alert(1)</script>", "source_url": "https://example.com"},
    )
    page = auth.get(f"/panel/research/{rid}").text
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    auth.post(BASE + "/auth/logout")
    assert client.get("/panel", follow_redirects=False).status_code == 303
