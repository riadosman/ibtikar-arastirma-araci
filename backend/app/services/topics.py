"""Research topics and places in the six search languages.

A brief says "AI and Math" or "görüntü işleme"; pages say "Yapay Zeka", "Computer Vision",
"Artificial Intelligence and Data Engineering". Each topic lists its names per language
(tr, en, de, fr, es, ar) for queries, plus extra aliases and related terms for matching. The
list is small on purpose: an unknown topic is searched and matched verbatim.
"""

from dataclasses import dataclass, field

from app.services.search_quality import normalize

LANGUAGES = ("tr", "en", "de", "fr", "es", "ar")


@dataclass(frozen=True)
class Topic:
    key: str
    names: tuple  # one name per LANGUAGES entry, used in queries
    aliases: tuple = ()  # other spellings and abbreviations, used for matching only
    related: tuple = ()  # narrower or sibling terms that also count as evidence

    def name(self, language):
        return self.names[LANGUAGES.index(language) if language in LANGUAGES else 1]

    def terms(self):
        return {t for t in (*self.names, *self.aliases) if t}


TOPICS = [
    Topic("ai", ("yapay zekâ", "artificial intelligence", "künstliche Intelligenz", "intelligence artificielle",
                 "inteligencia artificial", "الذكاء الاصطناعي"),
          ("ai", "yz", "yapay zeka", "a.i."),
          # Subfields are evidence of the field: a computer vision researcher works in AI.
          ("machine learning", "makine öğrenmesi", "deep learning", "derin öğrenme", "computer vision",
           "bilgisayarlı görü", "görüntü işleme", "natural language processing", "doğal dil işleme",
           "neural networks", "yapay sinir ağları", "pattern recognition", "örüntü tanıma",
           "reinforcement learning", "large language models", "büyük dil modelleri", "generative ai",
           "üretken yapay zeka")),
    Topic("ml", ("makine öğrenmesi", "machine learning", "maschinelles Lernen", "apprentissage automatique",
                 "aprendizaje automático", "تعلم الآلة"),
          ("makine öğrenimi", "deep learning", "derin öğrenme"), ("artificial intelligence", "yapay zeka")),
    Topic("cv", ("bilgisayarlı görü", "computer vision", "Computer Vision", "vision par ordinateur",
                 "visión por computador", "رؤية الحاسوب"),
          ("görüntü işleme", "goruntu isleme", "image processing", "bilgisayarli goru", "machine vision"),
          ("image analysis", "görüntü analizi", "pattern recognition", "örüntü tanıma")),
    Topic("nlp", ("doğal dil işleme", "natural language processing", "Verarbeitung natürlicher Sprache",
                  "traitement automatique des langues", "procesamiento del lenguaje natural",
                  "معالجة اللغات الطبيعية"),
          ("nlp", "dogal dil isleme", "computational linguistics", "hesaplamalı dilbilim"),
          ("large language models", "büyük dil modelleri", "llm", "text mining", "metin madenciliği")),
    Topic("data", ("veri bilimi", "data science", "Data Science", "science des données", "ciencia de datos",
                   "علم البيانات"),
          ("veri bilimci", "data scientist", "data analytics", "veri analitiği", "büyük veri", "big data"),
          ("data mining", "veri madenciliği")),
    Topic("robotics", ("robotik", "robotics", "Robotik", "robotique", "robótica", "الروبوتات"),
          ("robot", "otonom sistemler", "autonomous systems")),
    Topic("security", ("siber güvenlik", "cybersecurity", "Cybersicherheit", "cybersécurité", "ciberseguridad",
                       "الأمن السيبراني"),
          ("cyber security", "bilgi güvenliği", "information security", "network security", "ağ güvenliği"),
          ("cryptography", "kriptografi")),
    Topic("fintech", ("finansal teknoloji", "fintech", "Fintech", "fintech", "fintech", "التكنولوجيا المالية"),
          ("fintek", "financial technology", "dijital bankacılık", "digital banking", "ödeme sistemleri")),
    Topic("blockchain", ("blokzincir", "blockchain", "Blockchain", "blockchain", "blockchain", "سلسلة الكتل"),
          ("blok zincir", "web3", "kripto", "crypto")),
    Topic("iot", ("nesnelerin interneti", "internet of things", "Internet der Dinge", "internet des objets",
                  "internet de las cosas", "إنترنت الأشياء"), ("iot",)),
    Topic("cloud", ("bulut bilişim", "cloud computing", "Cloud Computing", "informatique en nuage",
                    "computación en la nube", "الحوسبة السحابية"), ("cloud",)),
    Topic("software", ("yazılım mühendisliği", "software engineering", "Softwaretechnik", "génie logiciel",
                       "ingeniería de software", "هندسة البرمجيات"),
          ("yazılım geliştirme", "software development", "yazilim")),
    Topic("cs", ("bilgisayar mühendisliği", "computer science", "Informatik", "informatique", "informática",
                 "علوم الحاسوب"),
          ("bilgisayar bilimleri", "computer engineering", "bilgisayar muhendisligi", "bilişim", "informatics")),
    Topic("ee", ("elektrik-elektronik mühendisliği", "electrical engineering", "Elektrotechnik", "génie électrique",
                 "ingeniería eléctrica", "الهندسة الكهربائية"),
          ("elektrik elektronik", "electrical and electronics engineering", "electronics", "elektronik")),
    Topic("math", ("matematik", "mathematics", "Mathematik", "mathématiques", "matemáticas", "الرياضيات"),
          ("math", "maths", "applied mathematics", "uygulamalı matematik"), ("statistics", "istatistik")),
    Topic("stats", ("istatistik", "statistics", "Statistik", "statistique", "estadística", "الإحصاء"),
          ("statistical", "biostatistics")),
    Topic("physics", ("fizik", "physics", "Physik", "physique", "física", "الفيزياء")),
    Topic("bio", ("biyoteknoloji", "biotechnology", "Biotechnologie", "biotechnologie", "biotecnología",
                  "التكنولوجيا الحيوية"), ("biyoinformatik", "bioinformatics", "genomics", "genomik")),
    Topic("health", ("sağlık teknolojileri", "health technology", "Gesundheitstechnologie", "technologies de la santé",
                     "tecnología sanitaria", "تكنولوجيا الصحة"),
          ("dijital sağlık", "digital health", "tıp", "medicine", "healthcare", "medical")),
    Topic("food", ("gastronomi", "gastronomy", "Gastronomie", "gastronomie", "gastronomía", "فن الطهي"),
          ("mutfak", "culinary", "cuisine", "aşçılık", "culinary arts")),
    Topic("startup", ("girişimcilik", "entrepreneurship", "Unternehmertum", "entrepreneuriat", "emprendimiento",
                      "ريادة الأعمال"),
          ("girişim", "startup", "start-up", "girisim", "girişimci", "entrepreneur", "venture")),
    Topic("tech", ("teknoloji", "technology", "Technologie", "technologie", "tecnología", "تكنولوجيا"),
          ("information technology", "bilişim", "bilisim", "tech")),
    Topic("energy", ("enerji", "energy", "Energie", "énergie", "energía", "الطاقة"),
          ("yenilenebilir enerji", "renewable energy")),
    Topic("edtech", ("eğitim teknolojileri", "educational technology", "Bildungstechnologie",
                     "technologies éducatives", "tecnología educativa", "تكنولوجيا التعليم"),
          ("edtech", "eğitimde yapay zeka", "ai in education")),
    Topic("games", ("oyun geliştirme", "game development", "Spieleentwicklung", "développement de jeux",
                    "desarrollo de videojuegos", "تطوير الألعاب"), ("oyun", "gaming", "game design")),
    Topic("defense", ("savunma sanayii", "defense industry", "Verteidigungsindustrie", "industrie de défense",
                      "industria de defensa", "الصناعات الدفاعية"),
          ("savunma sanayi", "havacılık", "aerospace", "uzay")),
    Topic("quantum", ("kuantum hesaplama", "quantum computing", "Quantencomputing", "informatique quantique",
                      "computación cuántica", "الحوسبة الكمومية"), ("kuantum", "quantum")),
]
# Query spelling of common cities per language; matching uses page_context.CITIES.
CITY_NAMES = {
    "istanbul": ("İstanbul", "Istanbul", "Istanbul", "Istanbul", "Estambul", "إسطنبول"),
    "ankara": ("Ankara", "Ankara", "Ankara", "Ankara", "Ankara", "أنقرة"),
    "izmir": ("İzmir", "Izmir", "Izmir", "Izmir", "Esmirna", "إزمير"),
    "dubai": ("Dubai", "Dubai", "Dubai", "Dubaï", "Dubái", "دبي"),
    "riyadh": ("Riyad", "Riyadh", "Riad", "Riyad", "Riad", "الرياض"),
    "doha": ("Doha", "Doha", "Doha", "Doha", "Doha", "الدوحة"),
    "cairo": ("Kahire", "Cairo", "Kairo", "Le Caire", "El Cairo", "القاهرة"),
    "london": ("Londra", "London", "London", "Londres", "Londres", "لندن"),
    "berlin": ("Berlin", "Berlin", "Berlin", "Berlin", "Berlín", "برلين"),
    "paris": ("Paris", "Paris", "Paris", "Paris", "París", "باريس"),
}
CITY_ALIASES = {"istanbul": "istanbul", "stambul": "istanbul", "اسطنبول": "istanbul", "riyad": "riyadh",
                "riyadh": "riyadh", "kahire": "cairo", "cairo": "cairo", "londra": "london"}


# Fields so broad that the requested role already implies them ("CTO" in "technology").
BROAD = {"tech"}
# Abbreviations that name a topic in a brief but are ordinary words in page text.
BRIEF_ONLY = {"it": "tech", "ki": "ai", "ml": "ml", "bt": "tech"}


def find_topic(text):
    """The topic a phrase names, or None."""
    key = normalize(text).strip()
    if key in BRIEF_ONLY:
        return next(t for t in TOPICS if t.key == BRIEF_ONLY[key])
    for topic in TOPICS:
        if key in {normalize(t) for t in topic.terms()}:
            return topic
    return None


TOPIC_PHRASES = {normalize(term) for topic in TOPICS for term in (*topic.terms(), *topic.related) if term}


def topic_phrase(text):
    """The phrase is a research area name ("Data Mining", "Bilgisayarlı Görü"), not a person."""
    return normalize(text).strip() in TOPIC_PHRASES


@dataclass
class TopicTerm:
    """A requested topic: its query name per language and every term that counts as a match."""
    label: str
    topic: Topic | None = None
    match_terms: set = field(default_factory=set)

    def query(self, language):
        return self.topic.name(language) if self.topic else self.label

    def other(self, language):
        """The same topic in a second language (English for most, Turkish for English briefs)."""
        if not self.topic:
            return None
        second = "tr" if language == "en" else "en"
        name = self.topic.name(second)
        return name if normalize(name) != normalize(self.query(language)) else None


def contained_topics(label):
    """Known topics named inside a longer phrase: "yapay zeka girişim" -> AI and startups."""
    import re

    text = normalize(label)
    return [topic for topic in TOPICS
            if any(len(normalize(t)) > 2 and re.search(r"(?<!\w)" + re.escape(normalize(t)), text)
                   for t in topic.terms())]


def topic_term(label):
    topic = find_topic(label)
    terms = {label}
    if topic:
        terms |= topic.terms() | set(topic.related)
    else:
        # Queries keep the brief's own phrase; matching also accepts the topics it contains.
        for inner in contained_topics(label):
            terms |= inner.terms() | set(inner.related)
    return TopicTerm(label, topic, {normalize(t) for t in terms if t})


def city_name(location, language):
    key = normalize(location).strip()
    key = CITY_ALIASES.get(key, key)
    names = CITY_NAMES.get(key)
    if not names:
        return location.strip()
    return names[LANGUAGES.index(language) if language in LANGUAGES else 1]
