#!/usr/bin/env python
"""Evaluate the Laya topic classifier (v2 taxonomy) against hand-labeled ES titles.

Usage:
    python backend/scripts/eval_topics.py [--jsonl PATH]

Runs the real Laya model over each row and prints per-label precision/recall
plus the confusion pairs, so prompt iterations have a number to beat
(gate: precision >= 0.80 per label before the production re-classify).
Rows: `text`, `gold` in {academic, infrastructure, institutional, students,
culture, finance, government, health}; `#` lines are comments.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.classifications.topics import OTHER_LABEL, TopicClassifier  # noqa: E402

DEFAULT_JSONL = Path(__file__).resolve().parent.parent / "eval_topics_gold_es.jsonl"
LABELS = (
    "academic",
    "infrastructure",
    "institutional",
    "students",
    "culture",
    "sports",
    "finance",
    "government",
    "health",
)


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
            if row["gold"] not in (*LABELS,):
                raise ValueError(f"{path}:{line_number} unknown gold label: {row['gold']!r}")
            # Match the pipeline input: title + content head (the classifier
            # never sees the title alone in production).
            row["text"] = "\n".join(
                part for part in (row["text"], row.get("context") or "") if part
            )
            rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    args = parser.parse_args()

    rows = load_rows(args.jsonl)
    classifier = TopicClassifier()

    confusion: dict[str, Counter] = defaultdict(Counter)
    correct = 0
    empty = 0
    for row in rows:
        result = classifier.classify(row["text"], "es")
        predicted = result.label if not isinstance(result, list) else None
        if predicted is None:
            empty += 1
            predicted = OTHER_LABEL
        if predicted == row["gold"]:
            correct += 1
        confusion[row["gold"]][predicted] += 1

    print(f"rows={len(rows)} accuracy={correct / len(rows):.2f} empty={empty}")
    print("\nper-label (gold -> predicted):")
    worst = []
    for label in LABELS:
        gold_n = sum(confusion[label].values())
        if gold_n == 0:
            continue
        hits = confusion[label][label]
        precision = hits / max(1, sum(confusion[pred][label] for pred in confusion))
        recall = hits / gold_n
        print(f"  {label:<15} n={gold_n:<3} precision={precision:.2f} recall={recall:.2f}")
        if precision < 0.8:
            worst.append(label)
        wrong = {pred: n for pred, n in confusion[label].items() if pred != label and n}
        if wrong:
            print(f"    as: {wrong}")
    if worst:
        print(f"\nbelow gate 0.80: {worst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
