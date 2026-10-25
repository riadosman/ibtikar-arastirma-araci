"""Profile platforms: searched, never fetched.

LinkedIn, ResearchGate, Crunchbase, F6S and The Official Board forbid automated retrieval
(robots.txt or HTTP 403), as do Google Scholar and social networks. A search engine's result
for a profile still names a person, a role and an organization. That is kept as an unverified
lead: the profile page itself is never read, so nothing about the person is verified.
"""

import re
from urllib.parse import unquote, urlsplit

from app.services.extraction import build, person_name
from app.services.search_quality import contains, roles_in

LEAD_SOURCE = "platform_search_result"
# Domain -> (name shown to reviewers, first path segment of a person's profile).
PROFILES = {
    "linkedin.com": ("LinkedIn", "in"),
    "researchgate.net": ("ResearchGate", "profile"),
    "crunchbase.com": ("Crunchbase", "person"),
    "f6s.com": ("F6S", "member"),
    "theofficialboard.com": ("The Official Board", "biography"),
}
# Never fetched either, but their results are not professional profiles.
CLOSED = ("scholar.google.com", "instagram.com", "facebook.com", "x.com", "twitter.com")
SEPARATOR = re.compile(r"\s+[-–—|·]\s+|\s*\|\s*")
EMPLOYER = re.compile(r"(.+?)\s+(?:at|@)\s+(.+)")
DEGREE = re.compile(r"(?:ph\.?\s?d\.?|mba|m\.?sc\.?|b\.?sc\.?|md)", re.I)
LOCATION = re.compile(r"(?:Konum|Location|Standort|Lieu|Ubicación)\s*:\s*([^·|\n]+)")


def domain_of(url):
    host = (urlsplit(url).hostname or "").lower()
    return next((d for d in (*PROFILES, *CLOSED) if host == d or host.endswith("." + d)), None)


def never_fetch(url):
    return domain_of(url) is not None


def clean(part):
    return re.sub(r"\s*(?:\.\.\.|…)$", "", part).strip(" ,;")


def profile_lead(url, title, snippet, location=""):
    """CandidateCreate for a named person's profile result, or None."""
    domain = domain_of(url)
    if domain not in PROFILES:
        return None
    label, prefix = PROFILES[domain]
    segments = [s for s in unquote(urlsplit(url).path).split("/") if s]
    if len(segments) < 2 or segments[0].casefold() != prefix:
        return None
    original = " ".join((title or "").split())
    # Cut the platform name and anything after it: Yahoo glues the next result's title on.
    cut = re.search(re.escape(label), original, re.I)
    heading = (original[:cut.start()] if cut and cut.start() else original).rstrip(" -–—|·")
    parts = [clean(p) for p in SEPARATOR.split(heading) if clean(p)]
    if not parts:
        return None
    # "Deger Ayata, PhD", "Zeshan Alam (PhD, PEng)", "Hakan Saglam Bio"
    raw = re.sub(r"\s*\(.*?\)", "", parts[0]).split(",")[0]
    name = person_name(re.sub(r"\s+Bio$", "", raw))
    if not name:
        return None
    role = organization = None
    for part in parts[1:]:
        employer = EMPLOYER.fullmatch(part)
        if role is None and employer:
            role, organization = clean(employer.group(1)), clean(employer.group(2))
        elif role is None and roles_in(part):
            role = part
        elif organization is None and not roles_in(part) and not DEGREE.fullmatch(part):
            organization = part
    text = f"{original} {snippet or ''}"
    place = LOCATION.search(snippet or "")
    if place and any(c.isalpha() for c in place.group(1)):  # not a postal code
        location = clean(place.group(1))
    elif not (location and contains(text, location)):
        location = None
    return build(
        full_name=name,
        job_title=(role or "")[:200] or None,
        organization=(organization or "")[:200] or None,
        location=location,
        headline=heading[:2000],
        linkedin_url=url if domain == "linkedin.com" else None,
        website=None if domain == "linkedin.com" else url,
        source_url=url,
        source_name=f"{label} arama sonucu",
        source_type=LEAD_SOURCE,
        source_evidence=f"{label} arama sonucu (sayfa açılmadı): {original} — {snippet or ''}"[:2000],
    )
