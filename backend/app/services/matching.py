"""How well a person fits a brief: one decision per requirement, each with its basis.

"Unknown" is not "does not match" (audit FL3): a staff list may give no title, and a page may
never repeat the city next to a name. Decisions:

- role: match (stated), inferred (the page is e.g. an academic staff list), any (no role was
  requested), unknown, mismatch (a different role is stated),
- topic: match (in the person's own text), page (only the page or unit names it), unknown,
- place: match / country (same country, city not stated) / mismatch / unknown / any, with the
  basis "profile" (stated for the person) or "page" (the page owner's address, inferred),
- keywords: which of the brief's keywords appear.

The relevance score is the sum of the points of these decisions plus evidence points, so the
reason shown to a reviewer is the same evidence that ranked the person. A score is a review
hint, never an approval.
"""

import re

from app.services.page_context import place_matches
from app.services.search_quality import contains, normalize, roles_in
from app.services.topics import BROAD

# Page words that make the listed people's role clear even when a record states none.
PAGE_ROLES = {
    "professor": re.compile(r"(?<!\w)(?:faculty|academic staff|academic personnel|akademik kadro|akademik personel|"
                            r"öğretim üyeleri|ogretim uyeleri|öğretim elemanları|professors|professoren|"
                            r"هيئة التدريس)(?!\w)", re.I),
    "founder": re.compile(r"(?<!\w)(?:founders|kurucular|kurucularımız|kurucu üyeler\w*|kurucu ekip\w*)(?!\w)", re.I),
    "chef": re.compile(r"(?<!\w)(?:şefler|şeflerimiz|chefs|jüri|jury)(?!\w)", re.I),
    "doctor": re.compile(r"(?<!\w)(?:hekimlerimiz|doktorlarımız|our doctors|physicians)(?!\w)", re.I),
}
ROLE_POINTS = {"match": 25, "inferred": 15, "any": 25, "unknown": 0, "mismatch": 0}
PLACE_POINTS = {"match": 20, "country": 8, "unknown": 0, "mismatch": -20, "any": 20}
TOPIC_POINTS, PAGE_TOPIC_POINTS, KEYWORD_POINTS = 30, 12, 10
LABELS = {
    "role": {"match": "rol uyuyor", "inferred": "rol sayfadan çıkarıldı", "any": "rol şartı yok",
             "unknown": "rol belirtilmemiş", "mismatch": "rol farklı"},
    "topic": {"match": "konu kişinin kaydında geçiyor", "page": "konu yalnızca sayfada/birim adında geçiyor",
              "unknown": "konu doğrulanmadı"},
    "place": {"match": "konum uyuyor", "country": "aynı ülke, şehir belirtilmemiş", "mismatch": "konum farklı",
              "unknown": "konum bilinmiyor", "any": ""},
}


def _get(person, key):
    value = person.get(key) if isinstance(person, dict) else getattr(person, key, None)
    return value or ""


def person_text(person):
    return " ".join(filter(None, [_get(person, "job_title"), _get(person, "headline"), _get(person, "organization"),
                                  _get(person, "field"), str(_get(person, "bio"))[:3000],
                                  " ".join(_get(person, "expertise") or [])]))


def role_decision(person, spec, page_text):
    if not spec.roles:
        return "any", ""
    stated = " ".join(filter(None, [_get(person, "job_title"), _get(person, "headline")]))
    found = roles_in(stated) or roles_in(str(_get(person, "bio"))[:1500])
    if spec.roles & found:
        return "match", stated[:200] or "biyografide"
    for role in sorted(spec.roles):
        pattern = PAGE_ROLES.get(role)
        hit = pattern.search(page_text) if pattern else None
        if hit:
            return "inferred", hit.group(0)
    if roles_in(stated):
        return "mismatch", stated[:200]
    return "unknown", ""


def topic_decision(person, spec, page_text, own_text=""):
    own = f"{person_text(person)} {own_text}"

    def found_in(text):
        return [t.label for t in spec.topics if any(contains(text, term) for term in t.match_terms if len(term) > 1)]

    matched = found_in(own)
    if matched:
        return "match", matched
    on_page = found_in(page_text) if page_text else []
    return ("page", on_page) if on_page else ("unknown", [])


def place_decision(person, spec):
    if not spec.location:
        return "any", "", ""
    stated = _get(person, "location")
    if stated:
        return ("match" if place_matches(spec.location, stated) else "mismatch"), "profile", stated
    city, country = _get(person, "city"), _get(person, "country")
    if not (city or country):
        return "unknown", "", ""
    value = ", ".join(filter(None, [city, country]))
    if place_matches(spec.location, city, country):
        return ("match" if city or not spec.city else "country"), "page", value
    if not city and spec.country and normalize(spec.country) == normalize(country):
        return "country", "page", value
    return "mismatch", "page", value


def topic_required(spec):
    """Topic evidence is needed for a specific topic, unless the role names the field (chefs)."""
    specific = [t for t in spec.topics if not (t.topic and t.topic.key in BROAD)]
    return bool(specific) and spec.audience not in ("chef", "doctor")


def decide(person, spec, page_text="", own_text=""):
    """All decisions, their points (summing to the relevance score) and reasons.

    `page_text` names the page (title, headings); `own_text` is about this person only (the
    person's evidence quote, or the body of a single-person profile page)."""
    role, role_evidence = role_decision(person, spec, page_text)
    topic, topics = topic_decision(person, spec, page_text, own_text)
    place, basis, place_value = place_decision(person, spec)
    text = f"{person_text(person)} {own_text} {page_text}"
    keywords = [k for k in spec.keywords if contains(text, k)]
    points = {"role": ROLE_POINTS[role], "place": PLACE_POINTS[place]}
    if place == "match" and basis == "page":
        points["place"] -= 5  # the page owner's address, not stated for the person
    if topic == "match":
        points["topic"] = max(TOPIC_POINTS // 2, round(TOPIC_POINTS * len(topics) / max(1, len(spec.topics))))
    else:
        points["topic"] = PAGE_TOPIC_POINTS if topic == "page" else 0
    points["keywords"] = round(KEYWORD_POINTS * len(keywords) / len(spec.keywords)) if spec.keywords else 0
    return {
        "role": {"decision": role, "evidence": role_evidence},
        "topic": {"decision": topic, "terms": topics, "required": topic_required(spec)},
        "place": {"decision": place, "basis": basis, "value": place_value},
        "keywords": keywords,
        "points": points,
        "score": max(0, min(100, sum(points.values()))),
    }


def qualifies(details):
    """Imported at all: the stated or inferred role fits (or no role was asked for)."""
    return details["role"]["decision"] in ("match", "inferred", "any")


def shortfall(details):
    """Why a fitting person does not count toward the requested number: "place", "topic" or None.

    Another place (by the person's own or the page's address), or no topic evidence at all
    (a whole faculty list for a computer vision brief). Such people are still listed."""
    if details["place"]["decision"] == "mismatch":
        return "place"
    topic = details["topic"]
    if topic.get("required") and topic["decision"] == "unknown":
        return "topic"
    if topic.get("required") and topic["decision"] == "page" and details["role"]["decision"] == "any":
        return "topic"
    return None


def counts_for_target(details):
    return qualifies(details) and shortfall(details) is None


def reasons(details):
    points = details["points"]

    def signed(value):
        return f" ({value:+d})" if value else ""

    parts = [LABELS["role"][details["role"]["decision"]] + signed(points["role"])]
    topic = details["topic"]
    terms = f": {', '.join(topic['terms'])}" if topic["terms"] else ""
    parts.append(LABELS["topic"][topic["decision"]] + terms + signed(points["topic"]))
    place = details["place"]
    if LABELS["place"][place["decision"]]:
        value = f" ({place['value']}{', sayfadan' if place['basis'] == 'page' else ''})" if place["value"] else ""
        parts.append(LABELS["place"][place["decision"]] + value + signed(points["place"]))
    if details["keywords"]:
        parts.append("anahtar kelimeler: " + ", ".join(details["keywords"]) + signed(points["keywords"]))
    return "; ".join(parts)
