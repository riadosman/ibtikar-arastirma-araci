"""Collection with triage, best-first reading, ranked imports, place-aware targets and link following."""

from ddgs.exceptions import DDGSException
from test_workflow import BASE

from app.core.config import get_settings
from app.services.collection import run_next
from app.services.discovery import PublicSearchProvider, SearchHit

BRIEF = {
    "title": "Yapay zekâ akademisyenleri", "field": "Yapay Zeka", "location": "İstanbul",
    "target_type": "Akademisyen", "requested_quantity": 2, "keywords": [], "search_language": "tr",
}


def staff_page(city, people, title="Akademik Kadro - Örnek Üniversitesi"):
    cards = "".join(f'<div class="card"><h5>Prof. Dr. {name}</h5><p>Araştırma Alanları: {area}</p></div>'
                    for name, area in people)
    return (f"<html><head><title>{title}</title></head><body><h1>Akademik Kadro</h1>"
            f'<div class="grid">{cards}</div><footer><address>Kampüs, {city}</address></footer>'
            "</body></html>").encode()


def start(auth, **overrides):
    response = auth.post(BASE + "/research-requests", json={**BRIEF, **overrides})
    assert response.status_code == 201, response.text
    rid = response.json()["id"]
    assert auth.post(f"{BASE}/research-requests/{rid}/collect").status_code == 202
    return rid


def collection(auth, rid):
    return auth.get(f"{BASE}/research-requests/{rid}/collection").json()


def candidates(auth, rid):
    return auth.get(f"{BASE}/research-requests/{rid}/candidates").json()["items"]


def test_job_ads_are_skipped_unread_and_people_lists_are_read_first(auth):
    rid = start(auth)
    fetched = []

    class Provider:
        def discover(self, query, limit, page=1):
            return [
                SearchHit("https://news.example.com/teknoloji/1", "Teknoloji haberleri", "", "yahoo", 1),
                SearchHit("https://ilan.example.com/akademik/1", "Öğretim Üyesi Alım İlanı 2026", "", "yahoo", 2),
                SearchHit("https://cs.example.edu.tr/akademik-kadro", "Akademik Kadro - Yapay Zeka", "", "yahoo", 3),
            ] if page == 1 else []

    class Reader:
        def fetch(self, url):
            fetched.append(url)
            if "akademik-kadro" in url:
                return url, staff_page("İstanbul", [("Ayşe Kaya", "Yapay Zeka"), ("Can Demir", "Robotik")])
            return url, b"<title>Haber</title><h1>Haber</h1><p>Genel haber.</p>"

    run_next(Provider(), Reader())
    state = collection(auth, rid)
    assert fetched[0] == "https://cs.example.edu.tr/akademik-kadro"
    assert "https://ilan.example.com/akademik/1" not in fetched
    ad = next(s for s in state["sources"] if "ilan" in s["url"])
    assert ad["status"] == "SKIPPED" and ad["error"].startswith("Ön eleme") and ad["page_kind"] == "job_listing"
    staff = next(s for s in state["sources"] if "akademik-kadro" in s["url"])
    assert (staff["engine"], staff["rank"], staff["page_kind"]) == ("yahoo", 3, "people_list")
    assert staff["query"] and staff["priority"] > ad["priority"]
    assert state["job"]["status"] == "COMPLETED" and state["job"]["stats"]["triage_skipped"] >= 1


def test_people_elsewhere_are_listed_but_do_not_count_toward_the_target(auth):
    rid = start(auth, requested_quantity=1)
    pages = iter([
        ("https://uni-toronto.example.edu/faculty", staff_page("Toronto", [("Alice Smith", "AI"), ("Bob Jones", "AI")],
                                                               "Faculty | University of Toronto")),
        ("https://ornek.edu.tr/akademik-kadro", staff_page("İstanbul", [("Ayşe Kaya", "Yapay Zeka")])),
    ])

    class Provider:
        def discover(self, query, limit, page=1):
            url, _ = next(pages, (None, None))
            return [SearchHit(url, "Akademik Kadro", "")] if url else []

    bodies = {}

    class Reader:
        def fetch(self, url):
            return url, bodies[url]

    bodies.update({
        "https://uni-toronto.example.edu/faculty": staff_page("Toronto", [("Alice Smith", "AI"), ("Bob Jones", "AI")],
                                                              "Faculty | University of Toronto"),
        "https://ornek.edu.tr/akademik-kadro": staff_page("İstanbul", [("Ayşe Kaya", "Yapay Zeka")]),
    })
    run_next(Provider(), Reader())
    state = collection(auth, rid)
    people = {c["full_name"]: c for c in candidates(auth, rid)}
    # The Toronto list did not end the search; at most "requested" people from elsewhere are kept.
    assert "Ayşe Kaya" in people and state["job"]["status"] == "COMPLETED"
    elsewhere = [c for c in people.values() if c["match_details"]["place"]["decision"] == "mismatch"]
    assert len(elsewhere) == 1 and elsewhere[0]["city"] == "Toronto"
    assert people["Ayşe Kaya"]["relevance_score"] > elsewhere[0]["relevance_score"]
    assert state["job"]["stats"]["profiles_elsewhere"] == 1


def test_people_on_one_page_are_imported_best_match_first(auth):
    rid = start(auth, requested_quantity=2)

    class Provider:
        def discover(self, query, limit, page=1):
            return [SearchHit("https://ornek.edu.tr/akademik-kadro", "Akademik Kadro", "")]

    class Reader:
        def fetch(self, url):
            return url, staff_page("İstanbul", [("Can Demir", "Kimya"), ("Ece Aksoy", "Tarih"),
                                                ("Ayşe Kaya", "Yapay Zeka; Makine Öğrenmesi"),
                                                ("Deniz Acar", "Yapay Zeka")])

    run_next(Provider(), Reader())
    assert sorted(c["full_name"] for c in candidates(auth, rid)) == ["Ayşe Kaya", "Deniz Acar"]


def test_a_relevant_page_without_people_leads_to_its_own_team_page(auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "collection_max_followed_links", 5)
    rid = start(auth, requested_quantity=1, target_type="Kurucu", field="Yapay Zeka girişim")
    fetched = []

    class Provider:
        def discover(self, query, limit, page=1):
            return [SearchHit("https://startup.example.com/", "Yapay zeka girişimi", "")] if page == 1 else []

    class Reader:
        def fetch(self, url):
            fetched.append(url)
            if url.endswith("/ekibimiz"):
                return url, ("<title>Ekibimiz | Örnek AI</title><h1>Ekibimiz</h1><div class='team'>"
                             "<div class='m'><h3>Ayşe Kaya</h3><p>Kurucu ve CEO</p></div>"
                             "<div class='m'><h3>Can Demir</h3><p>Kurucu Ortak, CTO</p></div>"
                             "<div class='m'><h3>Ece Aksoy</h3><p>Yazılım Mühendisi</p></div></div>").encode()
            return url, ("<title>Örnek AI - yapay zeka girişimi</title><h1>Yapay zeka ile çözümler</h1>"
                         "<a href='/ekibimiz'>Ekibimiz</a><a href='/iletisim'>İletişim</a>").encode()

    run_next(Provider(), Reader())
    state = collection(auth, rid)
    assert "https://startup.example.com/ekibimiz" in fetched
    followed = next(s for s in state["sources"] if s["url"].endswith("/ekibimiz"))
    assert followed["query"] == "Bağlantı: https://startup.example.com/"
    assert state["job"]["stats"]["links_followed"] == 1
    assert [c["full_name"] for c in candidates(auth, rid)] == ["Ayşe Kaya"]


def test_candidate_page_shows_each_decision_and_its_basis(auth):
    rid = start(auth, requested_quantity=1)

    class Provider:
        def discover(self, query, limit, page=1):
            return [SearchHit("https://ornek.edu.tr/akademik-kadro", "Akademik Kadro", "")]

    class Reader:
        def fetch(self, url):
            return url, staff_page("İstanbul", [("Ayşe Kaya", "Yapay Zeka")])

    run_next(Provider(), Reader())
    person = candidates(auth, rid)[0]
    assert person["match_details"]["role"]["decision"] == "match"
    assert person["match_details"]["place"]["basis"] == "page"
    assert "(+" in person["relevance_reason"]
    page = auth.get(f"/panel/candidates/{person['id']}").text
    assert "sayfa adresinden çıkarıldı" in page and "Kişinin kaydında geçiyor" in page


def test_provider_asks_again_after_a_pause_when_every_engine_is_empty(monkeypatch):
    from app.services import discovery

    calls, pauses = [], []

    class Engine:
        def __init__(self, **kwargs):
            pass

        def text(self, query, backend, **kwargs):
            calls.append(backend)
            if len(calls) <= 2:
                raise DDGSException("No results found.")
            return [{"href": "https://example.edu.tr/kadro", "title": "Kadro", "body": ""}]

    monkeypatch.setattr(discovery, "DDGS", Engine)
    monkeypatch.setattr(get_settings(), "search_backends", "yahoo,duckduckgo")
    monkeypatch.setattr(get_settings(), "search_pause_seconds", 2.0)
    hits = PublicSearchProvider("tr", sleep=pauses.append).discover("yapay zeka kadro", 10)
    assert [h.url for h in hits] == ["https://example.edu.tr/kadro"] and hits[0].engine == "yahoo"
    assert calls == ["yahoo", "duckduckgo", "yahoo"] and pauses == [2.0]


def test_rescore_recomputes_scores_but_keeps_reviewer_decisions(auth):
    from app.core.db import SessionLocal
    from app.manage import rescore
    from app.models import Candidate

    rid = auth.post(BASE + "/research-requests", json=BRIEF).json()["id"]
    person = {"full_name": "Ayşe Kaya", "job_title": "Profesör", "expertise": ["Yapay Zeka"],
              "location": "İstanbul", "source_url": "https://ornek.edu.tr/ayse", "source_name": "Örnek"}
    cid = auth.post(f"{BASE}/research-requests/{rid}/candidates", json=person).json()["candidate"]["id"]
    auth.patch(f"{BASE}/candidates/{cid}", json={"status": "APPROVED", "notes": "Görüşüldü"})
    with SessionLocal() as db:
        candidate = db.get(Candidate, cid)
        expected = candidate.relevance_score
        candidate.relevance_score, candidate.match_details = 1, {}  # as saved by the previous version
        db.commit()
        assert rescore(db) == 1
    after = auth.get(f"{BASE}/candidates/{cid}").json()
    assert after["relevance_score"] == expected and after["match_details"]["role"]["decision"] == "match"
    assert (after["status"], after["notes"]) == ("APPROVED", "Görüşüldü")


def test_a_whole_faculty_list_does_not_fill_a_specific_topic_brief(auth):
    # A computer vision brief: a department list with no research areas names nobody in the
    # field. Its people are listed ("Konu doğrulanmadı"), the search goes on for evidence.
    rid = start(auth, requested_quantity=1, field="Computer Vision", target_type="Akademisyen")
    pages = {
        "https://a.edu.tr/akademik-kadro": staff_page("İstanbul", [("Can Demir", "Ağ Güvenliği"),
                                                                   ("Ece Aksoy", "Veri Tabanları")]),
        "https://b.edu.tr/akademik-kadro": staff_page("İstanbul", [("Ayşe Kaya", "Bilgisayarlı Görü")]),
    }
    urls = iter(pages)

    class Provider:
        def discover(self, query, limit, page=1):
            url = next(urls, None)
            return [SearchHit(url, "Akademik Kadro", "")] if url else []

    class Reader:
        def fetch(self, url):
            return url, pages[url]

    run_next(Provider(), Reader())
    state = collection(auth, rid)
    people = {c["full_name"]: c for c in candidates(auth, rid)}
    assert state["job"]["status"] == "COMPLETED" and "Ayşe Kaya" in people
    unconfirmed = [n for n, c in people.items() if c["match_details"]["topic"]["decision"] == "unknown"]
    assert len(unconfirmed) == 1 and state["job"]["stats"]["profiles_unconfirmed"] == 1


def test_a_broad_field_needs_no_topic_evidence():
    from test_search_plan import brief

    from app.services.matching import decide, topic_required
    from app.services.requirements import build_spec

    spec = build_spec(brief(field="Technology", target_type="CTO", keywords=[]))
    assert not topic_required(spec)
    assert decide({"full_name": "A B", "job_title": "CTO"}, spec)["topic"]["required"] is False


def test_menu_words_on_a_small_list_are_not_the_listed_peoples_topic(auth):
    rid = start(auth, requested_quantity=1, field="Computer Vision")
    page = ("<title>Misafir Öğretim Üyeleri - MEF</title><h1>Misafir Öğretim Üyeleri</h1>"
            "<p>Bölümler: Bilgisayarlı Görü Laboratuvarı, Yapay Zeka Merkezi</p><div class='g'>"
            "<div class='c'><h5>Prof. Dr. Can Demir</h5><p>Kimya</p></div>"
            "<div class='c'><h5>Prof. Dr. Ece Aksoy</h5><p>Tarih</p></div></div>"
            "<footer><address>Maslak, İstanbul</address></footer>").encode()

    class Provider:
        def discover(self, query, limit, page=1):
            return [SearchHit("https://mef.example.edu.tr/misafir", "Misafir Öğretim Üyeleri", "")] if page == 1 else []

    class Reader:
        def fetch(self, url):
            return url, page

    run_next(Provider(), Reader())
    people = candidates(auth, rid)
    assert people and all(c["match_details"]["topic"]["decision"] == "unknown" for c in people)
    assert collection(auth, rid)["job"]["status"] != "COMPLETED"


def test_the_country_of_the_site_applies_to_its_listed_people():
    from app.services.extraction import extract_profiles

    cards = "".join(f'<div class="c"><h3>د. {n}</h3><p>أستاذ</p></div>'
                    for n in ["محمد أحمد الشمري", "خالد سعد العتيبي", "عبدالله فهد القحطاني", "عمر سالم العطاس"])
    people = extract_profiles(f"<title>قسم الإحصاء</title><div class='g'>{cards}</div>",
                              "https://sciences.ksu.edu.sa/ar/node/14196")[1]
    assert len(people) == 4 and {p.country for p in people} == {"Suudi Arabistan"}
    assert {p.job_title for p in people} == {"أستاذ"}
