"""Site-independent extraction of people listed on staff, team, board and speaker pages.

Such pages repeat one record layout per person: a card, a table row or a list item with the
name in the same position. Records are found by their shape, not by site-specific class
names:

1. Every short text line is parsed as a possible name: academic titles ("Prof. Dr.",
   "Dr. Öğr. Üyesi", "Assoc. Prof."), degrees (", Ph.D."), "Role: Name", "Name – Role" and
   "Surname, Given" are handled.
2. Name lines are grouped by their structural signature: the tag and classes of the element
   and of its block ancestors, ignoring inline tags and per-item ids. A layout repeated for
   three or more names is a candidate list.
3. A list is accepted only with person evidence: many names start with a known given name,
   records carry titles or roles, or the page itself is a people page. Product and service
   cards ("Mobile App Development") are capitalized too, but carry none of this.
4. Each person's record block is the largest element around the name that contains no other
   listed name. Role, title, research areas, a profile link and a public e-mail are read only
   from that block, so one person's details are never attributed to another.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import Comment, Declaration, Doctype, ProcessingInstruction, Tag

from app.services.arabic_names import ARABIC_LETTER, HONORIFICS
from app.services.arabic_names import fold as fold_arabic
from app.services.given_names import fold, folded, known_given_name
from app.services.page_context import CITIES, COUNTRIES
from app.services.search_quality import normalize
from app.services.topics import topic_phrase

INLINE = {"a", "span", "strong", "b", "em", "i", "u", "small", "font", "abbr", "mark", "sup", "sub",
          "label", "time", "cite", "bdi", "big", "br"}
SKIP = {"script", "style", "noscript", "template", "svg", "select", "option", "button", "textarea",
        "iframe", "head", "title", "meta"}
NOT_TEXT = (Comment, Declaration, Doctype, ProcessingInstruction)
HEADINGS = ("h2", "h3", "h4", "h5", "h6")
# Class/id parts of navigation chrome. "header" is not here: cards keep names in "card-header".
CHROME = {"menu", "navbar", "nav", "navigation", "breadcrumb", "breadcrumbs", "sidebar", "footer",
          "cookie", "cookies", "pagination", "offcanvas", "megamenu", "submenu", "dropdown", "topbar",
          "share", "sharing", "social", "skip", "toc", "widget_recent_entries"}
TITLE_TOKENS = [
    r"prof(?:essor)?\.?\s*dr\.?", r"do[çc]\.?\s*dr\.?", r"dr\.?\s*[öo]ğr(?:etim)?\.?\s*[üu]yesi",
    r"dr\.?\s*[öo]ğretim\s+[üu]yesi", r"yrd\.?\s*do[çc]\.?\s*dr\.?", r"yard\.?\s*do[çc]\.?\s*dr\.?",
    r"[öo]ğr\.?\s*g[öo]r\.?\s*dr\.?", r"[öo]ğr\.?\s*g[öo]r\.?", r"[öo]ğretim\s+g[öo]revlisi",
    r"ara?[şs]\.?\s*g[öo]r\.?\s*dr\.?", r"ara?[şs]\.?\s*g[öo]r\.?", r"ar\.?\s*g[öo]r\.?",
    r"ara[şs]t[ıi]rma\s+g[öo]revlisi", r"uzm\.?\s*dr\.?", r"op\.?\s*dr\.?",
    r"assoc(?:iate)?\.?\s*prof(?:essor)?\.?(?:\s*dr\.?)?", r"ass(?:is|t|ist)\.?\s*prof(?:essor)?\.?(?:\s*dr\.?)?",
    r"assistant\s+prof(?:essor)?\.?(?:\s*dr\.?)?", r"res\.?\s*asst\.?(?:\s*dr\.?)?", r"lect\.?(?:\s*dr\.?)?",
    r"instr\.?(?:\s*dr\.?)?", r"prof\.?", r"dr\.?", r"mr\.?", r"mrs\.?", r"ms\.?", r"miss", r"sir",
    r"eng\.?", r"m[üu]h\.?", r"av\.?", r"dt\.?", r"ing\.?", r"dipl\.?-ing\.?", r"retired", r"emerit(?:us|a)",
]
# A title ends at a space, or at a capital letter right after its dot ("Prof.Dr.Ali"); never
# inside a word ("Muhammed", "Engin" start like "Müh.", "Eng.").
TITLE_PREFIX = re.compile(r"^(?:" + "|".join(TITLE_TOKENS) + r")(?=\s|$|(?<=\.)(?-i:[A-ZÇĞİÖŞÜ]))\s*", re.I)
# A degree after the name is a separate word. Short ones ("MA", "MD", "Dr") also end surnames
# ("Fermi Ma", "Mario Badr"), so they need a comma or parenthesis before them.
DEGREE_SUFFIX = re.compile(
    r"(?:\s*[,(]\s*|\s+)(?:ph\.?\s?d\.?|mba|m\.?\s?sc\.?|b\.?\s?sc\.?|pmp|cfa|prof\.?\s*dr\.?|do[çc]\.?\s*dr\.?)"
    r"\s*\)?\s*$|\s*[,(]\s*(?:m\.?\s?d\.?|m\.?\s?a\.?|dr\.?)\s*\)?\s*$", re.I)
SEPARATOR = re.compile(r"\s+[–—|·•]\s+|\s+-\s+|\s*[–—|]\s*(?=[A-ZÇĞİÖŞÜ])")
# Only a one-word nickname or a quoted name is dropped: "Kuei (Jack) Sun". A longer aside
# ("Tavuk Salamura (Ünlü Şeften)") marks a title or a description, which is not a name.
NICKNAME = re.compile(r"\s*(?:\([A-ZÇĞİÖŞÜ][\w'-]{1,15}\)|\"[^\"]{1,20}\"|“[^”]{1,20}”)\s*")
LEADER = re.compile(r"^\s*(?:\d{1,3}\s*[.)-]|[•·»▪►\-–—*])\s*")
EMAIL = re.compile(r"[\w.+-]+(?:@|\s*\[at\]\s*|\s*\(at\)\s*)[\w-]+(?:\.[\w-]+)+", re.I)
PHONE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
LINK_LABELS = {"profil", "profile", "homepage", "home page", "website", "web", "web sitesi", "mail",
               "e-mail", "email", "e-posta", "eposta", "detay", "detaylı bilgi", "detayli bilgi", "devamı",
               "devami", "more", "read more", "learn more", "view profile", "details", "cv", "özgeçmiş",
               "ozgecmis", "linkedin", "twitter", "google scholar", "scholar", "orcid", "github", "»",
               "bio", "biyografi", "incele", "tümü", "x", "facebook", "instagram", "youtube"}
# Lines that state a role or title. A broad list: it only decides what a record says about a
# person; whether that role is the one requested is decided later (search_quality).
ROLE_WORDS = re.compile(
    r"(?<!\w)(?:prof(?:essor)?|profes[öo]r|do[çc]ent|lecturer|instructor|teaching|researcher|research|"
    r"scientist|postdoc|fellow|emerit\w*|adjunct|visiting|chair\w*|dean|director|direkt[öo]r\w*|head|"
    r"president|ceo|cto|cfo|coo|cmo|cio|founder|co-?founder|founding|partner|owner|board|member|"
    r"advisor|adviser|consultant|specialist|expert|analyst|editor|representative|coordinator|officer|"
    r"lead|manager|engineer|developer|designer|architect|chef|doctor|physician|speaker|moderator|"
    r"panelist|mentor|jury|judge|principal|principle|associate|assistant|student|candidate|intern|"
    r"distinguished|instructional|endowed|clinical|investigator|"
    r"öğretim|ogretim|araştırma\w*|arastirma\w*|görevlisi|gorevlisi|üyesi|uyesi|üye|uye|uzman\w*|müdür\w*|"
    r"mudur\w*|yönetici\w*|yonetici\w*|başkan\w*|baskan\w*|kurucu\w*|ortak\w*|danışman\w*|danisman\w*|"
    r"mühendis\w*|muhendis\w*|geliştirici|gelistirici|tasarımcı|tasarimci|sorumlu\w*|koordinat[öo]r\w*|"
    r"şef|sef|aşçı|asci|doktor|hekim|avukat|edit[öo]r|temsilci\w*|konuşmacı|konusmaci|moderat[öo]r|"
    r"jüri|juri|genel sekreter|sekreter|yardımcısı|yardimcisi|vekili|lideri|"
    r"أستاذ|مدير|رئيس|مؤسس|مهندس|باحث|عضو|محاضر|خبير)(?!\w)", re.I)
PEOPLE_PAGE = re.compile(
    r"people|our-team|the-team|team|staff|faculty|members|directory|speakers|jury|judges|board|"
    r"leadership|management|founders|advisors|mentors|experts|ekip|ekib|kadro|ogretim-uyeleri|"
    r"öğretim üyeleri|ogretim uyeleri|personel|yonetim|yönetim|kurucu|konusmaci|konuşmacı|jüri|juri|"
    r"mentor|danisman|danışman|uzmanlar|akademisyen|academic|هيئة|فريق|المتحدث|أعضاء", re.I)
# Words that make a capitalized phrase a heading, a company or a service, not a person's name.
NON_NAME = folded("""
about academic academy accessibility agency ajans alanları alumni anasayfa application apply araştırma
award awards başvuru blog board capital center centre çözüm çözümler çözümleri company consulting
contact corporate data department design development digital directory duyuru duyurular eğitim
engineering enerji energy etkinlik event events faculty finans finance firma fund galeri gallery global
grup group haber haberler hakkımızda hizmet hizmeti hizmetleri hizmetler holding home iletişim
innovation institute kapital kariyer kodları kurumsal kurulu kurul laboratory lab labs legal limited
management marketing medya merkezi merkez misyon mobilitesi mümkün müşavirlik news office ofis
ortakları partners platform politikası portal privacy product products program programs project
projects projeler proje sahibi school services service sistem sistemleri software solutions startup
studio summit team teknoloji teknolojileri technologies technology tüketici university üniversitesi
ventures video vizyon web workshop yazılım yönetim yönetimi menü menu sayfa page kod code tag script
swiper analytics login register search arama sepet cart google scholar koleji lisesi okulu
safety health website webpage homepage personal phone number position name title email room
öğrenci öğrenciler asistan asistanlar asistanları idari personeli araştırmacılar uzmanlar öğretmenler
hukuk hukuku anabilim dalı bşk kurumu kurum müdürlüğü başkanlığı bakanlığı photo available image
robot robots control continuum
keşfet keşfedin davet edin incele inceleyin başvur başvurun izle izleyin tıkla tıklayın kaydol katıl katılın
programı discover explore invite join watch subscribe download
analysis network networks social business solution systems system processing learning mining intelligence science sciences studies information communication communications security hardware computing computer computers applications mathematics statistics physics chemistry biology economics modeling modelling optimization theory methods online
gıda yatırımları yatırım sanayi sanayii ticaret inşaat bankası banka sigorta lojistik turizm otomotiv
tekstil ilaç kimya medikal mobilya elektrik elektronik makina makine grubu şirketi şirketleri derneği
vakfı federasyonu odası borsası ajansı stüdyo platformu girişim girişimi
status contact interests areas doktora sonrası lisans yüksek ar-ge menüsü fiyat listesi tarifi tarifleri
""")
COMPANY_SUFFIX = re.compile(r"(?<!\w)(?:a\.?ş\.?|ltd\.?|şti\.?|inc\.?|llc|gmbh|corp\.?|plc|s\.a\.|b\.v\.)(?!\w)", re.I)
# "Başkan'dan", "Ankara'nın": an inflected word, not a name as written on a record.
CASE_SUFFIX = re.compile(r"['’](?:dan|den|tan|ten|ndan|nden|in|ın|un|ün|nin|nın|nun|nün|a|e|ya|ye|na|ne|"
                         r"da|de|ta|te|nda|nde|ı|i|u|ü|yı|yi|yu|yü|ni|nı|la|le|yla|yle)$", re.I)
EXPERTISE_LABEL = re.compile(r"^(?:research (?:areas?|interests?)|interests?|araştırma alanları|"
                             r"arastirma alanlari|uzmanlık alanları|uzmanlik alanlari|expertise|"
                             r"ilgi alanları|çalışma alanları)\s*:?\s*(.*)$", re.I)
HEX_ID = re.compile(r"[0-9a-f]{5,}", re.I)
STATE_CLASSES = {"active", "current", "selected", "open", "show", "first", "last", "odd", "even",
                 "visible", "hidden", "animated", "fadein", "fade", "wow", "in", "lazyloaded", "loaded"}
SOCIAL_HOSTS = ("linkedin.", "twitter.", "x.com", "facebook.", "instagram.", "youtube.", "scholar.google")
PLACES = {normalize(a) for a in CITIES} | {normalize(c) for c, _ in CITIES.values()} | {
    normalize(a) for a in COUNTRIES}
MIN_RECORDS = 3
MAX_LINES = 30000


@dataclass
class Record:
    name: str
    element: Tag
    title: str = ""
    role: str = ""  # stated on the name line itself ("Name – Role")
    inverted: bool = False
    block: Tag | None = None
    lines: list = field(default_factory=list)
    block_role: str = ""  # stated on another line of the record


def clean_classes(element):
    tokens = []
    for token in element.get("class", []) or []:
        lowered = token.lower()
        if lowered in STATE_CLASSES or HEX_ID.search(lowered) or re.search(r"\d{3,}", lowered):
            continue
        if re.search(r"(?:^|[-_])(?:post|item|node|row|entry|id|elementor-element)[-_]?\d+$", lowered):
            continue
        tokens.append(lowered)
    return ".".join(sorted(tokens)[:4])


def is_chrome(element):
    if element.name in ("nav", "footer", "aside", "header"):
        return True
    if element.get("role") in ("navigation", "banner", "contentinfo", "menu", "menubar"):
        return True
    words = []
    for token in (element.get("class", []) or []) + [element.get("id") or ""]:
        words += re.split(r"[-_\s]+", token.lower())
    return any(w in CHROME for w in words)


def boilerplate(element, total):
    """Navigation chrome that is safe to drop: never the main content (some sites put the page
    body in an <aside class="content">)."""
    if not is_chrome(element):
        return False
    if element.name in ("nav", "header", "footer"):
        return True  # explicit navigation markup is never the page body
    if element.find(["main", "article", "h1"]) is not None:
        return False
    return len(element.get_text(" ", strip=True)) <= 0.4 * total


def remove_chrome(body):
    """Drop navigation, menus, sidebars and footers, but never the main content itself."""
    total = len(body.get_text(" ", strip=True)) or 1
    for element in list(body.find_all(True)):
        if getattr(element, "decomposed", False) or element.parent is None:
            continue
        if boilerplate(element, total):
            element.decompose()


def strip_titles(text):
    titles = []
    while True:
        match = TITLE_PREFIX.match(text)
        if not match or not match.group(0).strip():
            break
        titles.append(match.group(0).strip())
        text = text[match.end():].lstrip(" ,")
    return text, " ".join(titles)


def split_trailing_role(words):
    """'Selim YAZICI Co-Founder' -> (['Selim', 'YAZICI'], 'Co-Founder')."""
    joiners = ("in", "of", "and", "ve", "&", "chief", "vice", "senior", "general", "genel", "yönetim",
               "kurulu", "kurul")
    for size in (4, 3, 2, 1):
        if len(words) - size < 2:
            continue
        tail = words[-size:]
        if any(known_given_name(w) for w in tail) or not ROLE_WORDS.search(" ".join(tail)):
            continue
        if all(ROLE_WORDS.search(w) or w.lower() in joiners for w in tail):
            return words[:-size], " ".join(tail)
    return words, ""


def plausible(name):
    """Reject capitalized phrases that are headings, roles, companies, places or inflected words."""
    if COMPANY_SUFFIX.search(name) or normalize(name) in PLACES or topic_phrase(name):
        return False  # a company, a place or a research topic ("Bilgisayarlı Görü")
    words = name.split()
    if (len(words[0]) >= 2 and words[0].isupper() and "." not in words[0]
            and any(not w.isupper() for w in words[1:])):
        return False  # "SGK Yenal Arslan", "UDHB Haberleşme Genel": an acronym, then other words
    caps = [len(w) >= 2 and w.isupper() and "." not in w for w in words]
    if any(caps[i] and not caps[i + 1] for i in range(1, len(words) - 1)):
        return False  # "Mehmet HAKLIDIR OECD One": words after an upper-case surname
    if normalize(words[-1]) in PLACES and not any(known_given_name(w) for w in words[:-1]):
        return False  # "NVIDIA Toronto", "Polytechnique Montréal": a unit and its city
    for word in words:
        if len(word) > 5 and not known_given_name(word) and re.search(r"(?:ics|ology|logy|tion|ical)$", word.lower()):
            return False  # "Medical Biophysics", "Information": field names, not surnames
        if CASE_SUFFIX.search(word) or word.count(".") >= 2:
            return False  # "Başkan'dan"; initialisms such as "V.S.T.S" are units, not names
        if known_given_name(word):
            continue
        if fold(word) in NON_NAME or ROLE_WORDS.fullmatch(word.strip(".,")):
            return False
    return True


def parse_line(text, person_name):
    """(name, title, role, inverted) when the line is shaped like a person's name, else None."""
    text = " ".join(text.replace("\xa0", " ").split())
    if not 3 <= len(text) <= 140 or "@" in text or "http" in text.lower():
        return None
    text = LEADER.sub("", text)
    role = ""
    if ":" in text:
        left, right = (p.strip() for p in text.split(":", 1))
        if not (left and right and len(left.split()) <= 5 and ROLE_WORDS.search(left)):
            return None
        role, text = left, right
    parts = [p.strip() for p in SEPARATOR.split(text) if p.strip()]
    if len(parts) > 1:
        # "Name – Role": only the first part may be the name, so a role line
        # ("Castrol - Küresel İş Mobilitesi Direktörü") never yields one.
        parsed = parse_line(parts[0], person_name)
        if not parsed:
            return None
        return parsed[0], parsed[1], parsed[2] or role or " – ".join(parts[1:])[:200], parsed[3]
    text = NICKNAME.sub(" ", text).strip()
    text, title = strip_titles(text)
    if ARABIC_LETTER.search(text):
        # "د.", "أ.د.": Arabic titles before the name, like "Dr." and "Prof. Dr.".
        words = text.split()
        while words and fold_arabic(words[0]) in HONORIFICS:
            title = (title + " " + words.pop(0)).strip()
        text = " ".join(words)
    previous = None
    while previous != text:
        previous = text
        text = DEGREE_SUFFIX.sub("", text).strip(" ,")
    inverted = False
    if text.count(",") == 1:
        left, right = (p.strip() for p in text.split(","))
        right, more_title = strip_titles(right)
        title = title or more_title
        if right and 1 <= len(left.split()) <= 2 and 1 <= len(right.split()) <= 3 and not ROLE_WORDS.search(right):
            text, inverted = f"{right} {left}", True
        elif not right:
            text = left
        else:
            return None
    words, trailing = split_trailing_role(text.split())
    if trailing and not title and not any(known_given_name(w) for w in words):
        return None  # "Occupational Safety Coordinator" is a role, not a name and a role
    role = role or trailing
    if normalize(" ".join(words)) in LINK_LABELS:
        return None
    name = person_name(" ".join(words))
    if not name or not plausible(name):
        return None
    return name, title, role, inverted


def joined_name(element):
    """Short inline pieces that form one name: <span>David</span> <span>Arnold</span> (hCard)."""
    pieces = [c for c in element.children if isinstance(c, Tag) and c.name in INLINE and c.get_text(strip=True)]
    if len(pieces) < 2 or element.find(lambda t: t.name not in INLINE):
        return None
    text = " ".join(element.get_text(" ", strip=True).split())
    return text if len(text) <= 80 and len(text.split()) <= 6 else None


def line_elements(root):
    """(text, element) for visible text nodes, in document order; a name split into inline
    pieces is one line of its container."""
    joined = set()
    for node in root.find_all(string=True):
        if isinstance(node, NOT_TEXT) or node.parent is None or node.parent.name in SKIP:
            continue
        container = node.parent.parent if node.parent.name in INLINE else None
        if container is not None and container.name in INLINE and id(container) not in joined:
            text = joined_name(container)
            if text:
                joined.add(id(container))
                yield text, container
                continue
        if container is not None and id(container) in joined:
            continue
        text = " ".join(str(node).split())
        if text:
            yield text, node.parent


def signature(element):
    leaf = element
    parts = []
    if leaf.name in INLINE:
        parts.append(f"{leaf.name}.{clean_classes(leaf)}")
        while leaf is not None and leaf.name in INLINE:
            leaf = leaf.parent
    depth = 0
    while leaf is not None and leaf.name not in ("body", "[document]") and depth < 6:
        if leaf.name not in INLINE:
            parts.append(f"{leaf.name}.{clean_classes(leaf)}")
            depth += 1
        leaf = leaf.parent
    return "/".join(parts)


def competitor(text):
    """A capitalized phrase that could stand where a name stands: not a label, title or role."""
    words = text.split()
    if not 2 <= len(words) <= 7 or len(text) > 90 or not words[0][:1].isupper():
        return False
    if text.endswith(":") or normalize(text) in LINK_LABELS or EMAIL.search(text) or PHONE.fullmatch(text):
        return False
    rest, title = strip_titles(text)
    if title and not rest.strip(" ,()"):
        return False
    # Sentences ("Responsible for internship") and research areas ("Image Processing")
    # describe a record; only name-shaped phrases compete with names.
    if any(not w[:1].isupper() and w not in ("de", "van", "von", "del", "da") for w in words):
        return False
    return not ROLE_WORDS.search(text) and not topic_phrase(text)


def block_text_lines(element, limit=60):
    lines = []
    for text, _ in line_elements(element):
        if text not in lines:
            lines.append(text)
        if len(lines) >= limit:
            break
    return lines


def assign_blocks(records):
    """Grow each record to the largest ancestor that holds no other record's name element."""
    owners = {}
    for index, record in enumerate(records):
        for parent in [record.element, *record.element.parents]:
            owners.setdefault(id(parent), set()).add(index)
    for index, record in enumerate(records):
        block = record.element
        for parent in record.element.parents:
            if parent.name in ("body", "[document]", "html") or owners.get(id(parent), set()) - {index}:
                break
            block = parent
        record.block = block
        if owners.get(id(record.element), set()) - {index}:
            # Several names in one element (lines split by <br>): own line plus what follows.
            texts = block_text_lines(record.element, 400)
            last = record.name.split()[-1].casefold()
            start = next((i for i, t in enumerate(texts) if last in t.casefold()), 0)
            lines = texts[start:start + 1]
            for text in texts[start + 1:start + 4]:
                if any(r is not record and r.name.split()[-1].casefold() in text.casefold() for r in records):
                    break
                lines.append(text)
            record.lines = lines
        else:
            record.lines = block_text_lines(block)
        record.block_role = own_role(record)


def own_role(record):
    """A title or role stated on a line of the record other than the name line."""
    last = normalize(record.name.split()[-1])
    for line in record.lines[:12]:
        stripped = line.strip(" ,()|")
        if not stripped or last in normalize(stripped) or EXPERTISE_LABEL.match(stripped):
            continue
        if re.match(r"^[^:]{1,40}:", stripped) and not ROLE_WORDS.match(stripped):
            continue  # a field label ("Oda:", "Research Areas:"), not a role
        rest, found = strip_titles(stripped)
        if found and not rest.strip(" ,()"):
            return found
        if len(stripped) <= 160 and ROLE_WORDS.search(stripped) and not re.search(r"\d{4}", stripped):
            return stripped
    return ""


def describe(record):
    """Title, role, expertise and public e-mail stated in the record's own block."""
    title, expertise = record.title, []
    for index, line in enumerate(record.lines):
        stripped = line.strip(" ,()|")
        label = EXPERTISE_LABEL.match(stripped)
        if label and label.group(1):
            expertise += [p.strip() for p in re.split(r"[;,]", label.group(1)) if 2 < len(p.strip()) <= 120]
        elif label:
            for item in record.lines[index + 1:index + 8]:
                if len(item) > 200 or re.match(r"^(?:research|interests?|e-?mail|phone|telefon|oda|office|"
                                               r"web|iş deneyimi|eğitim|bağlantı)", item, re.I):
                    break
                expertise += [p.strip() for p in re.split(r"[;,]", item) if 2 < len(p.strip()) <= 120]
        elif not title:
            rest, found = strip_titles(stripped)
            if found and not rest.strip(" ,()"):
                title = found
    role = record.role or record.block_role
    if role == title:
        role = ""
    email = None
    for anchor in record.block.select('a[href^="mailto:"]') if record.block is not None else []:
        email = anchor["href"][7:].split("?")[0].strip()
        break
    if not email:
        for line in record.lines:
            match = EMAIL.search(line)
            if match:
                email = re.sub(r"\s*[\[(]at[\])]\s*", "@", match.group(0), flags=re.I)
                break
    return title, role, list(dict.fromkeys(expertise))[:12], email


def profile_link(record, base_url):
    """A link from the record to the person's own page, if the block has one."""
    if record.block is None:
        return None
    key = re.sub(r"[^a-z]", "", normalize(record.name.split()[-1]))
    for anchor in record.block.select("a[href]"):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        target = urljoin(base_url, href)
        parts = urlsplit(target)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            continue
        if any(s in parts.netloc for s in SOCIAL_HOSTS):
            continue
        label = normalize(anchor.get_text(" ", strip=True))
        slug = re.sub(r"[^a-z]", "", normalize(unquote(parts.path + parts.netloc)))
        if label in LINK_LABELS - {"mail", "e-mail", "email", "e-posta", "eposta"} or (key and key in slug) \
                or (label and normalize(record.name) in label):
            return target[:2000]
    return None


def given(record):
    return any(known_given_name(w) for w in record.name.split()[:2]) or bool(ARABIC_LETTER.search(record.name))


def backed(record):
    """A title or a role on its own line: the record says what this person does."""
    return bool(record.title or record.block_role)


def accept(records, people_page):
    """Records of a list that shows person evidence; weak members are dropped."""
    unique = {normalize(r.name) for r in records}
    if len(unique) < 2:
        return []
    named = sum(map(given, records)) / len(records)
    # A role line that every record repeats ("Founder Contacts" under each company of a startup
    # directory) is a label, not a statement about each person; titles ("Prof. Dr.") still count.
    roles = [normalize(r.block_role) for r in records if r.block_role and not r.title]
    common = max(set(roles), key=roles.count) if roles else None
    label = common is not None and roles.count(common) >= max(MIN_RECORDS, 0.8 * len(roles))

    def stated(record):
        # A title, a role written before the name ("Üye: Ad Soyad") or a role line that is not a
        # label. "Arçelik Pazarlama - Genel Müdür" is a company and a role, so a role after a dash
        # is not evidence that the first part names a person.
        line = next((x for x in record.lines if record.name.split()[-1] in x), "")
        before = bool(record.role) and line.lstrip(" -•").startswith(record.role) and ":" in line
        return bool(record.title or before
                    or (record.block_role and not (label and normalize(record.block_role) == common)))

    titled = sum(map(stated, records)) / len(records)
    if label and named < 0.3 and titled < 0.3:
        return []
    if people_page:
        enough = len(unique) >= MIN_RECORDS or titled >= 0.99
        trusted = named >= 0.15 or titled >= 0.3
    else:
        # An article's infobox or a news site's columnist strip also repeats a few names, but
        # rarely with a role line for each.
        enough = len(unique) >= MIN_RECORDS + 1 or (len(unique) >= MIN_RECORDS and titled >= 0.66)
        trusted = named >= 0.5 or titled >= 0.5
    if not (enough and trusted):
        return []
    # Records that hold nothing but the name ("Random Heading", "Former Academics" as bare
    # links) carry no evidence besides the name itself.
    bare = sum(len(r.lines) <= 1 for r in records) / len(records)
    if bare >= 0.5 and named < 0.6:
        return []
    # Members need their own evidence; in a list of mostly known names a record whose own
    # name is unknown may stay when it also has a record of its own (more than the name).
    return [r for r in records if given(r) or stated(r) or (named >= 0.6 and len(r.lines) > 1)]


def rescue_siblings(body, records, person_name):
    """Cards of the same list whose name sits in another tag (a lead's h6 among h5 cards)."""
    counts = {}
    for record in records:
        for token in set(record.block.get("class", []) or []):
            counts[token] = counts.get(token, 0) + 1
    tokens = sorted(t for t, n in counts.items() if n >= max(2, 0.6 * len(records))
                    and not HEX_ID.search(t) and t.lower() not in STATE_CLASSES)
    if not tokens:
        return []
    known = {id(r.block) for r in records}
    names = {normalize(r.name) for r in records}
    found = []
    for element in body.find_all(class_=tokens[0])[:300]:
        if id(element) in known or any(id(p) in known for p in element.parents) or element.find(
                lambda tag: id(tag) in known):
            continue
        for text, line_element in line_elements(element):
            parsed = parse_line(text, person_name)
            if parsed and normalize(parsed[0]) not in names:
                record = Record(parsed[0], line_element, parsed[1], parsed[2], parsed[3], block=element)
                record.lines = block_text_lines(element)
                record.block_role = own_role(record)
                found.append(record)
                names.add(normalize(parsed[0]))
                break
    return found


def headed_people(body, person_name, taken):
    """On a people page: a heading that is a name, followed by a line stating a role."""
    found = []
    # The line after every heading of the page: a line repeated under many headings is a label.
    after = [h.find_next_sibling(["p", "div", "span", "h4", "h5", "h6"]) for h in body.find_all(list(HEADINGS))[:300]]
    repeated = [normalize(a.get_text(" ", strip=True)) for a in after if a is not None]
    labels = {line for line in set(repeated) if repeated.count(line) >= MIN_RECORDS}
    for heading in body.find_all(list(HEADINGS))[:300]:
        text = heading.get_text(" ", strip=True)
        parsed = parse_line(text, person_name) if len(text) <= 120 else None
        if not parsed or normalize(parsed[0]) in taken:
            continue
        following = heading.find_next_sibling(["p", "div", "span", "h4", "h5", "h6"])
        line = following.get_text(" ", strip=True) if following else ""
        record = Record(parsed[0], heading, parsed[1], parsed[2], parsed[3], block=heading.parent)
        record.lines = [text] + ([line] if line and len(line) <= 300 else [])
        record.block_role = own_role(record)
        if normalize(record.block_role) in labels:
            record.block_role = ""
        # A title ("Prof. Dr.") or a role line says what the person does.
        if (given(record) or record.title) and (record.block_role or record.title):
            found.append(record)
            taken.add(normalize(parsed[0]))
    return found


def find_records(body, person_name, page_text_hint="", deadline=None, clock=None):
    """Lists of people in a cleaned <body>: [(signature, records)], [] when nobody is listed."""
    groups, totals = {}, {}
    for count, (text, element) in enumerate(line_elements(body)):
        if count > MAX_LINES or (deadline and clock and clock() > deadline):
            break
        key = signature(element)
        parsed = parse_line(text, person_name)
        if parsed:
            groups.setdefault(key, []).append(Record(parsed[0], element, parsed[1], parsed[2], parsed[3]))
            totals[key] = totals.get(key, 0) + 1
        elif competitor(text):
            totals[key] = totals.get(key, 0) + 1
    people_page = bool(PEOPLE_PAGE.search(page_text_hint))
    accepted, taken = [], set()
    for key, records in groups.items():
        if len(records) / totals[key] < 0.5:
            continue
        assign_blocks(records)
        kept = accept(records, people_page)
        if kept:
            kept += rescue_siblings(body, kept, person_name)
            accepted.append((key, kept))
            taken |= {normalize(r.name) for r in kept}
    if people_page:
        extra = headed_people(body, person_name, taken)
        if extra:
            accepted.append(("headed", extra))
    return accepted
