"""Build 100 explicitly fictional, deterministic search fixtures; never seed the live DB."""
import json
from html import escape
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
NAMES = {
    "tr": ["Deniz Acar", "Selin Demir", "Ayşe Yıldız", "Emre Kaya", "Ece Arslan", "Can Aksoy", "İpek Şahin", "Ozan Güneş", "Elif Yalçın", "Bora Çelik"],
    "en": ["Alex Morgan", "Jamie Taylor", "Robin Clark", "Sam Parker", "Casey Miller", "Drew Wilson", "Jordan Reed", "Avery Scott", "Blair Evans", "Riley Davis"],
    "de": ["Lena Müller", "Jonas Weber", "Mia Fischer", "Leon Wagner", "Clara Hoffmann", "Paul Schäfer", "Emma Bauer", "Felix Klein", "Laura Neumann", "Lukas Richter"],
    "fr": ["Camille Martin", "Louis Bernard", "Chloé Dubois", "Hugo Laurent", "Émilie Moreau", "Jules Simon", "Manon Lefèvre", "Alice Michel", "Arthur Roux", "Lucie Garnier"],
    "es": ["Lucía García", "Hugo Fernández", "Sofía López", "Mateo Sánchez", "Elena Rodríguez", "Diego Pérez", "Valeria Gómez", "Daniel Martín", "Paula Ruiz", "Álvaro Torres"],
    "ar": ["أحمد حسن", "ليلى محمود", "سارة علي", "عمر خالد", "نور سامي", "يوسف ناصر", "مريم عادل", "خالد أمين", "هند فؤاد", "رامي طارق"],
}
ROLES = {
    "tr": ["CTO", "Kurucu", "Doktor", "CTO", "Kurucu", "Profesör", "Mühendis", "Şef", "Profesör", "CTO"],
    "en": ["CTO", "Founder", "Doctor", "CTO", "Founder", "Professor", "Engineer", "Chef", "Professor", "CTO"],
    "de": ["CTO", "Gründer", "Arzt", "CTO", "Gründer", "Professor", "Ingenieur", "Koch", "Professor", "CTO"],
    "fr": ["CTO", "Fondateur", "Médecin", "CTO", "Fondateur", "Professeur", "Ingénieur", "Chef", "Professeur", "CTO"],
    "es": ["CTO", "Fundador", "Médico", "CTO", "Fundador", "Profesor", "Ingeniero", "Chef", "Profesor", "CTO"],
    "ar": ["CTO", "مؤسس", "طبيب", "CTO", "مؤسس", "أستاذ", "مهندس", "طاه", "أستاذ", "CTO"],
}


def build_cases():
    cases = []

    def add(category, lang, html, expected, name="Fixture Page", target="CTO", url=None):
        index = len(cases) + 1
        cases.append({"id": f"case-{index:03}", "category": category, "fictional": True,
                      "url": url or "https://fixture.example/people/" + quote(name.replace(" ", "-")),
                      "title": name, "html": f'<html lang="{lang}"><head><title>{escape(name)}</title></head><body>{html}</body></html>',
                      "research": {"title": f"Fictional case {index}", "field": "Technology",
                                   "location": "Istanbul", "target_type": target, "description": "",
                                   "search_language": lang, "requested_quantity": 1, "keywords": []},
                      "expected": expected})

    for lang, names in NAMES.items():
        for i, name in enumerate(names):
            role = ROLES[lang][i]
            bio = f"{name} — {role}. " + (f"{name} " * 4) + "Fictional professional biography for automated testing only."
            person = {"@type": "Person", "name": name, "jobTitle": role, "description": bio,
                      "worksFor": {"@type": "Organization", "name": "Demo Company"}}
            if i in (0, 5, 6, 8, 9):
                data = person if i == 0 else {"@type": "ProfilePage", "mainEntity": person} if i == 5 else [person]
                html = f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script><h1>{name}</h1><p>{bio}</p>'
            elif i == 1:
                html = f"<h1>{name}</h1><p>{bio}</p>"
            elif i == 2:
                html = f"<h2>{role} {name}</h2><p>{bio}</p>"
            elif i == 3:
                html = f"<h2>{name} — {role}</h2><p>{bio}</p>"
            elif i == 4:
                html = f'<h1>Team</h1><div class="team-member"><h3>{name}</h3><span>{role}</span><a href="/profile/{quote(name)}">Profile</a></div>'
            else:
                html = f"<strong>{i + 1}. {role} {name}</strong><div>{bio}</div>"
            add(f"positive-{i}", lang, html, [name], name, role)

    job_titles = [("tr", "İstanbul Mühendis İş İlanları"), ("tr", "Istanbul Muhendis Is Ilanlari"),
                  ("en", "London Software Job Openings"), ("en", "Engineering Jobs In Istanbul"),
                  ("de", "Berlin Ingenieur Stellenangebote"), ("fr", "Offres Emploi Ingénieur Paris"),
                  ("es", "Ofertas Empleo Ingeniero Madrid"), ("ar", "وظائف مهندس في اسطنبول"),
                  ("tr", "İstanbul Güncel İş Fırsatları"), ("en", "Chief Technology Officer Vacancies")]
    for lang, title in job_titles:
        data = {"@type": "JobPosting", "title": title, "description": "Engineer CTO Founder"}
        add("negative-job-listing", lang, f'<script type="application/ld+json">{json.dumps(data)}</script><h1>{title}</h1><p>{title} engineer CTO founder chef professor</p>', [], title,
            url="https://fixture.example/jobs/" + quote(title.replace(" ", "-")))
    for name in ["Atlas Systems", "Acme Labs", "Global Technology Services", "Future Engineering Group", "Bilgi Teknoloji Merkezi", "Yeni Eğitim Programları", "Research Team Members", "Chief Technology Officer"]:
        add("negative-organization", "en", f'<script type="application/ld+json">{json.dumps({"@type":"Organization","name":name})}</script><h1>{name}</h1><p>{name} engineer CTO founder</p>', [], name)
    for i in range(8):
        name = NAMES["en"][i]
        if i < 4:
            html = f'<script type="application/ld+json">{json.dumps({"@type":"Person","name":name,"jobTitle":"CTO"})}</script><h1>Technology News</h1><p>Article by {name}</p>'
        else:
            html = f'<nav><h2>CTO {name}</h2><p>{name} CTO biography ' + "navigation " * 15 + "</p></nav><h1>Welcome</h1>"
        add("negative-author-or-navigation", "en", html, [], "Technology News", url="https://fixture.example/news")
    for i in range(8):
        name = NAMES["en"][i]
        data = {"@type": "Person", "name": name, "jobTitle": "Chef", "description": f"{name} is a chef who teaches cooking."}
        add("negative-wrong-role", "en", f'<script type="application/ld+json">{json.dumps(data)}</script><h1>{name}</h1>', [], name, "CTO")
    for i in range(6):
        name = NAMES["en"][i]
        add("negative-insufficient-evidence", "en", f"<h1>{name}</h1><p>Contact our team for more information.</p>", [], name)
    assert len(cases) == 100
    return cases


if __name__ == "__main__":
    path = ROOT / "backend/tests/fixtures/search_cases_100.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_cases(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Created 100 fictional cases: {path}")
