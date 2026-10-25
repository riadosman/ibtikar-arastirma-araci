"""Conservative request-scoped identity matching.

Strong identifiers (personal profile URL, personal email) still need a compatible name,
because pages often repeat one shared address or company page for many people. A shared
company domain or organization alone is never identity. When unsure, keep two records:
a reviewer can merge by rejecting one, but a wrong merge silently loses a person.
"""

import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import unquote, urlsplit

# Mailboxes that belong to a team, not to one person.
ROLE_MAILBOXES = {
    "info", "contact", "iletisim", "hello", "office", "admin", "support", "team", "press",
    "media", "basin", "kontakt", "events", "etkinlik", "secretary", "sekreterlik", "noreply",
    "no-reply", "mail", "bilgi", "hr", "ik", "jobs", "careers", "kariyer", "sales",
}
PERSONAL_PROFILE_PATHS = {
    "linkedin.com": ("in",),
    "twitter.com": None,
    "x.com": None,
    "instagram.com": None,
}


def normalized(value):
    value = unicodedata.normalize("NFKD", (value or "").replace("ı", "i").replace("İ", "I"))
    value = "".join(c for c in value.casefold() if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", value).strip()


def host(value):
    netloc = urlsplit(value or "").hostname or ""
    netloc = netloc.lower().removeprefix("www.")
    # tr.linkedin.com and de.linkedin.com are the same profile host.
    return "linkedin.com" if netloc.endswith(".linkedin.com") else netloc


def domain(value):
    return host(value)


def profile(value):
    """Canonical host+path; query strings, fragments and trailing slashes are ignored."""
    if not value:
        return ""
    return (host(value) + urlsplit(value).path.rstrip("/")).casefold()


def personal_profile(value):
    """Canonical key of a URL that identifies one person, e.g. "linkedin.com/in/ada".

    Company pages and listings return "". Sub-pages (/in/ada/details/...) and encoding
    differences map to the same key.
    """
    if not value:
        return ""
    site = host(value)
    segments = [s for s in unquote(urlsplit(value).path).casefold().split("/") if s]
    if site not in PERSONAL_PROFILE_PATHS or not segments:
        return ""
    prefixes = PERSONAL_PROFILE_PATHS[site]
    if prefixes is None:
        handle = segments[0]
        return "" if handle in ("home", "search", "i", "explore") else f"{site}/{handle}"
    if segments[0] in prefixes and len(segments) >= 2:
        return f"{site}/{segments[0]}/{segments[1]}"
    return ""


def page_key(value):
    """A specific web page (path and query), used for personal websites."""
    if not value:
        return ""
    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    if not path and not parts.query:
        return ""  # a bare domain is shared by everyone at an organization
    return (host(value) + path + ("?" + parts.query if parts.query else "")).casefold()


def personal_email(value):
    email = (value or "").strip().casefold()
    local = email.split("@", 1)[0]
    return "" if not email or local in ROLE_MAILBOXES else email


# Academic/professional titles that sources add or omit ("Prof. Dr. Ayşe", "Doç. Dr.", "د.").
TITLES = {
    "dr", "prof", "professor", "doc", "docent", "assoc", "asst", "assist", "yrd", "ogr", "gor",
    "ars", "mr", "mrs", "ms", "miss", "eng", "muh", "av", "د", "ا", "أ",
}


def person_key(value):
    """Normalized name without leading titles; used only for comparing names."""
    tokens = normalized(value).split()
    while len(tokens) > 2 and tokens[0] in TITLES:
        tokens.pop(0)
    return " ".join(tokens)


def same_name(first, second):
    """Equal after normalization, or a one-letter spelling/transliteration difference."""
    a, b = person_key(first), person_key(second)
    if not a or not b:
        return False
    if a == b:
        return True
    matcher = SequenceMatcher(None, a, b)
    # Cheap upper bounds first: dedup compares every incoming name with every existing one.
    return matcher.real_quick_ratio() >= 0.94 and matcher.quick_ratio() >= 0.94 and (
        matcher.ratio() >= 0.94
    )


def names_compatible(first, second):
    """same_name, or one name adds a middle name ("Ayşe Yılmaz" / "Ayşe Nur Yılmaz").

    The looser rule is only used together with a personal email or profile URL; common
    names such as "Mehmet Yılmaz" and "Mehmet Ali Yılmaz" can be two people at one place.
    """
    if same_name(first, second):
        return True
    shorter, longer = sorted((person_key(first).split(), person_key(second).split()), key=len)
    return (
        len(shorter) >= 2
        and shorter[0] == longer[0]
        and shorter[-1] == longer[-1]
        and set(shorter) <= set(longer)
    )


def incoming_source_urls(incoming):
    urls = {source.url for source in incoming.sources}
    if incoming.source_url:
        urls.add(incoming.source_url)
    return urls


def match_reason(candidate, incoming):
    """Why two records are the same person, or None. Names must always agree."""
    if not names_compatible(incoming.full_name, candidate.full_name):
        return None
    strict = same_name(incoming.full_name, candidate.full_name)
    email = personal_email(incoming.public_email)
    if email and email == personal_email(candidate.public_email):
        return "email"
    for field in ("linkedin_url", "twitter_url", "instagram_url"):
        key = personal_profile(getattr(incoming, field))
        if key and key == personal_profile(getattr(candidate, field)):
            return "profile_url"
    # The same specific web page (e.g. a staff profile) is identity only with the same name:
    # directory pages such as personel.aspx?id=5 differ only by query.
    key = page_key(incoming.website)
    if strict and key and key == page_key(candidate.website):
        return "profile_url"
    exact_name = person_key(incoming.full_name) == person_key(candidate.full_name)
    if exact_name and incoming_source_urls(incoming) & {s.url for s in candidate.sources}:
        return "name_and_source"
    if not strict:
        return None
    if incoming.organization and normalized(incoming.organization) == normalized(
        candidate.organization
    ):
        return "name_and_organization"
    if incoming.website and candidate.website and domain(incoming.website) == domain(candidate.website):
        return "name_and_domain"
    return None


def deduplicate_candidates(existing, incoming):
    """Return a match to merge, or None. Never match across research requests.

    Conflicting personal identifiers (two different personal emails or LinkedIn profiles)
    always mean two people, even with the same name.
    """
    for candidate in existing:
        email_a, email_b = personal_email(incoming.public_email), personal_email(candidate.public_email)
        if email_a and email_b and email_a != email_b:
            continue
        linked_a = personal_profile(incoming.linkedin_url)
        linked_b = personal_profile(candidate.linkedin_url)
        if linked_a and linked_b and linked_a != linked_b:
            continue
        if match_reason(candidate, incoming):
            return candidate
    return None
