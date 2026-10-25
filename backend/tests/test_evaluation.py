"""Extraction is measured on frozen pages against hand-checked labels, not by result counts."""

import json
from types import SimpleNamespace

from app.services.evaluation import evaluate_pages, match_names


def test_names_match_despite_case_titles_and_one_letter_spelling():
    found, missed, wrong = match_names(
        ["Serhat ÖZEKES", "Prof. Dr. Jale Çakıroğlu", "Kurucu Üyelerimiz"],
        ["Serhat Özekes", "Jale Cakıroğlu", "Ayşe Yayla"],
    )
    assert found == ["Serhat Özekes", "Jale Cakıroğlu"]
    assert missed == ["Ayşe Yayla"]
    assert wrong == ["Kurucu Üyelerimiz"]


def test_pages_are_scored_for_recall_and_precision(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "01.html").write_text(
        '<script type="application/ld+json">{"@type": "Person", "name": "Ada Lovelace", "jobTitle": "CTO"}'
        "</script><h1>Ada Lovelace</h1><p>CTO</p>", encoding="utf-8")
    (tmp_path / "pages" / "02.html").write_text("<h1>Ekip</h1><p>Grace Hopper - CTO</p>", encoding="utf-8")
    labels = {"pages": [
        {"file": "01.html", "url": "https://example.org/ada-lovelace", "kind": "profile", "people": ["Ada Lovelace"]},
        {"file": "02.html", "url": "https://example.org/ekip", "kind": "team list", "people": ["Grace Hopper"]},
    ]}
    (tmp_path / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
    report = evaluate_pages(tmp_path)
    assert [(p["file"], p["listed"], p["correct"], p["wrong"]) for p in report["pages"]] == [
        ("01.html", 1, 1, 0), ("02.html", 1, 0, 0)]
    assert report["total"] == {"pages": 2, "listed": 2, "correct": 1, "wrong": 0, "recall": 0.5,
                               "precision": 1.0, "pages_with_people": 1, "page_recall": 0.5,
                               "empty_pages_with_names": 0}


def test_names_a_page_mentions_in_passing_are_not_counted_as_wrong(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "01.html").write_text("<p>x</p>", encoding="utf-8")
    labels = {"pages": [{"file": "01.html", "url": "https://example.org/news", "kind": "article",
                         "people": ["Ada Lovelace"], "ignore": ["Grace Hopper"]}]}
    (tmp_path / "labels.json").write_text(json.dumps(labels), encoding="utf-8")

    def extract(html, url):
        return "", [SimpleNamespace(full_name=n) for n in ("Ada Lovelace", "Grace Hopper", "Alan Turing")]

    page = evaluate_pages(tmp_path, extract)["pages"][0]
    assert (page["correct"], page["wrong"], page["ignored"]) == (1, 1, ["Grace Hopper"])
