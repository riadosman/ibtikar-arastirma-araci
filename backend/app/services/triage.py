"""Triage of search results before any page is fetched.

The audit found that sources were read in search order: people-list URLs yielded people in 14%
of cases, "other" pages in 3%, and job ads, definitions ("CTO nedir?") and closed platforms
never. Each result is classified from its URL, title and snippet into a page kind, scored for
the brief (topic, place, role words) and either queued by priority or skipped with a reason.
Skipping never hides anything: the source stays listed with its reason.
"""

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from app.services.page_context import place_matches
from app.services.platforms import never_fetch
from app.services.search_quality import contains, job_listing, normalize

PROFILE_PATH = re.compile(r"/(?:people|person|staff|faculty|team|uye|kisi|akademisyen|personel|profile|profil|"
                          r"speakers?|konusmaci|ogretim-uyesi)/[^/]{3,}/?$", re.I)
DEFINITION = re.compile(r"(?<!\w)(?:nedir|ne demek|ne iş yapar|ne is yapar|kimdir\?|what is|what does|"
                        r"meaning of|definition|nasıl olunur|nasil olunur|maaşları|maaslari|salary|salaries)(?!\w)",
                        re.I)
JOBS = re.compile(r"(?<!\w)(?:iş ilanı|is ilani|ilanları|ilanlari|alım ilanı|alim ilani|kariyer fırsatları|"
                  r"job opening|jobs? in|vacanc|hiring|we are hiring|apply now|başvuru formu|kadro ilanı)(?!\w)", re.I)
DOCUMENT = re.compile(r"\.(?:pdf|docx?|xlsx?|pptx?|zip|rar)(?:$|\?)", re.I)
SHOP = re.compile(r"(?<!\w)(?:satın al|sepete ekle|fiyatı|fiyat listesi|indirim|kampanya|buy now|price|"
                  r"shop|store|ürün kodu)(?!\w)", re.I)
NEWS_HOST = re.compile(r"(?:^|\.)(?:haber|news|gazete|hurriyet|milliyet|sabah|sozcu|ntv|cnnturk|aa\.com|"
                       r"trthaber|iha|dha|bbc|reuters|medium)\.", re.I)
EVENT = re.compile(r"(?<!\w)(?:summit|zirve\w*|konferans\w*|conference|kongre\w*|congress|forum|festival\w*|"
                   r"hackathon|meetup|etkinli\w*|event|panel|sempozyum\w*|symposium|workshop)(?!\w)", re.I)
# Words of pages and links that list people, as whole words (not "dashboard", "steam").
PEOPLE_WORDS = re.compile(
    r"(?<!\w)(?:ekip|ekibimiz|ekibi|takımımız|kadro|kadromuz|kadrosu|akademik kadro|akademik personel|"
    r"öğretim üyeleri|ogretim uyeleri|öğretim elemanları|yönetim kurulu|yonetim kurulu|yönetim ekibi|"
    r"yonetim ekibi|yönetim|yonetim|kurucular|kurucularımız|kurucu üyeler|kurucu uyelerimiz|danışma kurulu|"
    r"danışmanlarımız|konuşmacılar|konusmacilar|konuşmacılarımız|jüri|juri|jüri üyeleri|mentorlar|"
    r"mentorlarımız|uzmanlarımız|hekimlerimiz|doktorlarımız|şeflerimiz|our team|team|the team|meet the team|"
    r"people|our people|staff|staff list|faculty|faculty members|faculty directory|academic staff|"
    r"leadership|leadership team|management team|board of directors|board|founders|speakers|judges|jury|"
    r"mentors|advisors|advisory board|researchers|members|directory|أعضاء هيئة التدريس|فريق العمل|فريقنا|"
    r"المتحدثون|مجلس الإدارة)(?!\w)", re.I)
# Kinds that never list the requested people: skipped without fetching.
SKIP = {"job_listing": "iş/kadro ilanı", "definition": "tanım veya maaş yazısı",
        "document": "PDF/ofis belgesi (yalnızca HTML okunur)", "shop": "ürün veya fiyat sayfası"}
BASE = {"people_list": 60, "profile": 50, "event": 40, "page": 25, "article": 20, "platform": 30}


@dataclass
class Triage:
    kind: str
    priority: int
    reason: str = ""

    @property
    def skip(self):
        return self.kind in SKIP


def classify(url, title="", snippet=""):
    """Page kind from what the search result shows."""
    path = unquote(urlsplit(url).path)
    host = (urlsplit(url).hostname or "").lower()
    head = f"{title} {path}"
    if never_fetch(url):
        return "platform"
    if DOCUMENT.search(path):
        return "document"
    if job_listing(head) or JOBS.search(head):
        return "job_listing"
    if DEFINITION.search(title):
        return "definition"
    if SHOP.search(title):
        return "shop"
    if PROFILE_PATH.search(path):
        return "profile"
    if PEOPLE_WORDS.search(head.replace("-", " ").replace("_", " ")):
        return "people_list"
    if EVENT.search(head):
        return "event"
    if NEWS_HOST.search(host) or re.search(r"/(?:haber|news|blog|makale|article)s?/", path, re.I):
        return "article"
    return "page"


def triage(url, title, snippet, spec):
    """Kind, fetch priority (higher first) and, for skipped kinds, the reason."""
    kind = classify(url, title, snippet)
    if kind in SKIP:
        return Triage(kind, 0, f"Ön eleme: {SKIP[kind]}; sayfa açılmadı.")
    text = f"{title} {snippet} {unquote(urlsplit(url).path).replace('-', ' ')}"
    score = BASE.get(kind, 20)
    matched = [t.label for t in spec.topics if any(contains(text, term) for term in t.match_terms if len(term) > 2)]
    score += 15 * min(len(matched), 2)
    if spec.location and place_matches(spec.location, text):
        score += 10
    if spec.roles and any(contains(text, w) for w in role_words(spec)):
        score += 5
    return Triage(kind, min(score, 100))


def role_words(spec):
    from app.services.search_quality import ROLES

    return [alias for role in spec.roles for alias in ROLES.get(role, []) if len(alias) > 2]


def follow_links(soup, base_url, limit=3):
    """Links on a page to people-list pages of the same site ("Ekibimiz", "Akademik Kadro")."""
    from urllib.parse import urljoin

    host = (urlsplit(base_url).hostname or "").lower().removeprefix("www.")
    found = []
    for anchor in soup.select("a[href]")[:1500]:
        label = " ".join(anchor.get_text(" ", strip=True).split())
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")) or len(label) > 60:
            continue
        target = urljoin(base_url, href).split("#")[0]
        parts = urlsplit(target)
        if parts.scheme not in ("http", "https") or parts.username or parts.password:
            continue
        if (parts.hostname or "").lower().removeprefix("www.") != host or target.rstrip("/") == base_url.rstrip("/"):
            continue
        path = unquote(parts.path).replace("-", " ").replace("_", " ")
        if not (PEOPLE_WORDS.search(label) or PEOPLE_WORDS.search(path)) or DOCUMENT.search(parts.path):
            continue
        if JOBS.search(label) or JOBS.search(path) or normalize(label) in ("kariyer", "careers", "jobs"):
            continue
        if target not in found:
            found.append(target)
        if len(found) >= limit:
            break
    return found
