"""Site-independent people lists: records found by their repeated shape, not by class names."""

import pytest

from app.services.extraction import extract_profiles, person_name
from app.services.page_context import page_context
from app.services.record_blocks import parse_line


@pytest.mark.parametrize("line, expected", [
    ("Prof. Dr. Jale Çakıroğlu", ("Jale Çakıroğlu", "Prof. Dr.", "", False)),
    ("Dr.Öğretim Üyesi AYÇA TOPALLI", ("AYÇA TOPALLI", "Dr.Öğretim Üyesi", "", False)),
    ("Arş.Gör.Dr. SERTAÇ KILIÇKAYA", ("SERTAÇ KILIÇKAYA", "Arş.Gör.Dr.", "", False)),
    ("Assoc. Prof. Dr. Berna Kiraz", ("Berna Kiraz", "Assoc. Prof. Dr.", "", False)),
    ("Muhammet Sebul Beratoğlu, Ph.D.", ("Muhammet Sebul Beratoğlu", "", "", False)),
    ("Prof. Dr. Selim YAZICI – Kurucu Ortak", ("Selim YAZICI", "Prof. Dr.", "Kurucu Ortak", False)),
    ("İhsan ELGİN Co-Founder", ("İhsan ELGİN", "", "Co-Founder", False)),
    ("Üye: Prof. Dr. Ahmet Alper ÖNER", ("Ahmet Alper ÖNER", "Prof. Dr.", "Üye", False)),
    ("Alman, Josh", ("Josh Alman", "", "", True)),
    ("Kuei (Jack) Sun", ("Kuei Sun", "", "", False)),
    # Names that begin like a title ("Müh.", "Eng.") or end like a degree ("Dr", "MA").
    ("Muhammed Göleç", ("Muhammed Göleç", "", "", False)),
    ("Doç. Dr. Engin Karahan", ("Engin Karahan", "Doç. Dr.", "", False)),
    ("Mario Badr", ("Mario Badr", "", "", False)),
    ("Fermi Ma", ("Fermi Ma", "", "", False)),
])
def test_name_lines_are_parsed_with_titles_roles_and_name_order(line, expected):
    assert parse_line(line, person_name) == expected


@pytest.mark.parametrize("line", [
    "Occupational Safety Coordinator", "Google Scholar", "Mobile App Development", "Başkan'dan Mesaj",
    "Teknoloji Danışmanı", "Nevzat Aydın Kapital A.Ş.", "Tavuk Salamura (Ünlü Şeften)", "San Francisco",
    "Castrol - Küresel İş Mobilitesi Direktörü", "Phone Number", "Agarwal Website", "Oda: EFA-112",
    "Programı Keşfet", "Davet Edin", "Mehmet HAKLIDIR OECD One", "İdare Hukuku", "Termodinamik Anabilim Dalı",
])
def test_headings_roles_companies_and_labels_are_not_names(line):
    assert parse_line(line, person_name) is None


STAFF = """<html><head><title>Akademik Kadro - Örnek Üniversitesi</title></head><body>
<nav><ul><li><a href="/">Ana Sayfa</a></li><li><a href="/kadro">Ali Veli</a></li></ul></nav>
<h1>Akademik Kadro</h1>
<!-- Google Tag Manager -->
<div class="grid">
 <div class="card"><h5 class="card-title">Prof. Dr. Ayşe Kaya</h5><p>Bölüm Başkanı</p>
  <p>Araştırma Alanları: Bilgisayarlı Görü; Makine Öğrenmesi</p>
  <a href="mailto:ayse.kaya@ornek.edu.tr">E-posta</a><a href="/akademisyen/ayse-kaya">Profil</a></div>
 <div class="card"><h5 class="card-title">Doç. Dr. Mehmet Demir</h5><p>Öğretim Üyesi</p>
  <p>Araştırma Alanları: Doğal Dil İşleme</p></div>
 <div class="card"><h5 class="card-title">Dr. Öğr. Üyesi Zeynep Arslan</h5><p>Öğretim Üyesi</p></div>
 <div class="card lead"><h6 class="card-title">Prof. Dr. Can Öztürk</h6><p>Dekan</p></div>
</div>
<footer><address>Örnek Üniversitesi, Maslak, İstanbul, Türkiye</address></footer>
</body></html>"""


def test_staff_cards_become_people_with_their_own_role_expertise_and_contact():
    people = {p.full_name: p for p in extract_profiles(STAFF, "https://ornek.edu.tr/akademik-kadro")[1]}
    assert set(people) == {"Ayşe Kaya", "Mehmet Demir", "Zeynep Arslan", "Can Öztürk"}
    ayse = people["Ayşe Kaya"]
    assert ayse.job_title == "Bölüm Başkanı" and ayse.source_type == "people_list"
    assert ayse.expertise == ["Bilgisayarlı Görü", "Makine Öğrenmesi"]
    assert ayse.public_email == "ayse.kaya@ornek.edu.tr"
    assert ayse.website == "https://ornek.edu.tr/akademisyen/ayse-kaya"
    # Contact details of one card never leak into the next card.
    assert people["Mehmet Demir"].public_email is None and people["Mehmet Demir"].website is None
    assert people["Mehmet Demir"].expertise == ["Doğal Dil İşleme"]
    # The page owner and its address apply to everyone listed, marked as inferred.
    assert ayse.organization == "Örnek Üniversitesi" and (ayse.city, ayse.country) == ("İstanbul", "Türkiye")
    assert "Sayfa bağlamından çıkarıldı" in ayse.source_evidence


def test_product_cards_are_capitalized_like_names_but_are_not_people():
    html = """<title>Hizmetlerimiz | Örnek Yazılım</title><h1>Hizmetlerimiz</h1><div class="services">
    <div class="item"><h3>Mobile App Development</h3><p>iOS ve Android</p></div>
    <div class="item"><h3>Smart City Solutions</h3><p>Akıllı şehir</p></div>
    <div class="item"><h3>Cloud Platform Services</h3><p>Bulut</p></div>
    <div class="item"><h3>Data Analytics Consulting</h3><p>Veri</p></div></div>"""
    assert extract_profiles(html, "https://ornek.com/hizmetler")[1] == []


def test_table_rows_and_role_labels_are_records():
    html = """<title>Yönetim Kurulu</title><h1>Yönetim Kurulu</h1><table><tbody>
    <tr><td>Başkan : Prof. Dr. Oktay Özkan</td></tr><tr><td>Üye: Prof. Dr. Uğur Şahin</td></tr>
    <tr><td>Üye: Murat Yibur</td></tr><tr><td>Üye: Latif Başkal</td></tr></tbody></table>"""
    people = {p.full_name: p.job_title for p in extract_profiles(html, "https://ornek.com/yonetim-kurulu")[1]}
    assert people == {"Oktay Özkan": "Başkan", "Uğur Şahin": "Üye", "Murat Yibur": "Üye", "Latif Başkal": "Üye"}


def test_bare_links_without_record_content_need_known_given_names():
    html = """<title>Faculty members</title><h1>Faculty members</h1>
    <a href="/news">Random Heading</a><a href="/x">Former Academics</a><a href="/y">Grace Hopper</a>"""
    assert extract_profiles(html, "https://example.com/people")[1] == []


def test_an_article_infobox_with_a_few_relatives_is_not_a_people_list():
    html = """<title>Ada Yılmaz - Vikipedi</title><h1>Ada Yılmaz</h1><table class="infobox">
    <tr><th>Ebeveyn</th><td>Can Yılmaz</td></tr><tr><th>Kardeş</th><td>Ece Yılmaz</td></tr>
    <tr><th>Eş</th><td>Deniz Acar</td></tr></table><p>Ada Yılmaz bir mühendistir.</p>"""
    names = [p.full_name for p in extract_profiles(html, "https://tr.wikipedia.org/wiki/Ada_Y%C4%B1lmaz")[1]]
    assert not {"Can Yılmaz", "Ece Yılmaz", "Deniz Acar"} & set(names)


def test_page_owner_comes_from_the_title_segment_that_matches_the_host():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<title>Ekibimiz | Alias Yazılım | Kapsamlı Teknoloji Çözümleri</title>"
                         "<footer>Kayseri Teknopark, Kayseri</footer>", "html.parser")
    context = page_context(soup, "https://www.aliasyazilim.com/Team", soup.title.string)
    assert context.organization == "Alias Yazılım"
    assert (context.city, context.country) == ("Kayseri", "Türkiye")


def test_an_ambiguous_city_word_counts_only_in_an_address():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<title>Aydın Akan - Profil</title><h1>Aydın Akan</h1>", "html.parser")
    assert page_context(soup, "https://example.org/aa", soup.title.string).city is None


def test_a_company_directory_with_a_repeated_label_is_not_a_people_list():
    # Live: vcbacked.co listed startups, each with the same "Founder Contacts" link label.
    names = ["Wodo Network", "Spark SuperApp", "Silent Protocol", "Fork N Knife", "JAZARI Powertrain",
             "Leo Drive", "Ace Games"]
    cards = "".join(f'<div class="c"><h3>{n}</h3><p>Founder Contacts</p><p>Istanbul, Turkey</p></div>'
                    for n in names)
    html = f'<title>Istanbul startups | VCBacked</title><h1>Startups</h1><div class="grid">{cards}</div>'
    assert extract_profiles(html, "https://www.vcbacked.co/directory/cities/turkey/istanbul")[1] == []
    # The same label under people's names is fine when the names are people's.
    board = "".join(f'<div class="c"><h3>{n}</h3><p>Yönetim Kurulu Üyesi</p></div>'
                    for n in ["Ayşe Kaya", "Mehmet Demir", "Can Öztürk", "Zeynep Arslan"])
    people = extract_profiles(f"<title>Yönetim Kurulu</title><h1>Yönetim Kurulu</h1>{board}",
                              "https://example.com/yonetim-kurulu")[1]
    assert len(people) == 4


def test_research_area_headings_and_retired_prefixes_are_not_names():
    assert person_name("Bilgisayarlı Görü") is None and person_name("Machine Learning") is None
    assert parse_line("Retired Muhittin Gökmen", person_name)[:2] == ("Muhittin Gökmen", "Retired")


def test_page_body_inside_an_aside_and_names_split_into_hcard_spans_are_read():
    # Live: a faculty list inside <aside class="content">, and hCard names in two spans.
    cards = "".join(f'<div class="card"><h5>{t} {n}</h5><p>Öğretim Üyesi</p></div>'
                    for t, n in [("PROF. DR.", "AHMET KARAKOCALI"), ("DOÇ. DR.", "ELİF UZUN"),
                                 ("ARAŞ. GÖR.", "BURAK IŞIK")])
    html = (f'<title>Akademik Kadro</title><nav><a href="/">Ana Sayfa</a></nav>'
            f'<aside class="col-md-9 content"><h2>Akademik Kadro</h2>{cards}</aside>')
    names = [p.full_name for p in extract_profiles(html, "https://example.edu.tr/akademik-kadro")[1]]
    assert names == ["AHMET KARAKOCALI", "ELİF UZUN", "BURAK IŞIK"]
    hcards = "".join(f'<div class="item"><span class="fn n"><span class="given-name">{g}</span> '
                     f'<span class="family-name">{f}</span></span><span class="title">Professor</span></div>'
                     for g, f in [("David", "Arnold"), ("Navid", "Asadi"), ("Swarup", "Bhunia")])
    people = extract_profiles(f"<title>Faculty</title><h1>Faculty</h1>{hcards}", "https://ece.example.edu/faculty")[1]
    assert [p.full_name for p in people] == ["David Arnold", "Navid Asadi", "Swarup Bhunia"]


def test_an_acronym_before_a_name_is_an_organization_label():
    assert parse_line("SGK Yenal Arslan", person_name) is None
    assert parse_line("UDHB Haberleşme Genel Müdürlüğü", person_name) is None
    assert parse_line("Selim YAZICI", person_name)[0] == "Selim YAZICI"
