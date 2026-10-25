"""Run real briefs through the live pipeline against a throwaway SQLite database and report.

Nothing touches the workspace database: DATABASE_URL points to a temporary file. The web is
live (search engines and pages), so two runs differ; compare versions on the same briefs, run
close together, and judge relevance by reading the top candidates (results are not labels).

    .venv/Scripts/python.exe scripts/eval_search.py [--backend DIR] [--briefs 1,3] [--budget 420]
        [--json out.json]

--backend points to another copy of backend/ (e.g. the previous version) to compare.
"""

import argparse
import json
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIEFS = [
    {"title": "İstanbul bilgisayarlı görü akademisyenleri", "field": "Computer Vision", "location": "İstanbul",
     "target_type": "Akademisyen", "keywords": ["görüntü işleme"], "search_language": "tr",
     "description": "Bilgisayarlı görü alanında çalışan öğretim üyeleri"},
    {"title": "Yapay zekâ girişim kurucuları", "field": "teknoloji", "location": "istanbul", "target_type": "kurucu",
     "keywords": ["yapay zeka girisim"], "search_language": "tr", "description": "cto veya kurucu arıyoruz"},
    {"title": "Computer Vision Experts", "field": "Artificial Intelligence", "location": "Istanbul",
     "target_type": "Speaker", "keywords": ["Computer Vision"], "search_language": "auto",
     "description": "Potential speakers / experts with university or industry experience"},
    {"title": "Gastronomi şefleri", "field": "gastronomi", "location": "İstanbul", "target_type": "şef",
     "keywords": [], "search_language": "tr", "description": "Yemek yarışması jürisi için şefler"},
    {"title": "Data science professors (Arabic)", "field": "Data science", "location": "Istanbul",
     "target_type": "Professor", "keywords": [], "search_language": "ar", "description": ""},
    {"title": "Fintech yöneticileri", "field": "fintech", "location": "İstanbul", "target_type": "CTO",
     "keywords": [], "search_language": "tr", "description": "fintech şirketlerinde CTO veya kurucu"},
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=str(ROOT / "backend"))
    parser.add_argument("--briefs", default="")
    parser.add_argument("--budget", type=int, default=420)
    parser.add_argument("--quantity", type=int, default=10)
    parser.add_argument("--json")
    args = parser.parse_args()
    folder = tempfile.mkdtemp(prefix="rip-eval-")
    os.environ.update({
        "DATABASE_URL": "sqlite:///" + (Path(folder) / "eval.db").as_posix(), "SECRET_KEY": secrets.token_hex(32),
        "APP_ENV": "development", "DEMO_MODE": "false", "LOG_LEVEL": "WARNING",
        "COLLECTION_TIME_BUDGET_SECONDS": str(args.budget),
    })
    sys.path.insert(0, args.backend)
    from app.core.db import Base, SessionLocal, engine
    from app.models import Candidate, CollectionJob, ResearchKeyword, ResearchRequest, SourceDocument
    from app.services.collection import enqueue, run_next

    Base.metadata.create_all(engine)
    chosen = [int(i) for i in args.briefs.split(",") if i] or range(1, len(BRIEFS) + 1)
    report = []
    for number in chosen:
        brief = BRIEFS[number - 1]
        with SessionLocal() as db:
            research = ResearchRequest(**{k: v for k, v in brief.items() if k != "keywords"},
                                       requested_quantity=args.quantity, notes="")
            research.keywords = [ResearchKeyword(value=k) for k in brief["keywords"]]
            db.add(research)
            db.flush()
            enqueue(db, research, None)
            db.commit()
            rid = research.id
        started = time.monotonic()
        run_next()
        elapsed = round(time.monotonic() - started)
        with SessionLocal() as db:
            job = db.query(CollectionJob).filter_by(research_request_id=rid).one()
            sources = db.query(SourceDocument).filter_by(collection_job_id=job.id).all()
            people = (db.query(Candidate).filter_by(research_request_id=rid)
                      .order_by(Candidate.relevance_score.desc()).all())
            rows = []
            for c in people:
                details = getattr(c, "match_details", None) or {}
                rows.append({
                    "name": c.full_name, "job_title": c.job_title, "organization": c.organization,
                    "place": ", ".join(filter(None, [c.location, c.city, c.country])),
                    "score": c.relevance_score, "role": (details.get("role") or {}).get("decision"),
                    "topic": (details.get("topic") or {}).get("decision"),
                    "place_decision": (details.get("place") or {}).get("decision"),
                    "source": c.sources[0].url if c.sources else "", "source_type":
                        c.sources[0].source_type if c.sources else "",
                })
            stats = job.stats or {}
            statuses = {}
            for s in sources:
                statuses[s.status] = statuses.get(s.status, 0) + 1
            entry = {"brief": number, "title": brief["title"], "status": job.status, "seconds": elapsed,
                     "queries": stats.get("search_queries"), "empty_queries": stats.get("search_empty"),
                     "sources": len(sources), "source_status": statuses,
                     "fetched": stats.get("sources_fetched"), "failed": stats.get("sources_failed"),
                     "triage_skipped": stats.get("triage_skipped", 0), "links_followed": stats.get("links_followed", 0),
                     "extracted": stats.get("profiles_extracted"), "qualified": stats.get("profiles_qualified"),
                     "candidates": len(rows), "leads": len(stats.get("lead_ids", [])),
                     "elsewhere": len(stats.get("elsewhere_ids", [])), "top": rows[:15]}
            report.append(entry)
        print(f"\n## {number}. {brief['title']} — {entry['status']} in {elapsed}s: {entry['queries']} queries "
              f"({entry['empty_queries']} empty), {entry['sources']} sources {statuses}, "
              f"{entry['extracted']} extracted, {entry['candidates']} candidates "
              f"({entry['leads']} leads, {entry['elsewhere']} elsewhere)", flush=True)
        for row in rows[:12]:
            print(f"   {row['score']:>3} {row['name'][:28]:<28} | {str(row['job_title'] or '')[:30]:<30} | "
                  f"{str(row['organization'] or '')[:24]:<24} | {row['place'][:18]:<18} | {row['role']}/"
                  f"{row['topic']}/{row['place_decision']} | {row['source'][:60]}", flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
