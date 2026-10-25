from types import SimpleNamespace

import pytest
from test_collection import PROFILE, Discovery, Fetcher
from test_workflow import BASE, BRIEF, request

from app.services.collection import run_next
from app.services.discovery import SearchHit, build_queries
from app.services.extraction import extract_profiles
from app.services.fetching import FetchError

BIO = """<article><h1>Şefler</h1><div><span>Chef Ayşe Yılmaz</span></div>
<div>Chef Ayşe Yılmaz gastronomi alanında çalışır. Yemek yarışmalarında jüri olarak
görev alır ve öğrencilere mutfak eğitimi verir.</div></article>""".encode()


def test_culinary_context_is_not_mistaken_for_academic_role():
    research = SimpleNamespace(field="gastronomi", location="Turkiye", target_type="Expert",
                               description="universite ogrencileri arasinda pisirme yarismasi",
                               notes="basarili kisiler", keywords=[SimpleNamespace(value="chef yemek")])
    assert "şef" in build_queries(research)[0]
    assert not any("professor" in query for query in build_queries(research))
    research.target_type = "Öğrenci"  # the brief's own words for an unknown role are searched
    assert any("Öğrenci" in query for query in build_queries(research))


def test_named_biography_has_local_evidence_and_no_invented_fields():
    people = extract_profiles(BIO, "https://example.org/chefs", "Şefler")[1]
    assert len(people) == 1
    person = people[0]
    assert person.full_name == "Ayşe Yılmaz" and person.job_title == "Chef"
    assert "jüri" in person.bio and person.source_type == "named_biography"
    assert person.location is None and person.organization is None


@pytest.mark.parametrize("prefix", ["1. ", "2) ", "3 - "])
def test_numbered_turkish_biography_sections(prefix):
    html = BIO.decode().replace("<span>Chef Ayşe Yılmaz</span>",
                                f"<strong>{prefix}Şef Ayşe Yılmaz</strong>")
    people = extract_profiles(html.encode(), "https://example.org/chefs")[1]
    assert len(people) == 1
    assert people[0].full_name == "Ayşe Yılmaz"
    assert people[0].job_title == "Şef"


@pytest.mark.parametrize("heading, url", [
    ("Öğretim Üyeleri", "https://mse.example.edu.tr/tr/ogretim-uyeleri"),
    ("Yapay Zeka Konuşmacıları", "https://agency.example.com.tr/yapay-zeka-konusmacilari"),
    ("Ünlü Akademisyen", "https://example.com/tr/unlu-akademisyen/"),
    ("Kurucu Üyelerimiz", "https://dernek.example.org/kurucu-uyelerimiz/"),
    ("Danışmanlarımız", "https://dernek.example.org/danismanlarimiz/"),
])
def test_listing_page_heading_is_not_a_person(heading, url):
    # Live pages: the heading matched the URL slug and the list mentioned "Prof. Dr.".
    html = (f"<title>{heading}</title><h1>{heading}</h1>"
            "<p>Prof. Dr. Jale Çakıroğlu Oda: EFA-112 Araştırma Alanları: Fen Eğitimi</p>")
    # The titled name in the list is a person; the heading never is, and "Oda:" is a label.
    people = extract_profiles(html.encode(), url)[1]
    assert [(p.full_name, p.job_title) for p in people] == [("Jale Çakıroğlu", "Prof. Dr.")]


SITE_ORGANIZATION = ('<script type="application/ld+json">{"@context": "https://schema.org", "@graph": ['
                     '{"@type": "Organization", "name": "Örnek Fintek Derneği"},'
                     '{"@type": "WebPage", "name": "Ekip"}]}</script>')


def test_site_wide_organization_markup_does_not_hide_the_people_on_a_page():
    # SEO plugins add the site's Organization to every page; Wikipedia adds its publisher.
    team = (f"<title>Ekip - Örnek Fintek Derneği</title>{SITE_ORGANIZATION}<h1>Ekip</h1>"
            '<div class="team-member"><h3>Selin Aksoy</h3><span>Kurucu Ortak</span>'
            '<a href="/ekip/selin-aksoy">Profil</a></div>')
    people = extract_profiles(team.encode(), "https://fintek.example.org/ekip/", "Ekip")[1]
    assert [p.full_name for p in people] == ["Selin Aksoy"]
    article = ('<title>Deniz Acar - Vikipedi</title><script type="application/ld+json">'
               '{"@type": "Article", "name": "Deniz Acar", "publisher": {"@type": "Organization",'
               ' "name": "Wikimedia Foundation, Inc."}}</script><h1>Deniz Acar</h1>'
               "<p>Deniz Acar, Türk mühendis ve bir yapay zekâ şirketinin kurucusudur.</p>")
    people = extract_profiles(article.encode(), "https://tr.wikipedia.org/wiki/Deniz_Acar")[1]
    assert [p.full_name for p in people] == ["Deniz Acar"]


def test_a_name_the_page_declares_as_an_organization_is_not_a_person():
    page = ('<script type="application/ld+json">{"@type": "Organization", "name": "Atlas Systems"}'
            "</script><h1>Atlas Systems</h1><p>Atlas Systems engineer CTO founder</p>")
    assert extract_profiles(page.encode(), "https://fixture.example/people/Atlas-Systems")[1] == []


def test_navigation_names_and_unsubstantiated_labels_are_not_people():
    html = BIO.replace(b"<article>", b"<nav>").replace(b"</article>", b"</nav>")
    assert extract_profiles(html, "https://example.org")[1] == []
    assert extract_profiles(b"<h2>Chef Random Person</h2><p>Our recipes</p>", "https://example.org")[1] == []


def test_empty_primary_search_automatically_tries_alternative_queries(auth):
    queries = []

    class Provider:
        def discover(self, query, limit, page=1):
            queries.append(query)
            # Only a query from a later round finds the page that lists someone.
            if len(queries) > 4:
                return [SearchHit("https://example.org/chef", "Şefler", "")]
            return [SearchHit("https://example.org/portal", "Gastronomi", "")]

    class Reader:
        def fetch(self, url):
            return url, BIO if url.endswith("chef") else b"<h1>Gastronomi portal</h1>"

    rid = request(auth)
    endpoint = f"{BASE}/research-requests/{rid}"
    auth.post(endpoint + "/collect")
    loading = auth.get(f"/panel/research/{rid}")
    assert loading.status_code == 200
    assert "data-collection=" in loading.text and "Diğer araştırmalara geç" in loading.text
    run_next(Provider(), Reader())
    result = auth.get(endpoint + "/collection").json()
    assert result["job"]["created_count"] == 1
    assert len(queries) > 4


def test_existing_reviewed_people_survive_empty_or_blocked_retry(auth):
    rid = request(auth)
    endpoint = f"{BASE}/research-requests/{rid}"
    auth.post(endpoint + "/collect")
    run_next(Discovery(), Fetcher())
    person = auth.get(endpoint + "/candidates").json()["items"][0]
    auth.patch(f"{BASE}/candidates/{person['id']}", json={"status": "APPROVED", "notes": "Keep me"})

    class Blocked:
        def fetch(self, url):
            raise FetchError("Source returned HTTP 403")

    auth.post(endpoint + "/collect")
    run_next(Discovery(), Blocked())
    assert auth.get(endpoint).json()["status"] == "READY_FOR_REVIEW"
    saved = auth.get(f"{BASE}/candidates/{person['id']}").json()
    assert saved["status"] == "APPROVED" and saved["notes"] == "Keep me"


def test_progress_is_live_lightweight_and_target_stops_unneeded_fetches(auth):
    rid = auth.post(BASE + "/research-requests", json={**BRIEF, "requested_quantity": 1}).json()["id"]
    endpoint = f"{BASE}/research-requests/{rid}"
    reads = []

    class Reader:
        def fetch(self, url):
            reads.append(url)
            status = auth.get(endpoint + "/collection?summary=true").json()
            assert status["progress"]["current_source"] == url
            assert status["progress"]["phase"] == "reading"
            assert all("text" not in source for source in status["sources"])
            return url, PROFILE

    auth.post(endpoint + "/collect")
    run_next(Discovery(), Reader())
    assert len(reads) == 1
    summary = auth.get(endpoint + "/collection?summary=true").json()
    assert summary["job"]["status"] == "COMPLETED"
    assert summary["job"]["processed"] == summary["job"]["discovered"] == 2
    assert summary["progress"]["blocked"] == 0
    assert summary["total_candidates"] == 1
    assert summary["candidates"][0]["full_name"] == "Ada Lovelace"
