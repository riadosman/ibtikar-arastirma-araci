"""Arabic has no capital letters, the main evidence the extractor uses that a phrase is a name.

The rejected phrases are the non-people an Arabic search returned as candidates on 2026-10-13.
"""

from urllib.parse import quote

import pytest

from app.services.extraction import extract_profiles, person_name


@pytest.mark.parametrize("phrase", [
    "أستاذ جامعي",             # "university professor": a Wikipedia article title
    "أستاذ دكتور",             # "professor doctor": only titles
    "علم البيانات",            # "data science"
    "قالب السيرة الذاتية",     # "résumé template"
    "الذكاء الاصطناعي",        # "artificial intelligence"
    "جامعة إسطنبول التقنية",   # "Istanbul Technical University"
    "أعضاء هيئة التدريس",      # "faculty members"
    "أحمد حسن أستاذ",          # a name followed by a role word is a label, not a name
    "محمد صلى الله عليه وسلم",  # a religious formula, not a person's full name
])
def test_arabic_phrases_that_are_not_names_are_rejected(phrase):
    assert person_name(phrase) is None


@pytest.mark.parametrize("phrase, name", [
    ("أحمد حسن", "أحمد حسن"),
    ("محمد عبد الله", "محمد عبد الله"),
    ("عبد الرحمن السميط", "عبد الرحمن السميط"),
    ("عبدالله المحمد", "عبدالله المحمد"),
    ("فاطمة الزهراء علي", "فاطمة الزهراء علي"),
    ("مريم عادل", "مريم عادل"),
    ("د. خالد منصور", "خالد منصور"),
    ("الدكتورة نوال السعداوي", "نوال السعداوي"),
    ("أ.د. هالة يوسف", "هالة يوسف"),
])
def test_arabic_names_are_kept_without_their_titles(phrase, name):
    assert person_name(phrase) == name


def test_other_scripts_without_capital_letters_are_not_names():
    assert person_name("מרכז המחקר") is None  # Hebrew: "the research center"


def test_latin_names_are_unchanged():
    assert person_name("Ayşe Yılmaz") == "Ayşe Yılmaz"
    assert person_name("Ludwig van Beethoven") == "Ludwig van Beethoven"
    assert person_name("üniversite hocası") is None


def article(heading, body):
    return (f'<html lang="ar"><head><title>{heading} - ويكيبيديا</title></head><body>'
            f'<h1>{heading}</h1><p>{body}</p></body></html>')


def wiki(heading):
    return "https://ar.wikipedia.org/wiki/" + quote(heading.replace(" ", "_"))


def test_arabic_article_about_a_profession_yields_nobody():
    heading = "أستاذ جامعي"
    html = article(heading, "الأستاذ الجامعي هو أعلى رتبة أكاديمية يحملها عضو هيئة التدريس في الجامعة. "
                            "يعمل أستاذ جامعي في التدريس والبحث العلمي.")
    assert extract_profiles(html, wiki(heading), f"{heading} - ويكيبيديا")[1] == []


def test_arabic_biography_article_yields_the_person():
    heading = "خالد منصور"
    html = article(heading, "خالد منصور أستاذ في علم البيانات بجامعة إسطنبول. "
                            "خالد منصور سيرة خيالية لأغراض الاختبار فقط.")
    people = extract_profiles(html, wiki(heading), f"{heading} - ويكيبيديا")[1]
    assert [p.full_name for p in people] == ["خالد منصور"]


def test_arabic_label_with_a_role_but_no_name_yields_nobody():
    paragraph = ("قالب السيرة الذاتية لوظيفة أستاذ جامعي يساعدك على كتابة سيرة ذاتية احترافية "
                 "تبرز خبراتك في التدريس والبحث العلمي.")
    html = f'<html lang="ar"><body><h2>قالب السيرة الذاتية | أستاذ</h2><p>{paragraph}</p></body></html>'
    assert extract_profiles(html, "https://www.example.com/ar/resume-template/professor")[1] == []
