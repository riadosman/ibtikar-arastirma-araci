"""Measure person extraction on frozen real pages: recall, precision, pages with people.

The page set (artifacts/eval/pages + labels.json) holds real people's names and stays out
of git. Run it before and after every extraction change and compare the totals; result
counts alone are not a quality measure (docs/search-audit.md, section 7).

    .venv/Scripts/python.exe scripts/eval_extraction.py [artifacts/eval] [--json out.json]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.evaluation import evaluate_pages  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", default=str(ROOT / "artifacts" / "eval"))
    parser.add_argument("--json", help="also write the full report here")
    args = parser.parse_args()
    report = evaluate_pages(args.directory)
    for page in report["pages"]:
        print(f"{page['file']}  {page['kind']:<16} {page['correct']:>3}/{page['listed']:<3} doğru, "
              f"{page['wrong']} yanlış  {page['url'][:70]}")
        if page["wrong_names"]:
            print(f"      yanlış: {', '.join(page['wrong_names'])}")
    total = report["total"]
    print(f"\nToplam: {total['correct']}/{total['listed']} kişi (duyarlılık {total['recall']}), "
          f"{total['wrong']} yanlış (kesinlik {total['precision']}), "
          f"{total['pages_with_people']}/{total['pages']} sayfadan en az bir doğru kişi, "
          f"sayfa ortalaması duyarlılık {total['page_recall']}, "
          f"kişisiz sayfadan ad çıkan: {total['empty_pages_with_names']}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
