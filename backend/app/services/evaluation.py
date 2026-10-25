"""Offline extraction quality on frozen real pages (see docs/search-audit.md, sets D1/D1b).

`directory` holds `labels.json` and `pages/<file>`. Labels list every person a page names
("people"); "ignore" lists real people a page mentions in passing (columnists, editors) that
are neither required nor counted as wrong. They hold real names, so the sets live outside git
(artifacts/eval/).
"""

import json
import re
from pathlib import Path

from app.services.deduplication import same_name
from app.services.extraction import extract_profiles

NICKNAME = re.compile(r"\s*(?:\([^)]*\)|\"[^\"]*\"|“[^”]*”)\s*")


def plain(name):
    """'Kuei (Jack) Sun' and 'Kuei Sun' name the same person."""
    return " ".join(NICKNAME.sub(" ", name).split())


def match_names(extracted, expected):
    """(found, missed, wrong): labeled names extracted, labeled names missed, extra names."""
    unused = list(extracted)
    found, missed = [], []
    for name in expected:
        hit = next((x for x in unused if same_name(plain(x), plain(name))), None)
        if hit is None:
            missed.append(name)
        else:
            found.append(name)
            unused.remove(hit)
    return found, missed, unused


def ratio(part, whole):
    return round(part / whole, 3) if whole else None


def evaluate_pages(directory, extract=extract_profiles):
    directory = Path(directory)
    labels = json.loads((directory / "labels.json").read_text(encoding="utf-8"))
    pages = []
    for page in labels["pages"]:
        html = (directory / "pages" / page["file"]).read_bytes()
        names = [p.full_name for p in extract(html, page["url"])[1]]
        found, missed, wrong = match_names(names, page["people"])
        ignored = [n for n in wrong if any(same_name(n, x) for x in page.get("ignore", []))]
        wrong = [n for n in wrong if n not in ignored]
        pages.append({"file": page["file"], "url": page["url"], "kind": page["kind"],
                      "listed": len(page["people"]), "correct": len(found), "wrong": len(wrong),
                      "wrong_names": wrong, "missed": missed, "ignored": ignored})
    listed = sum(p["listed"] for p in pages)
    correct = sum(p["correct"] for p in pages)
    wrong = sum(p["wrong"] for p in pages)
    with_people = [p for p in pages if p["listed"]]
    return {"pages": pages, "total": {
        "pages": len(pages), "listed": listed, "correct": correct, "wrong": wrong,
        "recall": ratio(correct, listed), "precision": ratio(correct, correct + wrong),
        "pages_with_people": sum(p["correct"] > 0 for p in pages),
        # Every page weighs the same: one 195-person directory cannot hide ten missed pages.
        "page_recall": ratio(sum(p["correct"] / p["listed"] for p in with_people), len(with_people)),
        "empty_pages_with_names": sum(not p["listed"] and p["wrong"] > 0 for p in pages)}}
