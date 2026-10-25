"""Collection widens the search in rounds, then reads further result pages, until the target
is reached, the user stops it, no new source is left or the safety ceiling passes."""

from types import SimpleNamespace

import pytest
from ddgs.exceptions import DDGSException
from sqlalchemy import select
from test_collection import PROFILE
from test_workflow import BASE, BRIEF

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import CollectionJob, ResearchRequest
from app.services.collection import run_next
from app.services.discovery import (
    PublicSearchProvider,
    SearchHit,
    query_rounds,
)

HACKATHON = {
    "title": "Hackathon mentorları",
    "field": "AI and Math",
    "location": "istanbul",
    "target_type": "Akademisyen, isinde uzman",
    "description": "Öğrenci kulübü hackathonunda projelere mentorluk edecek hocalar",
    "requested_quantity": 1,
    "keywords": ["Math", "Theore"],
    "search_language": "tr",
}
EMPTY = b"<html><title>Portal</title><h1>Haberler</h1><p>Genel duyurular.</p></html>"


def person(name):
    return PROFILE.replace(b"Ada Lovelace", name.encode())


def brief(**overrides):
    values = {**HACKATHON, **overrides}
    keywords = [SimpleNamespace(value=k) for k in values.pop("keywords")]
    return SimpleNamespace(**values, notes="", keywords=keywords)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def start(auth, **overrides):
    response = auth.post(BASE + "/research-requests", json={**HACKATHON, **overrides})
    assert response.status_code == 201, response.text
    rid = response.json()["id"]
    assert auth.post(f"{BASE}/research-requests/{rid}/collect").status_code == 202
    return rid


def rounds_for(rid):
    with SessionLocal() as db:
        return query_rounds(db.get(ResearchRequest, rid))


def state(auth, rid):
    return auth.get(f"{BASE}/research-requests/{rid}/collection").json()


def test_first_round_targets_list_pages_and_the_keyword_and_rounds_never_repeat():
    # Staff lists are where the extractor finds people; the brief's keyword is searched in
    # round 1 (it used to wait for round 5, which a stalled search never reached).
    research = brief()
    rounds = query_rounds(research)
    assert "yapay zekâ İstanbul akademik kadro" in rounds[0]
    assert "matematik İstanbul akademisyen" in rounds[0]
    assert all(q.startswith(("linkedin ", "researchgate ")) for q in rounds[1])
    flat = [q for queries in rounds for q in queries]
    assert len(flat) == len(set(flat))
    assert len(rounds) > 2 and all(1 <= len(queries) <= 4 for queries in rounds)
    # Definition and biography suffixes brought "CTO nedir?" pages and celebrities.
    assert not any(word in q for q in flat for word in ("kimdir", "biyografi", "biography"))


def test_compound_field_is_split_and_translated_for_the_search_language():
    flat = [q for queries in query_rounds(brief()) for q in queries]
    assert "yapay zekâ İstanbul akademisyen" in flat
    assert "matematik İstanbul akademisyen" in flat
    assert not any("AI and Math" in q for q in flat)


def test_later_rounds_target_directories_keywords_synonyms_and_a_wider_area():
    rounds = query_rounds(brief())
    flat = [q for queries in rounds[2:] for q in queries]
    assert any("öğretim üyeleri" in q for q in flat)
    assert any(q.startswith("site:edu.tr ") for q in flat)
    assert any(q.startswith("Theore İstanbul") for q in flat)
    # Terminology variants: the topic's English name with English list-page words.
    assert "artificial intelligence Istanbul faculty members" in flat
    # The last round drops the city; the Turkish search region keeps results local.
    assert "matematik akademisyen" in rounds[-1]


def test_english_brief_uses_english_terms_first_without_turkish_site_filter():
    rounds = query_rounds(brief(search_language="en"))
    flat = [q for queries in rounds for q in queries]
    assert any("faculty members" in q for q in flat)
    assert any("mathematics" in q for q in flat)
    assert not any("site:edu.tr" in q for q in flat)
    assert not any("öğretim" in q or "akademik" in q for q in rounds[0])


def test_arabic_brief_translates_field_and_city_instead_of_mixing_scripts():
    rounds = query_rounds(brief(search_language="ar", field="Data science", target_type="Professor",
                                keywords=[], description=""))
    assert rounds[0][0] == "علم البيانات إسطنبول أعضاء هيئة التدريس"
    assert not any("السيرة الذاتية" in q for queries in rounds for q in queries)


def test_search_keeps_widening_until_a_person_is_found(auth):
    rid = start(auth)
    rounds = rounds_for(rid)
    late = set(rounds[3])
    queries = []

    class Provider:
        def discover(self, query, limit, page=1):
            queries.append(query)
            slug = abs(hash(query))
            return [SearchHit(f"https://example.edu.tr/{'people' if query in late else 'news'}/{slug}",
                              "Sayfa", "")]

    class Reader:
        def fetch(self, url):
            return url, person("Emmy Noether") if "/people/" in url else EMPTY

    run_next(Provider(), Reader())
    job = state(auth, rid)["job"]
    assert job["status"] == "COMPLETED"
    assert job["stats"]["search_rounds"] == 4
    assert [c["full_name"] for c in auth.get(f"{BASE}/research-requests/{rid}/candidates").json()["items"]] == ["Emmy Noether"]
    # Once the target is reached no further round is searched.
    assert not set(queries) & set(rounds[4])


def test_search_keeps_reading_when_no_new_person_appears_for_minutes(auth):
    # It used to give up after 60 s without a new person, usually in round 4 of 7.
    clock = FakeClock()
    fetched = []

    class Provider:
        def discover(self, query, limit, page=1):
            return [SearchHit(f"https://example.org/{abs(hash(query))}/{i}", "Sayfa", "") for i in range(5)]

    class SlowReader:
        def fetch(self, url):
            fetched.append(url)
            clock.now += 10
            return url, EMPTY

    rid = start(auth)
    run_next(Provider(), SlowReader(), clock=clock)
    result = state(auth, rid)
    queries = [q for queries in rounds_for(rid) for q in queries]
    assert len(fetched) == 5 * len(queries)
    assert result["job"]["status"] == "NO_RESULTS"
    assert "Aranacak yeni kaynak kalmadı" in result["job"]["error"]
    assert not [s for s in result["sources"] if s["status"] == "SKIPPED"]


def test_after_the_last_round_the_next_result_page_is_searched(auth):
    rid = start(auth)
    queries = [q for queries in rounds_for(rid) for q in queries]
    calls = []

    class Provider:
        def discover(self, query, limit, page=1):
            calls.append((query, page))
            kind = "people" if (query, page) == (queries[0], 2) else "news"
            return [SearchHit(f"https://example.edu.tr/{kind}/{abs(hash(query))}/{page}", "Sayfa", "")]

    class Reader:
        def fetch(self, url):
            return url, person("Emmy Noether") if "/people/" in url else EMPTY

    run_next(Provider(), Reader())
    assert state(auth, rid)["job"]["status"] == "COMPLETED"
    assert calls[:len(queries)] == [(q, 1) for q in queries]
    # Round 1 is searched again on page 2; its sources are read once the round is searched.
    assert calls[len(queries):] == [(q, 2) for q in rounds_for(rid)[0]]
    assert [c["full_name"] for c in auth.get(f"{BASE}/research-requests/{rid}/candidates").json()["items"]] == ["Emmy Noether"]


def test_a_query_goes_deeper_only_while_its_pages_bring_new_sources(auth):
    rid = start(auth, requested_quantity=5)
    first = rounds_for(rid)[0][0]
    calls = []

    class Provider:
        def discover(self, query, limit, page=1):
            calls.append((query, page))
            # Only the first query keeps returning new addresses on every page.
            return [SearchHit(f"https://example.org/{abs(hash(query))}/{page if query == first else 1}",
                              "Sayfa", "")]

    class Reader:
        def fetch(self, url):
            return url, EMPTY

    run_next(Provider(), Reader())
    pages = {}
    for query, page in calls:
        pages.setdefault(query, []).append(page)
    assert pages.pop(first) == [1, 2, 3, 4, 5]
    assert pages and all(searched == [1, 2] for searched in pages.values())
    assert "Aranacak yeni kaynak kalmadı" in state(auth, rid)["job"]["error"]


def test_search_stops_at_the_sixty_minute_safety_ceiling(auth):
    clock = FakeClock()
    fetched = []

    class Provider:
        def discover(self, query, limit, page=1):
            return [SearchHit(f"https://example.org/{abs(hash(query))}/{page}/{i}", "Sayfa", "")
                    for i in range(5)]

    class SlowReader:
        def fetch(self, url):
            fetched.append(url)
            clock.now += 400
            return url, EMPTY

    rid = start(auth)
    run_next(Provider(), SlowReader(), clock=clock)
    result = state(auth, rid)
    assert len(fetched) == 9  # 9 x 400 s reaches the 3600 s ceiling.
    assert result["job"]["status"] == "NO_RESULTS"
    assert "süre sınırı" in result["job"]["error"]
    skipped = [s for s in result["sources"] if s["status"] == "SKIPPED"]
    assert skipped and all("süre sınırı" in s["error"] for s in skipped)


def test_search_stops_when_the_source_limit_is_full(auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "collection_max_sources", 3)
    rid = start(auth)
    calls = []

    class Provider:
        def discover(self, query, limit, page=1):
            calls.append(query)
            return [SearchHit(f"https://example.org/{abs(hash(query))}/{page}/{i}", "Sayfa", "")
                    for i in range(5)]

    class Reader:
        def fetch(self, url):
            return url, EMPTY

    run_next(Provider(), Reader())
    job = state(auth, rid)["job"]
    assert job["discovered"] == 3
    assert "kaynak sınırı" in job["error"]
    # Nothing is searched once there is no room for another source.
    assert calls == rounds_for(rid)[0]


def test_deeper_result_pages_are_searched_with_a_pause(auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "search_pause_seconds", 2.0)
    start(auth)
    pages, pauses = [], []

    class Provider:
        def discover(self, query, limit, page=1):
            pages.append(page)
            return [SearchHit(f"https://example.org/{abs(hash(query))}", "Sayfa", "")] if page == 1 else []

    class Reader:
        def fetch(self, url):
            return url, EMPTY

    run_next(Provider(), Reader(), sleep=pauses.append)
    assert pages.count(2) > 0
    assert pauses == [2.0] * pages.count(2)


def test_job_resumes_from_the_round_it_had_finished(auth):
    rid = start(auth)
    rounds = rounds_for(rid)
    with SessionLocal() as db:
        job = db.scalar(select(CollectionJob).where(CollectionJob.research_request_id == rid))
        job.stats = {"stage": "round:3", "search_rounds": 3}
        db.commit()
    queries = []

    class Provider:
        def discover(self, query, limit, page=1):
            queries.append((query, page))
            return []

    run_next(Provider(), None)
    assert queries and queries[0] == (rounds[3][0], 1)
    # Finished rounds are not searched again on page 1 (they may still get a page 2).
    assert not {q for q, page in queries if page == 1} & {q for r in rounds[:3] for q in r}


def test_job_saved_by_previous_version_resumes_after_fallback(auth):
    rid = start(auth)
    rounds = rounds_for(rid)
    with SessionLocal() as db:
        job = db.scalar(select(CollectionJob).where(CollectionJob.research_request_id == rid))
        job.stats = {"stage": "fallback"}
        db.commit()
    queries = []

    class Provider:
        def discover(self, query, limit, page=1):
            queries.append(query)
            return []

    run_next(Provider(), None)
    assert queries[0] == rounds[2][0]


def test_job_resumes_on_the_result_page_it_had_reached(auth):
    rid = start(auth)
    rounds = rounds_for(rid)
    spent = rounds[1][0]
    with SessionLocal() as db:
        job = db.scalar(select(CollectionJob).where(CollectionJob.research_request_id == rid))
        # Page 1 and round 1 of page 2 were done; one query had run out of new pages.
        job.stats = {"stage": f"round:{len(rounds) + 1}", "search_rounds": 1, "search_pages": 2,
                     "spent_queries": [spent]}
        db.commit()
    calls = []

    class Provider:
        def discover(self, query, limit, page=1):
            calls.append((query, page))
            return []

    run_next(Provider(), None)
    assert calls[0] == (rounds[1][1], 2)
    assert (spent, 2) not in calls
    assert all(page > 1 for _, page in calls)
    # Every page-2 query searched now came back empty; round 1 had still been finding sources.
    assert [query for query, page in calls if page == 3] == rounds[0]


def test_progress_reports_current_round_and_result_page(auth):
    rid = start(auth)
    seen = []

    class Provider:
        def discover(self, query, limit, page=1):
            return [SearchHit(f"https://example.org/{abs(hash(query))}/{page}", "Sayfa", "")] if page <= 2 else []

    class Reader:
        def fetch(self, url):
            progress = auth.get(f"{BASE}/research-requests/{rid}/collection?summary=true").json()["progress"]
            seen.append((progress["round"], progress["rounds"], progress["page"]))
            return url, EMPTY

    run_next(Provider(), Reader())
    total = len(rounds_for(rid))
    assert seen[0] == (1, total, 1)
    assert (total, total, 1) in seen
    assert seen[-1] == (total, total, 2)


def test_no_results_from_search_engine_is_empty_not_an_error(monkeypatch):
    from app.services import discovery

    class Engine:
        message = "No results found."

        def __init__(self, **kwargs):
            pass

        def text(self, query, **kwargs):
            raise DDGSException(Engine.message)

    monkeypatch.setattr(discovery, "DDGS", Engine)
    assert PublicSearchProvider("tr").discover("matematik istanbul akademisyen", 10) == []
    Engine.message = "https://bing.com/ return None. ConnectTimeout"
    with pytest.raises(DDGSException):
        PublicSearchProvider("tr").discover("matematik istanbul akademisyen", 10)


def engine_answering_on(working, calls, failure="No results found."):
    class Engine:
        def __init__(self, **kwargs):
            pass

        def text(self, query, backend, **kwargs):
            calls.append(backend)
            if backend == working:
                return [{"href": "https://math.example.edu.tr/tr/faculty", "title": "Öğretim üyeleri", "body": ""}]
            raise DDGSException(failure)

    return Engine


def test_provider_tries_engines_one_at_a_time_and_keeps_the_working_one_first(monkeypatch):
    from app.services import discovery

    calls = []
    monkeypatch.setattr(discovery, "DDGS", engine_answering_on("yahoo", calls))
    monkeypatch.setattr(get_settings(), "search_backends", "duckduckgo,yahoo,brave")
    provider = PublicSearchProvider("tr")
    hits = provider.discover("matematik istanbul öğretim üyeleri", 10)
    assert [h.url for h in hits] == ["https://math.example.edu.tr/tr/faculty"]
    assert calls == ["duckduckgo", "yahoo"]
    provider.discover("site:edu.tr matematik öğretim üyeleri", 10)
    assert calls[2:] == ["yahoo"]


def test_provider_reports_a_real_engine_failure_when_no_engine_answers(monkeypatch):
    from app.services import discovery

    monkeypatch.setattr(discovery, "DDGS", engine_answering_on(None, [], failure="ConnectTimeout"))
    monkeypatch.setattr(get_settings(), "search_backends", "duckduckgo,yahoo")
    with pytest.raises(DDGSException):
        PublicSearchProvider("tr").discover("matematik istanbul", 10)


def test_provider_asks_the_engine_for_the_requested_result_page(monkeypatch):
    from app.services import discovery

    pages = []

    class Engine:
        def __init__(self, **kwargs):
            pass

        def text(self, query, page=1, **kwargs):
            pages.append(page)
            return [{"href": "https://math.example.edu.tr/tr/faculty", "title": "Öğretim üyeleri", "body": ""}]

    monkeypatch.setattr(discovery, "DDGS", Engine)
    PublicSearchProvider("tr").discover("matematik istanbul öğretim üyeleri", 10, page=3)
    assert pages == [3]


def test_defaults_search_until_the_target_with_a_sixty_minute_ceiling():
    # "bing" is no longer a DDGS engine; yahoo answered when the others returned empty pages.
    assert get_settings().search_backends == "yahoo,duckduckgo,brave,google,mojeek,startpage"
    settings = get_settings()
    assert not hasattr(settings, "collection_stall_seconds")
    assert settings.collection_time_budget_seconds == 3600
    assert settings.collection_max_sources == 500


def test_auto_language_brief_has_several_unique_rounds():
    research = SimpleNamespace(**{**BRIEF, "keywords": [SimpleNamespace(value="Computer Vision")]},
                               description="", notes="", search_language="auto")
    rounds = query_rounds(research)
    flat = [q for queries in rounds for q in queries]
    assert len(rounds) > 2 and len(flat) == len(set(flat))
