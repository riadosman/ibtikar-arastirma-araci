"""From a research brief to a research specification and a search plan.

The brief's free fields become explicit requirements:

- roles: requested roles (OR); a broad "expert/speaker" target means no role constraint,
- topics: field parts and keywords, each with names in the search languages and synonyms,
- place: the requested city/country, a ranking preference and never a filter (user decision),
- languages: the query language plus a second language for terminology variants.

The plan is a list of rounds of purposeful queries, most specific first. Every query targets
a page type the extractor reads well (staff, team, speaker and jury lists) or a source of
leads (profile platforms); generic suffixes ("kimdir", "biyografi") are not used because they
return definitions and celebrity pages.
"""

from dataclasses import dataclass, field
from html import unescape

from app.services.page_context import CITIES, place_matches
from app.services.search_quality import TRANSLATIONS, normalize, requested_roles
from app.services.topics import LANGUAGES, city_name, topic_term

ROUND_SIZE = 4
# (role query term, list-page terms) per language; list pages are where people are listed.
DIRECTORY = {
    "academic": {"tr": ("akademisyen", ("akademik kadro", "öğretim üyeleri")),
                 "en": ("professor", ("faculty members", "academic staff")),
                 "de": ("Professor", ("Professoren", "wissenschaftliche Mitarbeiter")),
                 "fr": ("professeur", ("enseignants-chercheurs", "corps professoral")),
                 "es": ("profesor", ("profesorado", "personal académico")),
                 "ar": ("أستاذ", ("أعضاء هيئة التدريس", "الكادر الأكاديمي"))},
    "founder": {"tr": ("kurucu", ("kurucu ekibimiz", "yönetim ekibi")),
                "en": ("founder", ("founders team", "leadership team")),
                "de": ("Gründer", ("Gründerteam", "Geschäftsführung")),
                "fr": ("fondateur", ("équipe fondatrice", "équipe dirigeante")),
                "es": ("fundador", ("equipo fundador", "equipo directivo")),
                "ar": ("مؤسس", ("فريق المؤسسين", "فريق الإدارة"))},
    "executive": {"tr": ("CTO", ("yönetim ekibi", "ekibimiz")),
                  "en": ("CTO", ("leadership team", "our team")),
                  "de": ("CTO", ("Geschäftsführung", "unser Team")),
                  "fr": ("CTO", ("équipe dirigeante", "notre équipe")),
                  "es": ("CTO", ("equipo directivo", "nuestro equipo")),
                  "ar": ("CTO", ("فريق الإدارة", "فريقنا"))},
    "chef": {"tr": ("şef", ("şefler", "jüri üyeleri")), "en": ("chef", ("chefs", "jury members")),
             "de": ("Koch", ("Köche", "Jury")), "fr": ("chef", ("chefs", "jury")),
             "es": ("chef", ("chefs", "jurado")), "ar": ("طاه", ("الطهاة", "لجنة التحكيم"))},
    "doctor": {"tr": ("doktor", ("hekimlerimiz", "doktorlarımız")), "en": ("doctor", ("our doctors", "physicians")),
               "de": ("Arzt", ("Ärzte", "unser Team")), "fr": ("médecin", ("nos médecins", "équipe médicale")),
               "es": ("médico", ("nuestros médicos", "equipo médico")), "ar": ("طبيب", ("أطباؤنا", "الفريق الطبي"))},
    "engineer": {"tr": ("mühendis", ("ekibimiz", "mühendislik ekibi")), "en": ("engineer", ("our team", "engineering team")),
                 "de": ("Ingenieur", ("unser Team", "Team")), "fr": ("ingénieur", ("notre équipe", "équipe")),
                 "es": ("ingeniero", ("nuestro equipo", "equipo")), "ar": ("مهندس", ("فريقنا", "فريق الهندسة"))},
    "expert": {"tr": ("uzman", ("konuşmacılar", "uzmanlar")), "en": ("expert", ("speakers", "experts")),
               "de": ("Experte", ("Referenten", "Experten")), "fr": ("expert", ("intervenants", "experts")),
               "es": ("experto", ("ponentes", "expertos")), "ar": ("خبير", ("المتحدثون", "الخبراء"))},
}
# Event pages list speakers and juries with biographies: (event word, people word).
EVENTS = {"tr": ("zirvesi", "konuşmacılar"), "en": ("summit", "speakers"), "de": ("Konferenz", "Referenten"),
          "fr": ("conférence", "intervenants"), "es": ("congreso", "ponentes"), "ar": ("مؤتمر", "المتحدثون")}
GENERIC_TARGETS = {"expert", "experts", "speaker", "speakers", "uzman", "uzmanlar", "konusmaci",
                   "konusmacilar", "kisi", "people", "person", "katilimci", "participant"}
ROLE_AUDIENCE = {"professor": "academic", "founder": "founder", "cto": "executive", "chef": "chef",
                 "doctor": "doctor", "engineer": "engineer"}


@dataclass
class ResearchSpec:
    language: str  # query language: tr, en, de, fr, es or ar
    second: str | None  # terminology variants are also searched in this language
    region_country: str | None
    roles: set = field(default_factory=set)  # empty: any role (experts, speakers)
    audience: str = "expert"
    topics: list = field(default_factory=list)  # TopicTerm, field parts first, then keywords
    keywords: list = field(default_factory=list)
    location: str = ""
    city: str | None = None
    country: str | None = None
    target: str = ""  # the brief's own target words when they name no known role ("Öğrenci")

    def place(self, language=None):
        return city_name(self.location, language or self.language) if self.location else ""

    def role_term(self, language=None):
        language = language or self.language
        if self.target:
            return self.target
        if self.roles and self.audience in ("founder", "executive") and len(self.roles) > 1:
            return " ".join(TRANSLATIONS[r][LANGUAGES.index(language)] for r in sorted(self.roles))
        return DIRECTORY[self.audience][language][0]

    def directories(self, language=None):
        return DIRECTORY[self.audience][language or self.language][1]


def clean(value):
    """Copied briefs carry HTML entities ("&#32;machine learning") and stray whitespace."""
    return " ".join(unescape(value or "").split())


def split_field(value):
    import re

    parts = re.split(r"\s+(?:and|ve|und|et|y|و)\s+|\s*[,/&+;]\s*", clean(value), flags=re.I)
    return [p for p in dict.fromkeys(p.strip() for p in parts) if p]


def audience_of(research, roles):
    if roles:
        # A brief may ask for several roles; the first in this order decides the list pages.
        for role in ("professor", "founder", "cto", "chef", "doctor", "engineer"):
            if role in roles:
                return ROLE_AUDIENCE[role]
    context = normalize(" ".join(clean(getattr(research, k, "")) for k in
                                 ("field", "target_type", "description", "notes")))
    if any(w in context for w in ("professor", "faculty", "academic", "akademisyen", "hoca", "ogretim uyesi")):
        return "academic"
    if any(w in context for w in ("gastronom", "chef", "asci", "sef ")):
        return "chef"
    return "expert"


def build_spec(research):
    language = getattr(research, "search_language", "auto") or "auto"
    location = clean(research.location)
    if not any(c.isalpha() for c in location):
        location = ""  # "—" or "-" means no place was given
    key = normalize(location)
    place = next(((c, k) for alias, (c, k) in CITIES.items() if normalize(alias) == key or normalize(c) == key),
                 (None, None))
    city, country = place
    if not country and place_matches("Türkiye", location):
        country = "Türkiye"
    if language == "auto":
        # A Turkish city is searched in Turkish first, with English terminology variants.
        language, second = ("tr", "en") if country == "Türkiye" else ("en", None)
    else:
        second = "en" if language not in ("en",) else ("tr" if country == "Türkiye" else None)
    roles = requested_roles(research)
    keywords = [clean(k.value) for k in research.keywords if clean(k.value)]
    topics = [topic_term(p) for p in split_field(research.field)]
    seen = {t.topic.key if t.topic else normalize(t.label) for t in topics}
    for keyword in keywords:
        term = topic_term(keyword)
        marker = term.topic.key if term.topic else normalize(term.label)
        if marker not in seen:
            topics.append(term)
            seen.add(marker)
    audience = audience_of(research, roles)
    target = clean(research.target_type)
    words = set(normalize(target).replace(",", " ").split())
    own_target = target if not roles and not words & GENERIC_TARGETS else ""
    return ResearchSpec(language=language, second=second, region_country=country, roles=roles,
                        audience=audience, topics=topics, keywords=keywords, location=location,
                        city=city, country=country, target=own_target[:60])


def query(*parts):
    return " ".join(" ".join(p for p in parts if p).split())


def plan(spec):
    """Rounds of queries, most specific first; a query never repeats in a later round."""
    lang, place = spec.language, spec.place()
    topics = spec.topics or [topic_term("")]
    main = topics[0]
    role = spec.role_term()
    lists = spec.directories()
    event, people = EVENTS[lang]
    keyword_topics = [t for t in topics[1:] if t.label in spec.keywords]
    field_topics = [t for t in topics if t not in keyword_topics]

    first = [query(main.query(lang), place, lists[0]), query(main.query(lang), place, role)]
    if keyword_topics:
        first.append(query(keyword_topics[0].query(lang), place, role))
    if spec.audience == "expert":
        first.append(query(main.query(lang), event, place, people))
    first.append(query(main.query(lang), place, lists[1]))

    platforms = []
    for topic in (keyword_topics[:1] + field_topics)[:2]:
        platforms.append(query("linkedin", topic.query(lang), role, place))
        if spec.audience == "academic":
            platforms.append(query("researchgate", topic.query(lang), place))

    variants = []
    for topic in topics[:3]:
        other = topic.other(lang)
        if spec.second and other:
            second_lists = DIRECTORY[spec.audience][spec.second][1]
            variants.append(query(other, spec.place(spec.second), second_lists[0]))
        for related in sorted(topic.topic.related if topic.topic else ())[:1]:
            variants.append(query(related, place, lists[0]))

    parts = [query(t.query(lang), place, role) for t in topics[1:]]
    parts += [query(t.query(lang), place, lists[0]) for t in topics[1:]]
    if spec.audience == "academic" and lang == "tr":
        parts += [query("site:edu.tr", t.query(lang), lists[1]) for t in field_topics[:2]]

    events = [query(t.query(lang), event, place, people) for t in topics[:2]]
    if spec.second:
        second_event, second_people = EVENTS[spec.second]
        events.append(query(main.other(lang) or main.query(spec.second), second_event, spec.place(spec.second),
                            second_people))

    # Wider area: drop the city; the language's search region keeps results local.
    wider = [query(t.query(lang), lists[0]) for t in topics[:2]] + [query(t.query(lang), role) for t in topics[:2]]
    if lang == "en" and not spec.region_country:
        wider = []

    rounds, seen = [], set()
    for queries in (first, platforms, variants, parts, events, wider):
        fresh = [q for q in dict.fromkeys(queries) if q and q not in seen][:ROUND_SIZE]
        seen.update(fresh)
        if fresh:
            rounds.append(fresh)
    return rounds


def region(spec, default):
    """Search region: from the requested place when the brief's language is automatic."""
    return {"Türkiye": "tr-tr", "BAE": "xa-ar", "Suudi Arabistan": "xa-ar", "Katar": "xa-ar",
            "Mısır": "xa-ar", "Almanya": "de-de", "Fransa": "fr-fr", "İspanya": "es-es",
            "Birleşik Krallık": "uk-en", "ABD": "us-en", "Kanada": "ca-en"}.get(spec.region_country, default)
