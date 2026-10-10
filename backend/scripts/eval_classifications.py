#!/usr/bin/env python
"""Evaluate the Laya political classifier against hand-labeled ES mentions.

Usage:
    python backend/scripts/eval_classifications.py [--jsonl PATH] [--threshold 0.70]

Runs the real Laya model (downloads on first use via the shared Laya runtime)
over each row in the JSONL and prints accuracy plus a confusion table vs gold
labels. Rows must contain `text` and `gold`; lines starting with `#` are
treated as comments (the gold file documents its labeling codebook there).
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.classifications.political import PoliticalClassifier  # noqa: E402

DEFAULT_JSONL = Path(__file__).parent / "eval_classifications_political_es.jsonl"
LABELS = ("political", "not_political", "uncertain")


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            missing = {"text", "gold"} - set(row)
            if missing:
                raise ValueError(f"{path}:{line_number} missing fields: {sorted(missing)}")
            if row["gold"] not in LABELS:
                raise ValueError(f"{path}:{line_number} unknown gold label: {row['gold']!r}")
            rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.70,
        help="Minimum chosen-label confidence before returning political/not_political.",
    )
    args = parser.parse_args()

    rows = load_rows(args.jsonl)
    if not rows:
        print(f"no rows found in {args.jsonl}", file=sys.stderr)
        return 1

    classifier = PoliticalClassifier(confidence_threshold=args.threshold)
    confusion: Counter[tuple[str, str]] = Counter()
    correct = 0
    for row in rows:
        gold = row["gold"]
        result = classifier.classify(row["text"], lang=row.get("lang", "es"))
        pred = result.label
        confusion[(gold, pred)] += 1
        correct += int(pred == gold)

    n = len(rows)
    print("engine: PoliticalClassifier(Laya)")
    print(f"threshold: {args.threshold:.2f}")
    print(f"rows: {n}  correct: {correct}  accuracy: {correct / n:.2%}")
    print()
    print("confusion table (rows=gold, cols=predicted):")
    header = f"{'gold':<15}" + "".join(f"{c:>15}" for c in LABELS) + f"{'recall':>9}"
    print(header)
    for gold_label in LABELS:
        gold_n = sum(confusion[(gold_label, p)] for p in LABELS)
        recall = confusion[(gold_label, gold_label)] / gold_n if gold_n else 0.0
        cells = "".join(f"{confusion[(gold_label, p)]:>15}" for p in LABELS)
        print(f"{gold_label:<15}{cells}{recall:>9.0%}")
    print()
    print("precision per predicted label:")
    for pred_label in LABELS:
        pred_n = sum(confusion[(g, pred_label)] for g in LABELS)
        precision = confusion[(pred_label, pred_label)] / pred_n if pred_n else 0.0
        print(f"  {pred_label:<15} precision={precision:.0%}  (predicted {pred_n})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
