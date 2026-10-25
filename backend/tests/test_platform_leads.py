"""Profile platforms (LinkedIn, ResearchGate, ...) are searched but never fetched.

Their robots.txt or HTTP 403 forbids automated retrieval. A search engine's result for a
profile still names a person, a role and an organization: that is kept as an unverified
lead, clearly labeled, never as page evidence.
"""

from types import SimpleNamespace

import pytest
from test_collection import PROFILE
from test_workflow import BASE

from app.services.collection import run_next
from app.services.discovery import SearchHit, query_rounds
from app.services.platforms import never_fetch, profile_lead

FOUNDERS = {
    "title": "Yapay zekâ girişim kurucuları",
    "field": "teknoloji",
    "location": "istanbul",
    "target_type": "kurucu",
    "description": "cto veya kurucu arıyoruz",
    "requested_quantity": 2,
    "keywords": ["yapay zeka girisim"],
    "search_language": "tr",
}
EMPTY = b"<html><title>Portal</title><h1>Haberler</h1><p>Genel duyurular.</p></html>"


def lead(url, title, snippet="", location="istanbul"):
    return profile_lead(url, title, snippet, location)


@pytest.mark.parametrize("url, title, snippet, expected", [
    ("https://tr.linkedin.com/in/sabrikustur", "Sabri Küstür - Founder, Kurucu - TeknolojiSK | LinkedIn",
     "Founder · Deneyim: TeknolojiSK · Konum: İstanbul · 500+ bağlantı",
     ("Sabri Küstür", "Founder, Kurucu", "TeknolojiSK", "İstanbul")),
    # Yahoo glues the next result's title onto LinkedIn titles.
    ("https://www.linkedin.com/in/ayse-demir", "Ayşe Demir - Lab Manager at ISK Biosciences | LinkedInAshley Brown - Student",
     "Experience: ISK · Location: Memphis", ("Ayşe Demir", "Lab Manager", "ISK Biosciences", "Memphis")),
    ("https://tr.linkedin.com/in/degerayata", "Deger Ayata, PhD - Founder CEO & Chief AI ... - LinkedIn",
     "", ("Deger Ayata", "Founder CEO & Chief AI", None, None)),
    ("https://www.crunchbase.com/person/cihan-eker",
     "Cihan Eker - Co-Founder and CTO @ Nimbu IT Services - Crunchbase", "",
     ("Cihan Eker", "Co-Founder and CTO", "Nimbu IT Services", None)),
    ("https://www.f6s.com/member/hakan-bulgurlu1", "Hakan BULGURLU | CTO at GroviaHub | F6S Member Profile", "",
     ("Hakan BULGURLU", "CTO", "GroviaHub", None)),
    ("https://www.theofficialboard.com/biography/hakan-saglam-94g23",
     "Hakan Saglam Bio - Dream Games CTO - The Official Board", "", ("Hakan Saglam", "Dream Games CTO", None, None)),
    ("https://www.researchgate.net/profile/Taner-Cevik",
     "Taner CEVIK | Professor | PhD | Istanbul Rumeli University, Istanbul ...", "",
     ("Taner CEVIK", "Professor", "Istanbul Rumeli University, Istanbul", "istanbul")),
    ("https://tr.linkedin.com/in/ismail-önden-03a2b333",
     "İsmail Önden - Prof. Dr. - Istanbul University - Computer and ...", "",
     ("İsmail Önden", "Prof. Dr.", "Istanbul University", "istanbul")),
])
def test_search_result_titles_become_leads(url, title, snippet, expected):
    found = lead(url, title, snippet)
    assert (found.full_name, found.job_title, found.organization, found.location) == expected
    assert found.source_type == "platform_search_result"
    assert title.split(" |")[0][:40] in found.source_evidence
    assert found.source_url == url
    if "linkedin.com" in url:
        assert found.linkedin_url == url


def test_a_postal_code_is_not_a_location():
    # Turkish LinkedIn snippets sometimes show "Konum: 34093" instead of a city.
    found = lead("https://tr.linkedin.com/in/sena-kacar", "Sena Kaçar - Akademisyen | LinkedIn",
                 "Akademisyen · Konum: 34093 · 12 bağlantı")
    assert found.full_name == "Sena Kaçar" and found.location is None


@pytest.mark.parametrize("url, title", [
    ("https://www.linkedin.com/jobs/view/cto-at-ft-teknoloji-3443435944", "FT Teknoloji hiring CTO | LinkedIn"),
    ("https://www.linkedin.com/company/hepsiburada", "Hepsiburada | LinkedIn"),
    ("https://tr.linkedin.com/in/hepsiburada-cto", "Chief Technology Officer - CTO at Hepsiburada - LinkedIn"),
    ("https://tr.linkedin.com/in/kurucu-uyelerimiz", "Kurucu Üyelerimiz | LinkedIn"),
    ("https://example.org/in/ada", "Ada Lovelace - Founder | Example"),
])
def test_pages_that_are_not_a_named_person_are_not_leads(url, title):
    assert lead(url, title) is None


def test_closed_platforms_are_never_fetched():
    for url in ("https://tr.linkedin.com/in/x", "https://www.researchgate.net/profile/X",
                "https://scholar.google.com/citations?user=a", "https://www.instagram.com/p/x/",
                "https://x.com/someone", "https://www.crunchbase.com/person/x"):
        assert never_fetch(url), url
    for url in ("https://notlinkedin.com/in/x", "https://www.itu.edu.tr/linkedin"):
        assert not never_fetch(url), url


def start(auth, **overrides):
    rid = auth.post(BASE + "/research-requests", json={**FOUNDERS, **overrides}).json()["id"]
    assert auth.post(f"{BASE}/research-requests/{rid}/collect").status_code == 202
    return rid


def linkedin(name, role="Kurucu", org="Örnek Yapay Zeka"):
    slug = name.lower().replace(" ", "-")
    return SearchHit(f"https://tr.linkedin.com/in/{slug}", f"{name} - {role} - {org} | LinkedIn",
                     f"{role} · Deneyim: {org} · Konum: İstanbul")


def test_platform_results_become_labeled_leads_without_fetching(auth):
    rid = start(auth)
    fetched = []

    class Provider:
        def discover(self, query, limit, page=1):
            return [linkedin("Selin Aksoy"),
                    SearchHit("https://tr.linkedin.com/in/serkan-kav", "Serkan Kav - 22+ Yıl Deneyim | LinkedIn", ""),
                    SearchHit("https://www.linkedin.com/jobs/view/1", "Hiring CTO | LinkedIn", ""),
                    SearchHit("https://example.org/haber", "Haber", "")]

    class Reader:
        def fetch(self, url):
            fetched.append(url)
            return url, EMPTY

    run_next(Provider(), Reader())
    assert fetched == ["https://example.org/haber"]
    people = auth.get(f"{BASE}/research-requests/{rid}/candidates").json()["items"]
    assert [p["full_name"] for p in people] == ["Selin Aksoy"]
    person = auth.get(f"{BASE}/candidates/{people[0]['id']}").json()
    assert person["organization"] == "Örnek Yapay Zeka" and person["location"] == "İstanbul"
    assert person["confidence_score"] <= 15
    assert "doğrulanmadı" in person["relevance_reason"]
    assert person["sources"][0]["source_type"] == "platform_search_result"
    sources = {s["url"]: s for s in auth.get(f"{BASE}/research-requests/{rid}/collection").json()["sources"]}
    assert sources["https://tr.linkedin.com/in/selin-aksoy"]["status"] == "EXTRACTED"
    assert "doğrulanmadı" in sources["https://tr.linkedin.com/in/selin-aksoy"]["error"]
    assert sources["https://www.linkedin.com/jobs/view/1"]["status"] == "SKIPPED"
    job = auth.get(f"{BASE}/research-requests/{rid}/collection").json()["job"]
    # Leads alone never complete a request: the target asks for page-verified people.
    assert job["status"] == "PARTIAL" and "ipucu" in job["error"]
    assert job["stats"]["platform_leads"] == 1
    page = auth.get(f"/panel/research/{rid}").text
    assert "Platform ipucu · doğrulanmadı" in page and "1 kişi LinkedIn gibi platformların" in page


def test_leads_do_not_stop_the_search_for_verified_people(auth):
    rid = start(auth, requested_quantity=1)
    rounds = query_rounds(SimpleNamespace(**{**FOUNDERS, "keywords": [SimpleNamespace(value="yapay zeka girisim")]},
                                          notes=""))
    late = set(rounds[2])
    names = iter(["Ada Yılmaz", "Can Demir", "Ece Kaya", "Deniz Acar", "Elif Şahin", "Mert Aydın",
                  "Zeynep Arslan", "Kaan Öztürk", "Ece Aksoy", "Ali Çelik", "Burak Tan", "Defne Er"] * 3)

    class Provider:
        def discover(self, query, limit, page=1):
            hits = [linkedin(next(names))]
            if query in late:
                hits.append(SearchHit(f"https://example.org/people/{abs(hash(query))}", "Ekip", ""))
            return hits

    class Reader:
        def fetch(self, url):
            return url, PROFILE.replace(b"Researcher", b"Kurucu")

    run_next(Provider(), Reader())
    job = auth.get(f"{BASE}/research-requests/{rid}/collection").json()["job"]
    assert job["status"] == "COMPLETED" and job["stats"]["search_rounds"] == 3
    people = auth.get(f"{BASE}/research-requests/{rid}/candidates").json()["items"]
    assert "Ada Lovelace" in [p["full_name"] for p in people]
    leads = [p for p in people if p["full_name"] != "Ada Lovelace"]
    # At most as many unverified leads as people requested.
    assert len(leads) == 1


def test_founder_brief_searches_its_keywords_first_then_profile_platforms():
    research = SimpleNamespace(**{**FOUNDERS, "keywords": [SimpleNamespace(value="yapay zeka girisim")]}, notes="")
    rounds = query_rounds(research)
    assert "yapay zeka girisim İstanbul CTO kurucu" in rounds[0]
    assert rounds[1] == ["linkedin yapay zeka girisim CTO kurucu İstanbul", "linkedin teknoloji CTO kurucu İstanbul"]


def test_academic_brief_also_searches_researchgate():
    research = SimpleNamespace(title="Mentorlar", field="AI and Math", location="istanbul",
                               target_type="Akademisyen", description="", notes="", requested_quantity=5,
                               keywords=[], search_language="tr")
    platform = query_rounds(research)[1]
    assert platform == ["linkedin yapay zekâ akademisyen İstanbul", "researchgate yapay zekâ İstanbul",
                        "linkedin matematik akademisyen İstanbul", "researchgate matematik İstanbul"]
