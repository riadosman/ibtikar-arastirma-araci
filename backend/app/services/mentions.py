"""People named in running text: news about an event, a jury, a panel or a speaker.

Articles rarely lay people out as records; they write "jüri üyeleri Somer Sivrioğlu, Mehmet
Yalçınkaya ve Danilo Zanna" or "Dr. Öğr. Üyesi Emrah Köksal Sezgin'in yürüttüğü". Three
anchors are accepted, each with the sentence kept as evidence:

- an academic title right before the name ("Prof. Dr. Ayşe Kaya"),
- a professional role word right before or after the name ("şef Mehmet Yalçınkaya",
  "Ali Kavak, co-founder of ..."), only with a known given name,
- a plural role followed by a list of names ("konuşmacılar: A, B ve C").

A capitalized pair with no anchor is never taken: running text is full of places, brands
and titles. Whether the stated role is the one requested is decided later.
"""

import re

from app.services.given_names import known_given_name
from app.services.record_blocks import TITLE_TOKENS, plausible

CAP = r"[A-ZÇĞİÖŞÜ][a-zçğıöşüâîûéèáíóúñäë]+(?:-[A-ZÇĞİÖŞÜ][a-zçğıöşüâîûéèáíóúñäë]+)?"
UPPER = r"[A-ZÇĞİÖŞÜ]{2,}"
# A word followed by ":" is a field label ("Oda:"), never part of a name. Names never span
# lines: callers pass text with one line per block element.
WORD = rf"(?:{CAP}|{UPPER})(?![:\w])"
NAME = rf"{WORD}(?:[ \t]+{WORD}){{1,3}}"
SUFFIX = r"(?:['’][a-zçğıöşü]{1,5})?"
# Title and role words in any case; the name itself must be capitalized.
TITLE = r"(?i:" + "|".join(TITLE_TOKENS[:23]) + r")"
ROLE_BEFORE = (r"şef|chef|aşçı|kurucu(?:su)?|kurucu ortak|founder|co-?founder|ceo|cto|genel müdür(?:ü)?|"
               r"direktör(?:ü)?|director|profesör|professor|akademisyen|araştırmacı|researcher|uzman|"
               r"konuşmacı|speaker|moderatör|moderator|mentor|jüri (?:üyesi|başkanı)|eğitmen|"
               r"yönetim kurulu başkanı|chairman|editör|gazeteci|yazar|girişimci|entrepreneur")
ROLE_AFTER = r"founder|co-?founder|ceo|cto|director|professor|chef|chair(?:man)?|head|partner"
PLURAL = (r"jüri üyeleri|jürileri|jüri üyelerinden|jüride|konuşmacılar|konuşmacılarımız|şefler|şefleri|"
          r"kurucuları|kurucular|mentorlar|mentorları|uzmanlar|panelistler|speakers|judges|jury members|"
          r"panelists|mentors|founders|katılımcılar")
TITLE_NAME = re.compile(rf"(?<![\w.]){TITLE}[ \t]*({NAME}){SUFFIX}")
BEFORE_NAME = re.compile(rf"(?<!\w)((?i:{ROLE_BEFORE}))[ \t]+({NAME}){SUFFIX}")
NAME_AFTER = re.compile(rf"({NAME}){SUFFIX}[ \t]*,[ \t]+(?i:(?:the[ \t]+|a[ \t]+)?(?:{ROLE_AFTER}))(?!\w)")
LIST = re.compile(rf"(?<!\w)((?i:{PLURAL}))[ \t]*:?[ \t]+((?:{NAME}{SUFFIX})(?:[ \t]*,[ \t]*{NAME}{SUFFIX}){{0,8}}"
                  rf"(?:[ \t]*,?[ \t]+(?:ve|and|ile|&)[ \t]+{NAME}{SUFFIX})?)")
STOP_TAIL = {"kimdir", "nedir", "hakkında", "biyografi", "ödülleri", "yer", "tarafından", "olarak"}
MAX_MENTIONS = 12


def clean(name, person_name):
    words = [re.sub(r"['’].*$", "", w) for w in name.split()]
    while words and words[-1].casefold() in STOP_TAIL:
        words.pop()
    found = person_name(" ".join(words)) if len(words) >= 2 else None
    return found if found and plausible(found) else None


def sentence(text, start, end):
    left = max(text.rfind(".", 0, max(0, start - 1)), text.rfind("\n", 0, start), start - 220)
    right = [i for i in (text.find(". ", end), text.find("\n", end)) if i != -1]
    return " ".join(text[left + 1:min(right + [end + 220])].split())[:400]


def mentioned_people(text, person_name):
    """[(name, role, evidence)] for people anchored by a title or a role in running text."""
    text = text[:60000]
    found, seen = [], set()

    def add(raw, role, start, end, need_given):
        name = clean(raw, person_name)
        if not name or name.casefold() in seen:
            return
        if need_given and not known_given_name(name.split()[0]):
            return
        seen.add(name.casefold())
        found.append((name, role, sentence(text, start, end)))

    for match in TITLE_NAME.finditer(text):
        title = text[match.start():match.start(1)].strip()
        add(match.group(1), title, match.start(), match.end(), False)
    for match in BEFORE_NAME.finditer(text):
        add(match.group(2), match.group(1), match.start(), match.end(), True)
    for match in NAME_AFTER.finditer(text):
        role = text[match.end(1):match.end()].strip(" ,")
        add(match.group(1), role, match.start(), match.end(), True)
    for match in LIST.finditer(text):
        names = re.split(r"[ \t]*,[ \t]*|[ \t]+(?:ve|and|ile|&)[ \t]+", match.group(2))
        given = sum(known_given_name(n.split()[0]) for n in names if n)
        if given * 3 < len(names):  # a third with a known given name: a list of people
            continue
        for raw in names:
            add(raw, match.group(1), match.start(), match.end(), False)
    return found[:MAX_MENTIONS]
