"""Requirements, search plan, triage and per-requirement matching."""

from types import SimpleNamespace as N

from bs4 import BeautifulSoup

from app.services.extraction import extract_profiles, person_name
from app.services.matching import counts_for_target, decide, qualifies
from app.services.mentions import mentioned_people
from app.services.requirements import build_spec, plan, region
from app.services.triage import classify, follow_links, triage


def brief(**overrides):
    values = dict(title="t", field="Artificial Intelligence", location="İstanbul", target_type="Akademisyen",
                  description="", notes="", requested_quantity=5, search_language="tr")
    values.update(overrides)
    keywords = values.pop("keywords", ["Computer Vision"])
    return N(**values, keywords=[N(value=k) for k in keywords])


def test_spec_keeps_roles_topics_synonyms_and_place():
    spec = build_spec(brief())
    assert spec.roles == {"professor"} and spec.audience == "academic"
    assert [t.label for t in spec.topics] == ["Artificial Intelligence", "Computer Vision"]
    assert "goruntu isleme" in spec.topics[1].match_terms  # normalized synonyms
    assert (spec.city, spec.country) == ("İstanbul", "Türkiye")


def test_automatic_language_for_a_turkish_city_searches_turkish_in_the_turkish_region():
    spec = build_spec(brief(search_language="auto"))
    assert (spec.language, spec.second) == ("tr", "en")
    assert region(spec, "us-en") == "tr-tr"
    assert plan(spec)[0][0] == "yapay zekâ İstanbul akademik kadro"


def test_a_place_without_letters_is_no_place():
    assert build_spec(brief(location="—")).location == ""


def test_speaker_briefs_search_event_speaker_pages():
    flat = [q for r in plan(build_spec(brief(target_type="Speaker"))) for q in r]
    assert "yapay zekâ zirvesi İstanbul konuşmacılar" in flat


def test_triage_skips_job_ads_definitions_and_documents_and_ranks_people_lists_first():
    spec = build_spec(brief())
    assert triage("https://akademiktr.com/ilan/ankara", "Dr. Öğretim Üyesi İlanları 2026", "", spec).skip
    assert triage("https://blog.example.com/cto-nedir", "CTO nedir? Ne iş yapar?", "", spec).skip
    assert triage("https://x.edu.tr/kadro.pdf", "Kadro", "", spec).skip
    staff = triage("https://cs.example.edu.tr/akademik-kadro", "Akademik Kadro - Yapay Zeka", "", spec)
    news = triage("https://www.haber.com/teknoloji/x", "Teknoloji haberleri", "", spec)
    assert staff.kind == "people_list" and not staff.skip
    assert staff.priority > news.priority
    assert classify("https://example.com/dashboard", "Dashboard") == "page"


def test_followed_links_stay_on_the_site_and_lead_to_people_lists():
    soup = BeautifulSoup("""<a href="/ekibimiz">Ekibimiz</a><a href="https://other.com/team">Team</a>
    <a href="/kariyer">Kariyer</a><a href="/hakkinda">Hakkında</a><a href="/akademik-kadro">Kadro</a>""",
                         "html.parser")
    assert follow_links(soup, "https://lab.example.org/") == [
        "https://lab.example.org/ekibimiz", "https://lab.example.org/akademik-kadro"]


def test_matching_separates_unknown_from_mismatch_and_states_the_basis():
    spec = build_spec(brief())
    stated = decide({"full_name": "A B", "job_title": "Professor", "expertise": ["computer vision"],
                     "city": "İstanbul", "country": "Türkiye"}, spec, "Faculty")
    assert stated["role"]["decision"] == "match" and stated["topic"]["decision"] == "match"
    assert stated["place"] == {"decision": "match", "basis": "page", "value": "İstanbul, Türkiye"}
    inferred = decide({"full_name": "A B"}, spec, "Akademik Kadro - Yapay Zeka Bölümü")
    assert inferred["role"]["decision"] == "inferred" and inferred["topic"]["decision"] == "page"
    elsewhere = decide({"full_name": "A B", "job_title": "Professor", "city": "Toronto", "country": "Kanada"},
                       spec)
    assert qualifies(elsewhere) and not counts_for_target(elsewhere)
    assert elsewhere["score"] < inferred["score"] + 25
    other_role = decide({"full_name": "A B", "job_title": "Software Engineer"}, spec)
    assert other_role["role"]["decision"] == "mismatch" and not qualifies(other_role)


def test_people_named_in_running_text_need_a_title_or_role_anchor():
    text = ("MasterChef jüri üyeleri Somer Sivrioğlu, Mehmet Yalçınkaya ve Danilo Zanna yer aldı.\n"
            "Jüri Başkanı Dr. Öğr. Üyesi Emrah Köksal Sezgin’in yürüttüğü yarışma.\n"
            "İstanbul Teknik Üniversitesi açıklama yaptı. Ankara Büyükşehir Belediyesi de katıldı.")
    found = {name: role for name, role, _ in mentioned_people(text, person_name)}
    assert found == {"Emrah Köksal Sezgin": "Dr. Öğr. Üyesi", "Somer Sivrioğlu": "jüri üyeleri",
                     "Mehmet Yalçınkaya": "jüri üyeleri", "Danilo Zanna": "jüri üyeleri"}


def test_article_mentions_are_kept_with_their_sentence_as_evidence():
    html = ("<title>Gastronomi yarışması</title><article><p>Yarışmada jüri başkanlığını şef Mehmet "
            "Yalçınkaya yaptı.</p></article>")
    people = extract_profiles(html, "https://news.example.com/yarisma")[1]
    assert [(p.full_name, p.source_type) for p in people] == [("Mehmet Yalçınkaya", "text_mention")]
    assert "jüri başkanlığını" in people[0].source_evidence
