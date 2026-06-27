"""
Phase 0: Standalone hit-rate evaluation.

Usage:
    uv run scripts/phase0_eval.py cards.csv
    uv run scripts/phase0_eval.py cards.csv --limit 10 --out results/run1.json
    uv run scripts/phase0_eval.py cards.tsv --delay 5

Input CSV/TSV must have columns: 表面 (question), 裏面 (answer+commentary).
Anki export: File > Export > Notes in Plain Text, include field names.
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

sys.path.insert(0, str(Path(__file__).parent))
from image_sources import fetch_candidates
from llm import identify_entity


def load_cards(path: str) -> list[dict]:
    p = Path(path)
    dialect = "excel-tab" if p.suffix in (".tsv", ".txt") else "excel"
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, dialect=dialect))


def extract_answer(back_field: str) -> str:
    """Take the first line of the back field as the answer."""
    return back_field.split("\n")[0].split("<br>")[0].strip()


def process_card(card: dict) -> dict:
    question = card.get("表面") or card.get("front", "")
    answer = extract_answer(card.get("裏面") or card.get("back", ""))

    result: dict = {
        "question": question[:100] + "..." if len(question) > 100 else question,
        "answer": answer,
        "entity": None,
        "candidates": [],
        "hit": False,
        "error": None,
    }

    try:
        entity = identify_entity(question, answer)
        result["entity"] = {
            "name": entity.entity_name,
            "wikipedia_title_ja": entity.wikipedia_title_ja,
            "wikipedia_title_en": entity.wikipedia_title_en,
            "commons_queries": entity.commons_queries,
            "confidence": entity.confidence,
            "wikipedia_url": entity.wikipedia_url,
        }

        candidates = fetch_candidates(
            entity_name=entity.entity_name,
            wikipedia_title_ja=entity.wikipedia_title_ja,
            wikipedia_title_en=entity.wikipedia_title_en,
            commons_queries=entity.commons_queries,
        )
        result["candidates"] = [
            {"url": c.url, "thumb_url": c.thumb_url, "source": c.source, "title": c.title}
            for c in candidates
        ]
        result["hit"] = len(candidates) > 0

    except Exception as e:
        result["error"] = str(e)

    return result


def print_result(i: int, total: int, r: dict) -> None:
    status = "✓" if r["hit"] else "✗"
    conf = r["entity"]["confidence"] if r["entity"] else "—"
    n_cand = len(r["candidates"])
    answer_short = r["answer"][:30]
    print(f"[{i:3}/{total}] {status} [{conf:6}] {answer_short:<30}  {n_cand} candidates")
    if r["error"]:
        print(f"           ERROR: {r['error']}")
    if r["entity"] and r["entity"]["wikipedia_url"]:
        print(f"           Wikipedia: {r['entity']['wikipedia_url']}")


def print_summary(results: list[dict]) -> None:
    total = len(results)
    hits = sum(1 for r in results if r["hit"])
    high = sum(1 for r in results if r["hit"] and r.get("entity", {}) and r["entity"]["confidence"] == "high")
    errors = sum(1 for r in results if r["error"])

    print(f"\n{'='*60}")
    print(f"Total:          {total}")
    print(f"Hit (any image):{hits:4}  ({hits/total*100:.0f}%)")
    print(f"High-conf hits: {high:4}  ({high/total*100:.0f}%)")
    print(f"Errors:         {errors:4}")

    by_conf: dict[str, dict] = {}
    for r in results:
        if not r["entity"]:
            continue
        c = r["entity"]["confidence"]
        by_conf.setdefault(c, {"total": 0, "hit": 0})
        by_conf[c]["total"] += 1
        if r["hit"]:
            by_conf[c]["hit"] += 1

    if by_conf:
        print("\nHit rate by confidence:")
        for conf, s in sorted(by_conf.items()):
            print(f"  {conf:6}: {s['hit']}/{s['total']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 0 entity identification hit-rate eval")
    parser.add_argument("cards", help="Path to cards CSV or TSV file")
    parser.add_argument("--limit", type=int, default=None, help="Max number of cards to process")
    parser.add_argument("--out", default="results/phase0_results.json", help="Output JSON path")
    parser.add_argument("--delay", type=float, default=5.0,
                        help="Seconds between Gemini API calls (free tier: 15 RPM)")
    args = parser.parse_args()

    cards = load_cards(args.cards)
    if args.limit:
        cards = cards[:args.limit]

    print(f"Processing {len(cards)} cards  (delay={args.delay}s, model={__import__('os').environ.get('GEMINI_MODEL', 'gemini-2.0-flash')})")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    for i, card in enumerate(cards, 1):
        r = process_card(card)
        print_result(i, len(cards), r)
        results.append(r)
        if i < len(cards):
            time.sleep(args.delay)

    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print_summary(results)
    print(f"\nDetailed results → {out_path}")


if __name__ == "__main__":
    main()
