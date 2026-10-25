"""Conservative, keyless extraction. Missing facts remain missing."""

import json
import re
import time
import unicodedata
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup
from pydantic import ValidationError

from app.schemas import CandidateCreate
from app.services.arabic_names import ARABIC_LETTER, arabic_name
from app.services.mentions import mentioned_people
from app.services.page_context import page_context as owner_context
from app.services.record_blocks import (
    PEOPLE_PAGE,
    boilerplate,
    describe,
    find_records,
    profile_link,
    remove_chrome,
)
from app.services.search_quality import ROLES, job_listing, normalize, roles_in
from app.services.topics import topic_phrase


def name_key(value):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", value.casefold().replace("ı", "i"))
        if c.isalpha()
    )


STOP_WORDS = set(
    "university faculty department school research laboratory lab contact home about people team members computer vision artificial intelligence professor assistant associate welcome profile academic publications projects news engineering science technology istanbul ankara türkiye turkey official page dr prof üniversitesi mühendisliği araştırma bölümü akademik".split()
)
STOP_WORDS.update(
    "support staff program programs structure overview other affiliated industrial training advisory board gender equality success story admission admissions undergraduate graduate students student education events career careers services resources alumni calendar courses course news announcements awards grants funding visitor visitors".split()
)
STOP_WORDS.update("chef chefs şef şefler aşçı aşçılar mutfak mutfağı yemek haber haberleri turkish famous best yeni gizlilik politikası iletişim biyografi".split())
# Listing-page headings ("Öğretim Üyeleri", "Yapay Zeka Konuşmacıları") are never a person's name.
STOP_WORDS.update("öğretim üyeleri üyesi konuşmacı konuşmacılar konuşmacıları speakers yapay zeka zekâ kadro kadrosu personel uzmanlar uzmanları akademisyen akademisyenler hocalar hocalarımız ekibi ekibimiz yönetim bölüm bölümü ünlü insanları".split())
# "Üyelerimiz", "Danışmanlarımız", "Ekibimiz": "our ..." headings, never part of a name.
POSSESSIVE_HEADING = re.compile(r"(?:ımız|imiz|umuz|ümüz)$")
ROLE_LABEL = re.compile(
    r"^(?P<role>" + "|".join(re.escape(x) for x in sorted({x for xs in ROLES.values() for x in xs} | {"Prof. Dr.", "Avukat", "Mimar", "Diyetisyen", "Psikolog"}, key=len, reverse=True)) + r")\s+(?P<name>.+)$", re.I
)



# CPU guards: crafted pages with deep nesting must not stall the only worker.
EXTRACTION_SECONDS = 10
MAX_LABEL_DESCENDANTS = 12
# A directory can list hundreds of people; collection ranks them against the brief.
MAX_PEOPLE_PER_PAGE = 300


def labeled_people(soup, deadline=None):
    """Names explicitly labeled with a profession and repeated in adjacent biography text."""
    seen = set()
    for element in soup.select("h1,h2,h3,h4,strong,b,span,p,div")[:2500]:
        if deadline and time.monotonic() > deadline:
            return
        # A role label is a short element; get_text() on a large subtree is expensive.
        if len(element.find_all(True, limit=MAX_LABEL_DESCENDANTS + 1)) > MAX_LABEL_DESCENDANTS:
            continue
        if element.find_parent(["nav", "header", "footer", "aside"]):
            continue
        label = re.sub(r"^\s*\d{1,3}\s*[.)-]\s*", "", element.get_text(" ", strip=True))
        if len(label) > 110:
            continue
        match = ROLE_LABEL.fullmatch(label)
        if not match and re.search(r"\s[—–|]\s", label):
            parts = re.split(r"\s[—–|]\s", label, maxsplit=1)
            if roles_in(parts[1]):
                match = {"name": parts[0], "role": parts[1]}
        name = person_name(match["name"]) if match else None
        if not name or name_key(name) in seen:
            continue
        evidence = ""
        # Stay in the local biography section, rather than borrowing a whole page.
        for paragraph in element.find_all_next(["p", "div"], limit=5):
            if len(paragraph.find_all(True, limit=200)) >= 200:
                continue
            value = paragraph.get_text(" ", strip=True)
            if 80 <= len(value) <= 5000 and name_key(name) in name_key(value):
                evidence = value[:2000]
                break
        if evidence:
            seen.add(name_key(name))
            yield name, match["role"], evidence


def person_name(value):
    if not isinstance(value, str):
        return None
    if ARABIC_LETTER.search(value):
        # No capital letters to go by: Arabic needs its own evidence.
        return arabic_name(value.strip()) if len(value) <= 100 else None
    value = re.sub(r"^(?:(?:Prof|Dr|Assoc|Asst)\.?\s+)+", "", value.strip(), flags=re.I)
    words = value.split()
    if not 2 <= len(words) <= 5 or len(value) > 100:
        return None
    if job_listing(value) or any(normalize(word).strip(".,") in {normalize(w) for w in STOP_WORDS} for word in words):
        return None
    if any(POSSESSIVE_HEADING.search(word.casefold()) for word in words):
        return None
    if topic_phrase(value):
        return None  # a research area heading ("Bilgisayarlı Görü"), not a person
    # Every word is capitalized; a script without capital letters gives no such evidence.
    if any(
        (not word[0].isupper() and word not in ("de", "van", "von", "del", "da")) or not all(c.isalpha() or c in "-'.’" for c in word) for word in words
    ):
        return None
    return value


def build(**fields):
    """CandidateCreate, or None when page data fails validation (e.g. a huge URL)."""
    try:
        return CandidateCreate(**fields)
    except ValidationError:
        if fields.pop("public_email", None) or fields.pop("website", None):
            return build(**fields)  # an odd address must not cost the person
        return None


BLOCK_TAGS = ("p", "div", "li", "td", "th", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "br", "section",
              "article", "blockquote", "dd", "dt", "figcaption", "caption")


def line_text(soup):
    """Visible body text with one line per block element, so phrases never join across them."""
    body = soup.body or soup
    for element in body.find_all(["head", "title"]):
        element.decompose()  # the title repeats the name next to unrelated words
    for element in body.find_all(BLOCK_TAGS):
        element.insert_after("\n")
    text = re.sub(r"[ \t\xa0]+", " ", body.get_text(" "))
    return re.sub(r"\s*\n\s*", "\n", text).strip()[:60000]


def listed_people(soup, url, title, context, deadline):
    """People from repeated record blocks (staff, team, board, speaker lists)."""
    body = soup.body or soup
    remove_chrome(body)
    hint = " ".join([unquote(urlsplit(url).path), title or "",
                     *(h.get_text(" ", strip=True) for h in body.select("h1, h2")[:6])])
    people_page = bool(PEOPLE_PAGE.search(hint))
    found = {}
    for _, records in find_records(body, person_name, hint, deadline, time.monotonic):
        for record in records:
            key = name_key(record.name)
            title_, role, expertise, email = describe(record)
            entry = found.get(key)
            if entry and (entry[1] or not role):
                continue  # the same person in a second layout (card + modal) adds nothing
            found[key] = (record, role, title_, expertise, email)
    candidates = []
    for record, role, title_, expertise, email in found.values():
        own = [line for line in record.lines if line.strip()]
        evidence = " | ".join(own)[:700]
        bio = evidence if len(evidence) > len(record.name) + len(role) + 60 else None
        facts = []
        organization = city = country = None
        if people_page and context.organization:
            organization = context.organization[:200]
            facts.append(f"kurum: {organization} ({context.organization_evidence.lower()})")
        # News sites' columnist strips are rare; a site's listed people are mostly its own.
        if context.city or context.country:
            city, country = context.city, context.country
            facts.append(f"konum: {', '.join(filter(None, [city, country]))} "
                         f"({context.location_evidence.lower()})")
        note = f" [Sayfa bağlamından çıkarıldı — {'; '.join(facts)}]" if facts else ""
        job = role or title_ or None
        candidate = build(
            full_name=record.name, job_title=(job or "")[:200] or None, organization=organization,
            city=city, country=country, bio=bio, expertise=[e[:200] for e in expertise],
            public_email=email, website=profile_link(record, url),
            source_url=url, source_name=(title or "Kişi listesi")[:200], source_type="people_list",
            source_evidence=(evidence + note)[:2000],
        )
        if candidate:
            candidates.append(candidate)
    return candidates


def extract_profiles(html, url, title="", budget_seconds=EXTRACTION_SECONDS):
    deadline = time.monotonic() + budget_seconds
    soup = BeautifulSoup(html, "html.parser")
    structured = []
    kinds = set()
    organizations = set()  # names the page itself declares as an organization
    for script in soup.select('script[type="application/ld+json"]')[:30]:
        try:
            pending = [json.loads(script.string or script.get_text())]
        except (ValueError, RecursionError):
            continue
        visited = 0
        while pending and visited < 1000:
            node = pending.pop()
            visited += 1
            if isinstance(node, list):
                pending.extend(node)
            elif isinstance(node, dict):
                kind = node.get("@type", [])
                kinds.update(k for k in (kind if isinstance(kind, list) else [kind]) if isinstance(k, str))
                if "Person" in (kind if isinstance(kind, list) else [kind]):
                    structured.append(node)
                elif "Organization" in (kind if isinstance(kind, list) else [kind]) and isinstance(node.get("name"), str):
                    organizations.add(name_key(node["name"]))
                pending.extend(v for v in node.values() if isinstance(v, (dict, list)))
    headings = [h.get_text(" ", strip=True) for h in soup.select("h1")[:5]]
    # Site-wide Organization markup (SEO plugins, Wikipedia's publisher) says nothing about the
    # people listed on the page; only names declared as organizations are excluded below.
    if "JobPosting" in kinds or job_listing(" ".join([title, *headings])):
        return soup.get_text(" ", strip=True)[:50000], []
    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    # Before footers go: the address there is the page owner's location.
    context = owner_context(soup, url, page_title or title)
    # University/lab directories often expose names as profile links, not JSON-LD.
    # Require both a directory context and name evidence in the profile URL.
    directory_links = []
    directory_cards = []
    page_context = " ".join([title, *headings]).casefold()
    if any(
        word in page_context
        for word in ("faculty", "staff", "people", "team", "members", "akademik", "kadro", "ekip")
    ):
        # Explicit staff cards may link by username, rather than a full-name slug.
        # Bind the heading and role to one card; never treat arbitrary headings as people.
        for card in soup.select(".team-member, .faculty-member, .staff-member")[:100]:
            if card.find_parent(["nav", "header", "footer"]):
                continue
            names = card.select("h2, h3, h4, .profile-name")
            if len(names) != 1:
                continue
            name = person_name(names[0].get_text(" ", strip=True))
            role_element = names[0].find_next_sibling(["span", "p"])
            role = role_element.get_text(" ", strip=True) if role_element else ""
            if not name or not roles_in(role):
                continue
            for anchor in card.select("a[href]"):
                if anchor.get_text(" ", strip=True).casefold() not in ("profil", "profile"):
                    continue
                target = urljoin(url, anchor["href"])
                parts = urlsplit(target)
                if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
                    continue
                directory_cards.append((name, role[:200], target))
                break
        for anchor in soup.select("a[href]")[:1000]:
            if anchor.find_parent(["nav", "header", "footer"]):
                continue
            name_element = anchor.select_one(".profile-name")
            name_text = (
                " ".join(name_element.find_all(string=True, recursive=False)).strip()
                if name_element
                else anchor.get_text(" ", strip=True)
            )
            name = person_name(name_text)
            role_element = name_element.find("em") if name_element else None
            role = role_element.get_text(" ", strip=True)[:200] if role_element else None
            target = urljoin(url, anchor.get("href", ""))
            parts = urlsplit(target)
            if (
                not name
                or parts.scheme not in ("http", "https")
                or not parts.hostname
                or parts.username
                or parts.password
            ):
                continue
            segments = [segment for segment in unquote(parts.path).split("/") if segment]
            classes = " ".join(anchor.get("class", []) + anchor.parent.get("class", []))
            profile_markup = name_element is not None or any(
                marker in classes
                for marker in ("profile", "person", "faculty-member", "staff-member")
            )
            if not profile_markup:
                continue
            if not segments or name_key(name) not in name_key(segments[-1]):
                continue
            # Keep the exact linked name as evidence; do not attribute a whole roster's biography to one person.
            directory_links.append((name, target, role))
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    total = len((soup.body or soup).get_text(" ", strip=True)) or 1
    for tag in soup(["nav", "footer", "header", "aside"]):
        if not getattr(tag, "decomposed", False) and boilerplate(tag, total):
            tag.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())[:50000]
    listed = listed_people(soup, url, page_title or title, context, deadline)
    candidates, seen = [], set()
    for name, role, target in directory_cards:
        if name.casefold() in seen:
            continue
        candidate = build(
            full_name=name, job_title=role, website=target,
            source_url=url, source_name=(title or "Academic staff directory")[:200],
            source_type="directory_person_card",
            source_evidence=f"{name} - {role}"[:2000],
        )
        if candidate:
            candidates.append(candidate)
            seen.add(name.casefold())
    for node in structured:
        name = person_name(node.get("name"))
        if not name or name.casefold() in seen:
            continue
        # Ignore schema.org Person entries for article authors/editors unrelated to the profile.
        if not any(name.casefold() in heading.casefold() for heading in headings) and name_key(
            name
        ) not in name_key(unquote(urlsplit(url).path)):
            continue
        org = node.get("worksFor") or node.get("affiliation")
        org = org.get("name") if isinstance(org, dict) else None
        role = node.get("jobTitle")
        description = node.get("description")
        facts = [v for v in (name, role, org) if isinstance(v, str) and v]
        candidate = build(
            full_name=name,
            organization=org if isinstance(org, str) else None,
            job_title=role[:200] if isinstance(role, str) else None,
            bio=description[:20000] if isinstance(description, str) else None,
            source_url=url,
            source_name=(title or name)[:200],
            source_type="structured_profile",
            source_evidence=("Schema.org Person: " + ", ".join(facts))[:2000],
        )
        if not candidate:
            continue
        candidates.append(candidate)
        seen.add(name.casefold())
    # A personal site's root URL can carry the identity in its hostname.
    # Keep heading evidence local so unrelated footer roles cannot qualify a name.
    for heading in soup.select('h1,h2')[:30]:
        name = person_name(heading.get_text(' ', strip=True))
        if not name or name.casefold() in seen:
            continue
        adjacent = heading.find_next_sibling(['h2', 'h3', 'p'])
        evidence = adjacent.get_text(' ', strip=True) if adjacent else ''
        identity_url = name_key(unquote(urlsplit(url).path)) + name_key(urlsplit(url).hostname or '')
        if name_key(name) not in identity_url or not roles_in(evidence) or len(evidence) > 800:
            continue
        candidate = build(full_name=name, job_title=evidence[:200], bio=evidence,
                          source_url=url, source_name=(title or name)[:200],
                          source_type="profile_intro", source_evidence=evidence[:2000])
        if candidate:
            candidates.append(candidate)
            seen.add(name.casefold())
    # Heading-based proposals need a matching page title and the name in visible text.
    page_title = page_title or title
    for heading in headings:
        name = person_name(heading)
        if (
            name
            and name.casefold() not in seen
            and name.casefold() in page_title.casefold()
            and name.casefold() in text.casefold()
            and name_key(name) in name_key(unquote(urlsplit(url).path))
            and roles_in(text)
        ):
            candidate = build(
                full_name=name,
                bio=text[:2500],
                source_url=url,
                source_name=page_title[:200],
                source_type="profile_heading",
                source_evidence=text[:500],
            )
            if candidate:
                candidates.append(candidate)
                seen.add(name.casefold())
    for name, target, role in directory_links:
        if name.casefold() in seen:
            continue
        # A directory link proves a listed name, not a biography: keep it as evidence.
        candidate = build(
            full_name=name,
            job_title=role or None,
            sources=[
                {
                    "url": url,
                    "name": (title or "Academic directory")[:200],
                    "source_type": "directory_name_link",
                    "evidence": f"Dizin bu kişiyi listeliyor ve profile bağlantı veriyor: {target}"[
                        :2000
                    ],
                }
            ],
            website=target,
        )
        if candidate:
            candidates.append(candidate)
            seen.add(name.casefold())
    known_names = {name_key(c.full_name) for c in candidates}
    for candidate in listed:
        if name_key(candidate.full_name) not in known_names:
            candidates.append(candidate)
            known_names.add(name_key(candidate.full_name))
    for name, role, evidence in labeled_people(soup, deadline):
        if name_key(name) in known_names:
            continue
        candidate = build(
            full_name=name, job_title=role, bio=evidence, source_url=url,
            source_name=(title or name)[:200], source_type="named_biography",
            source_evidence=evidence[:2000],
        )
        if candidate:
            candidates.append(candidate)
            known_names.add(name_key(name))
    if not listed:
        # An article or event page: people named in running text, anchored by a title or role.
        for name, role, evidence in mentioned_people(line_text(soup), person_name):
            if name_key(name) in known_names:
                continue
            candidate = build(full_name=name, job_title=role[:200] or None, source_url=url,
                              source_name=(title or name)[:200], source_type="text_mention",
                              source_evidence=evidence[:2000])
            if candidate:
                candidates.append(candidate)
                known_names.add(name_key(name))
    candidates = [c for c in candidates if name_key(c.full_name) not in organizations]
    return text, candidates[:MAX_PEOPLE_PER_PAGE]
