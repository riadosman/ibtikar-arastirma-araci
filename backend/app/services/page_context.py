"""Who owns a page and where it is: the organization and city of a staff or team list.

A university's staff page rarely repeats the city next to each name, but its title names
the institution ("Akademik Kadro - TOBB ETÜ") and its footer gives the address ("Ankara").
People listed there work at that organization and place. These facts are inferred from the
page, never stated per person, so callers must label them as such (basis "page").
"""

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.services.search_quality import normalize

# City aliases (normalized) -> (display name, country). Ambiguous words ("Aydın" is also a
# given name, "Van" a particle) are trusted only in an address context, never in a title.
CITIES = {
    "istanbul": ("İstanbul", "Türkiye"), "stambul": ("İstanbul", "Türkiye"), "إسطنبول": ("İstanbul", "Türkiye"),
    "اسطنبول": ("İstanbul", "Türkiye"), "ankara": ("Ankara", "Türkiye"), "أنقرة": ("Ankara", "Türkiye"),
    "izmir": ("İzmir", "Türkiye"), "bursa": ("Bursa", "Türkiye"), "antalya": ("Antalya", "Türkiye"),
    "konya": ("Konya", "Türkiye"), "adana": ("Adana", "Türkiye"), "gaziantep": ("Gaziantep", "Türkiye"),
    "kocaeli": ("Kocaeli", "Türkiye"), "gebze": ("Kocaeli", "Türkiye"), "izmit": ("Kocaeli", "Türkiye"),
    "eskisehir": ("Eskişehir", "Türkiye"), "kayseri": ("Kayseri", "Türkiye"), "mersin": ("Mersin", "Türkiye"),
    "samsun": ("Samsun", "Türkiye"), "trabzon": ("Trabzon", "Türkiye"), "erzurum": ("Erzurum", "Türkiye"),
    "diyarbakir": ("Diyarbakır", "Türkiye"), "sakarya": ("Sakarya", "Türkiye"), "malatya": ("Malatya", "Türkiye"),
    "manisa": ("Manisa", "Türkiye"), "denizli": ("Denizli", "Türkiye"), "tekirdag": ("Tekirdağ", "Türkiye"),
    "edirne": ("Edirne", "Türkiye"), "canakkale": ("Çanakkale", "Türkiye"), "balikesir": ("Balıkesir", "Türkiye"),
    "elazig": ("Elazığ", "Türkiye"), "sivas": ("Sivas", "Türkiye"), "hatay": ("Hatay", "Türkiye"),
    "sanliurfa": ("Şanlıurfa", "Türkiye"), "kahramanmaras": ("Kahramanmaraş", "Türkiye"),
    "afyonkarahisar": ("Afyonkarahisar", "Türkiye"), "isparta": ("Isparta", "Türkiye"), "mugla": ("Muğla", "Türkiye"),
    "zonguldak": ("Zonguldak", "Türkiye"), "karabuk": ("Karabük", "Türkiye"), "duzce": ("Düzce", "Türkiye"),
    "bolu": ("Bolu", "Türkiye"), "rize": ("Rize", "Türkiye"), "ordu": ("Ordu", "Türkiye"), "aydin": ("Aydın", "Türkiye"),
    "van": ("Van", "Türkiye"), "batman": ("Batman", "Türkiye"), "nigde": ("Niğde", "Türkiye"), "nevsehir": ("Nevşehir", "Türkiye"),
    "kirikkale": ("Kırıkkale", "Türkiye"), "kirsehir": ("Kırşehir", "Türkiye"), "yozgat": ("Yozgat", "Türkiye"),
    "corum": ("Çorum", "Türkiye"), "tokat": ("Tokat", "Türkiye"), "amasya": ("Amasya", "Türkiye"), "kutahya": ("Kütahya", "Türkiye"),
    "usak": ("Uşak", "Türkiye"), "bilecik": ("Bilecik", "Türkiye"), "yalova": ("Yalova", "Türkiye"), "mardin": ("Mardin", "Türkiye"),
    "osmaniye": ("Osmaniye", "Türkiye"), "aksaray": ("Aksaray", "Türkiye"), "karaman": ("Karaman", "Türkiye"),
    "kastamonu": ("Kastamonu", "Türkiye"), "giresun": ("Giresun", "Türkiye"), "erzincan": ("Erzincan", "Türkiye"),
    "kars": ("Kars", "Türkiye"), "agri": ("Ağrı", "Türkiye"), "artvin": ("Artvin", "Türkiye"), "sinop": ("Sinop", "Türkiye"),
    "kirklareli": ("Kırklareli", "Türkiye"), "burdur": ("Burdur", "Türkiye"), "adiyaman": ("Adıyaman", "Türkiye"),
    "dubai": ("Dubai", "BAE"), "دبي": ("Dubai", "BAE"), "abu dhabi": ("Abu Dabi", "BAE"), "أبوظبي": ("Abu Dabi", "BAE"),
    "sharjah": ("Şarika", "BAE"), "riyadh": ("Riyad", "Suudi Arabistan"), "riyad": ("Riyad", "Suudi Arabistan"),
    "الرياض": ("Riyad", "Suudi Arabistan"), "jeddah": ("Cidde", "Suudi Arabistan"), "cidde": ("Cidde", "Suudi Arabistan"),
    "جدة": ("Cidde", "Suudi Arabistan"), "dammam": ("Dammam", "Suudi Arabistan"), "doha": ("Doha", "Katar"),
    "الدوحة": ("Doha", "Katar"), "kuwait city": ("Kuveyt", "Kuveyt"), "manama": ("Manama", "Bahreyn"),
    "muscat": ("Maskat", "Umman"), "cairo": ("Kahire", "Mısır"), "kahire": ("Kahire", "Mısır"), "القاهرة": ("Kahire", "Mısır"),
    "amman": ("Amman", "Ürdün"), "عمان": ("Amman", "Ürdün"), "beirut": ("Beyrut", "Lübnan"), "beyrut": ("Beyrut", "Lübnan"),
    "baghdad": ("Bağdat", "Irak"), "bagdat": ("Bağdat", "Irak"), "erbil": ("Erbil", "Irak"), "tehran": ("Tahran", "İran"),
    "baku": ("Bakü", "Azerbaycan"), "tbilisi": ("Tiflis", "Gürcistan"), "london": ("Londra", "Birleşik Krallık"),
    "londra": ("Londra", "Birleşik Krallık"), "cambridge": ("Cambridge", ""), "oxford": ("Oxford", "Birleşik Krallık"),
    "manchester": ("Manchester", "Birleşik Krallık"), "edinburgh": ("Edinburgh", "Birleşik Krallık"),
    "paris": ("Paris", "Fransa"), "berlin": ("Berlin", "Almanya"), "munich": ("Münih", "Almanya"), "munchen": ("Münih", "Almanya"),
    "munih": ("Münih", "Almanya"), "hamburg": ("Hamburg", "Almanya"), "frankfurt": ("Frankfurt", "Almanya"),
    "amsterdam": ("Amsterdam", "Hollanda"), "rotterdam": ("Rotterdam", "Hollanda"), "brussels": ("Brüksel", "Belçika"),
    "vienna": ("Viyana", "Avusturya"), "wien": ("Viyana", "Avusturya"), "zurich": ("Zürih", "İsviçre"),
    "geneva": ("Cenevre", "İsviçre"), "madrid": ("Madrid", "İspanya"), "barcelona": ("Barselona", "İspanya"),
    "rome": ("Roma", "İtalya"), "milan": ("Milano", "İtalya"), "stockholm": ("Stockholm", "İsveç"),
    "copenhagen": ("Kopenhag", "Danimarka"), "oslo": ("Oslo", "Norveç"), "helsinki": ("Helsinki", "Finlandiya"),
    "warsaw": ("Varşova", "Polonya"), "prague": ("Prag", "Çekya"), "budapest": ("Budapeşte", "Macaristan"),
    "athens": ("Atina", "Yunanistan"), "sofia": ("Sofya", "Bulgaristan"), "bucharest": ("Bükreş", "Romanya"),
    "moscow": ("Moskova", "Rusya"), "kyiv": ("Kiev", "Ukrayna"), "new york": ("New York", "ABD"),
    "boston": ("Boston", "ABD"), "san francisco": ("San Francisco", "ABD"), "los angeles": ("Los Angeles", "ABD"),
    "chicago": ("Chicago", "ABD"), "seattle": ("Seattle", "ABD"), "pittsburgh": ("Pittsburgh", "ABD"),
    "durham": ("Durham", ""), "stanford": ("Stanford", "ABD"), "toronto": ("Toronto", "Kanada"),
    "montreal": ("Montreal", "Kanada"), "vancouver": ("Vancouver", "Kanada"), "singapore": ("Singapur", "Singapur"),
}
AMBIGUOUS = {"aydin", "van", "batman", "ordu", "agri", "kars", "sinop", "cambridge", "durham", "sofia",
             "stanford", "عمان"}
COUNTRIES = {
    "turkiye": "Türkiye", "turkey": "Türkiye", "تركيا": "Türkiye", "germany": "Almanya", "deutschland": "Almanya",
    "united kingdom": "Birleşik Krallık", "england": "Birleşik Krallık", "france": "Fransa", "usa": "ABD",
    "united states": "ABD", "canada": "Kanada", "united arab emirates": "BAE", "uae": "BAE",
    "saudi arabia": "Suudi Arabistan", "qatar": "Katar", "egypt": "Mısır", "netherlands": "Hollanda",
    "italy": "İtalya", "spain": "İspanya", "switzerland": "İsviçre", "austria": "Avusturya", "belgium": "Belçika",
    "sweden": "İsveç", "norway": "Norveç", "denmark": "Danimarka", "finland": "Finlandiya", "poland": "Polonya",
    "greece": "Yunanistan", "israel": "İsrail", "iran": "İran", "iraq": "Irak", "jordan": "Ürdün",
    "lebanon": "Lübnan", "kuwait": "Kuveyt", "bahrain": "Bahreyn", "oman": "Umman", "morocco": "Fas",
    "tunisia": "Tunus", "algeria": "Cezayir", "pakistan": "Pakistan", "india": "Hindistan", "china": "Çin",
    "japan": "Japonya", "korea": "Kore", "singapore": "Singapur", "australia": "Avustralya",
    "azerbaijan": "Azerbaycan", "russia": "Rusya", "ukraine": "Ukrayna", "ireland": "İrlanda",
}
TLD_COUNTRY = {"tr": "Türkiye", "de": "Almanya", "uk": "Birleşik Krallık", "fr": "Fransa", "ca": "Kanada",
               "ae": "BAE", "sa": "Suudi Arabistan", "qa": "Katar", "eg": "Mısır", "nl": "Hollanda", "edu": "ABD"}
TITLE_SEPARATOR = re.compile(r"\s+[|–—«»·:]\s+|\s+-\s+|\s*\|\s*")
# Title segments that name the page, not its owner.
GENERIC_SEGMENT = re.compile(
    r"^(?:home|anasayfa|ana sayfa|people|our people|team|our team|the team|meet the team|staff|faculty|"
    r"faculty members|academic staff|faculty directory|directory|members|leadership|management|board|"
    r"board of directors|speakers|jury|founders|about|about us|contact|ekip|ekibimiz|ekibimizi tanıyın|"
    r"kadro|akademik kadro|öğretim üyeleri|ogretim uyeleri|yönetim|yonetim|yönetim kurulu|yonetim kurulu|"
    r"yönetim ekibi|kurucular|kurucu üyelerimiz|konuşmacılar|konusmacilar|jüri|hakkımızda|hakkimizda|"
    r"iletişim|iletisim|personel|akademik personel|academic personnel|faculty by name|staff list|team list)$",
    re.I,
)
# A page name glued to the owner without a separator ("Akademik Kadro İstanbul Topkapı Üniversitesi").
LEADING_GENERIC = re.compile(
    r"^(?:akademik kadro|öğretim üyeleri|akademik personel|ekibimiz|ekip|yönetim kurulu|yönetim ekibi|"
    r"our team|team|faculty members|faculty|academic staff|people|staff|speakers|konuşmacılar)\s+(?=\S)",
    re.I)
ADDRESS_HINT = re.compile(r"address|adres|contact|iletisim|footer|location|konum|kunye|imprint|impressum", re.I)
ORG_TYPES = ("Organization", "CollegeOrUniversity", "EducationalOrganization", "Corporation",
             "GovernmentOrganization", "NGO", "ResearchOrganization", "LocalBusiness")


@dataclass
class PageContext:
    organization: str | None = None
    organization_evidence: str = ""
    city: str | None = None
    country: str | None = None
    location_evidence: str = ""
    cities_seen: dict = field(default_factory=dict)


def host_words(url):
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return [label for label in host.split(".") if len(label) >= 3]


def _ld_nodes(soup):
    for script in soup.select('script[type="application/ld+json"]')[:30]:
        try:
            pending = [json.loads(script.string or script.get_text())]
        except (ValueError, RecursionError):
            continue
        visited = 0
        while pending and visited < 500:
            node = pending.pop()
            visited += 1
            if isinstance(node, list):
                pending.extend(node)
            elif isinstance(node, dict):
                yield node
                pending.extend(v for v in node.values() if isinstance(v, (dict, list)))


def organization_from(soup, url, title):
    hosts = host_words(url)

    def on_host(text):
        words = [normalize(w) for w in re.findall(r"\w+", text)]
        return any(len(w) >= 3 and any(w in h for h in hosts) for w in words)

    for node in _ld_nodes(soup):
        kinds = node.get("@type", [])
        kinds = kinds if isinstance(kinds, list) else [kinds]
        name = node.get("name")
        if any(k in ORG_TYPES for k in kinds) and isinstance(name, str) and 2 <= len(name) <= 150:
            if on_host(name):
                return name.strip(), "Sayfanın yapısal verisi (Organization)"
    meta = soup.find("meta", attrs={"property": "og:site_name"})
    site = (meta.get("content") or "").strip() if meta else ""
    if 2 <= len(site) <= 120 and not GENERIC_SEGMENT.match(site):
        return site, "Sayfanın site adı (og:site_name)"
    segments = [LEADING_GENERIC.sub("", s.strip()).strip() for s in TITLE_SEPARATOR.split(title or "")]
    useful = [s for s in segments if s and not GENERIC_SEGMENT.match(s) and len(s) <= 120]
    for segment in reversed(useful):
        if on_host(segment):
            return segment, "Sayfa başlığı"
    return None, ""


def _cities_in(text, allow_ambiguous):
    found = {}
    folded = normalize(text)
    for alias, place in CITIES.items():
        if alias in AMBIGUOUS and not allow_ambiguous:
            continue
        key = normalize(alias)
        count = len(re.findall(r"(?<!\w)" + re.escape(key) + r"(?!\w)", folded))
        if count:
            found[place] = found.get(place, 0) + count
    return found


def page_context(soup, url, title=""):
    """Organization and city of the page owner; call before navigation and footers are removed."""
    context = PageContext()
    context.organization, context.organization_evidence = organization_from(soup, url, title)
    scores = {}
    evidence = {}

    def add(found, weight, label):
        for place, count in found.items():
            scores[place] = scores.get(place, 0) + weight * count
            evidence.setdefault(place, label)

    for node in _ld_nodes(soup):
        address = node.get("address")
        locality = address.get("addressLocality") if isinstance(address, dict) else address
        if isinstance(locality, str):
            add(_cities_in(locality, True), 5, "Sayfanın yapısal adres verisi")
    blocks = soup.find_all(["address", "footer"])[:10]
    blocks += [el for el in soup.find_all(attrs={"class": ADDRESS_HINT})[:20]]
    blocks += [el for el in soup.find_all(attrs={"id": ADDRESS_HINT})[:10]]
    for block in blocks:
        text = block.get_text(" ", strip=True)[:3000]
        add(_cities_in(text, True), 2, "Sayfanın adres/iletişim bölümü")
    if context.organization:
        add(_cities_in(context.organization, False), 3, "Kurum adı")
    add(_cities_in(title or "", False), 1, "Sayfa başlığı")
    context.cities_seen = {f"{city}": score for (city, _), score in scores.items()}
    if scores:
        (city, country), _ = max(scores.items(), key=lambda kv: kv[1])
        context.city, context.country = city, country or None
        context.location_evidence = evidence[(city, country)]
    if not context.country:
        tld = (urlsplit(url).hostname or "").rsplit(".", 1)[-1]
        if tld in TLD_COUNTRY and tld != "edu":
            context.country = TLD_COUNTRY[tld]
            context.location_evidence = context.location_evidence or "Alan adı uzantısı"
    return context


def place_matches(requested, *values):
    """Requested location found in any of the given place strings (city or country)."""
    wanted = normalize(requested).strip()
    if not wanted:
        return None
    aliases = {wanted}
    for alias, (city, country) in CITIES.items():
        if normalize(alias) == wanted or normalize(city) == wanted:
            aliases |= {normalize(city), normalize(alias)}
    for alias, country in COUNTRIES.items():
        if normalize(alias) == wanted or normalize(country) == wanted:
            aliases |= {normalize(country), normalize(alias)}
    text = normalize(" ".join(v for v in values if v))
    if not text:
        return None
    return any(re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", text) for a in aliases if a)
