#!/usr/bin/env python
"""Evaluate the Laya sentiment analyzer against hand-labeled ES mentions.

Usage:
    python backend/scripts/eval_sentiment.py [--baseline] [--jsonl PATH]

Runs the real Laya model (downloads ~421MB on first use) over each mention
in eval_mentions_es.jsonl and prints an agreement table vs gold labels:
overall accuracy, per-label precision/recall, and the sarcasm subset.

--baseline runs the trivial KeywordBaselineAnalyzer instead (no download)
— useful as a floor to beat and to smoke-test the script.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sentiment.laya_analyzer import (  # noqa: E402
    KeywordBaselineAnalyzer,
    LayaAnalyzer,
)

DEFAULT_JSONL = Path(__file__).parent / "eval_mentions_es.jsonl"
LABELS = ("positive", "neutral", "negative")


def load_mentions(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Run the keyword baseline analyzer instead of Laya (no model).",
    )
    args = parser.parse_args()

    rows = load_mentions(args.jsonl)
    if not rows:
        print(f"no rows found in {args.jsonl}", file=sys.stderr)
        return 1

    analyzer = KeywordBaselineAnalyzer() if args.baseline else LayaAnalyzer()
    engine_name = "KeywordBaselineAnalyzer" if args.baseline else "LayaAnalyzer"

    confusion: Counter[tuple[str, str]] = Counter()
    correct = 0
    sarcasm_correct = 0
    sarcasm_total = 0
    for row in rows:
        gold = row["gold"]
        result = analyzer.analyze(row["text"], lang="es")
        pred = result.label.value
        confusion[(gold, pred)] += 1
        if pred == gold:
            correct += 1
        if row.get("sarcasm"):
            sarcasm_total += 1
            sarcasm_correct += int(pred == gold)

    n = len(rows)
    print(f"engine: {engine_name}")
    print(f"rows: {n}  correct: {correct}  accuracy: {correct / n:.2%}")
    print()
    print("agreement table (rows=gold, cols=predicted):")
    header = f"{'gold':<10}" + "".join(f"{c:>11}" for c in LABELS) + f"{'recall':>9}"
    print(header)
    for gold_label in LABELS:
        gold_n = sum(confusion[(gold_label, p)] for p in LABELS)
        recall = confusion[(gold_label, gold_label)] / gold_n if gold_n else 0.0
        cells = "".join(f"{confusion[(gold_label, p)]:>11}" for p in LABELS)
        print(f"{gold_label:<10}{cells}{recall:>9.0%}")
    print()
    print("precision per predicted label:")
    for pred_label in LABELS:
        pred_n = sum(confusion[(g, pred_label)] for g in LABELS)
        precision = confusion[(pred_label, pred_label)] / pred_n if pred_n else 0.0
        print(f"  {pred_label:<10} precision={precision:.0%}  (predicted {pred_n})")
    print()
    print(f"sarcasm subset: {sarcasm_correct}/{sarcasm_total} correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
