"""Heal existing event splits (T3): pair-reviewed arbitration backfill.

Ingest-side fixes never heal old splits; this script re-adjudicates them.
Dry-run by default: it detects the gray pairs over the window, asks the
arbiter (ai_model_fast) and PRINTS the verdict table — nothing is merged
or recorded. ``--apply`` runs the real pass (same verdicts re-judged at
temperature 0) and reports merged/kept counts.

Run inside the api container (skill pattern):

    docker cp backend/scripts/heal_event_splits.py media-monitor-api-1:/srv/backend/scripts/
    docker exec media-monitor-api-1 python -m scripts.heal_event_splits --days 7
    docker exec media-monitor-api-1 python -m scripts.heal_event_splits --days 7 --apply
"""

import argparse
from datetime import datetime, timezone

from app.db import SessionLocal
from app.ingest.arbitrator import (
    build_default_judge,
    find_gray_pairs,
    merge_deterministic_pairs,
    reconcile_gray_pairs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="lookback window")
    parser.add_argument("--client-id", type=int, default=1)
    parser.add_argument(
        "--apply", action="store_true", help="merge + record (default: dry-run)"
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        window_hours = args.days * 24
        # Deterministic pre-pass: legacy pairs that TODAY score >= the floor
        # (assignment-time drift) merge without judgment — same rule as the
        # live assigner, applied to history.
        if args.apply:
            deterministic = merge_deterministic_pairs(
                session, client_id=args.client_id, window_hours=window_hours
            )
            if deterministic["deterministic_merged"]:
                print(f"heal deterministic: {deterministic}")
        pairs = find_gray_pairs(
            session,
            client_id=args.client_id,
            now=datetime.now(tz=timezone.utc),
            window_hours=window_hours,
        )
        if not pairs:
            print("heal: no gray pairs in window")
            return 0

        if args.apply:
            result = reconcile_gray_pairs(
                session,
                client_id=args.client_id,
                now=datetime.now(tz=timezone.utc),
                window_hours=window_hours,
            )
            print(f"heal applied: {result}")
            return 0

        judge = build_default_judge(session, client_id=args.client_id)
        if judge is None:
            print(
                f"heal: {len(pairs)} gray pairs but no provider configured "
                "(set ai_api_key); nothing done"
            )
            return 1
        verdicts = judge(pairs)
        print(f"heal dry-run: {len(pairs)} gray pairs over {args.days}d")
        for pair in pairs:
            verdict = verdicts.get((pair.from_id, pair.to_id))
            if verdict is None:
                label, reason = "SIN VEREDICTO", "el juez no respondió este par"
            else:
                label = "MISMA" if verdict.mismo else "DISTINTA"
                reason = verdict.razon
            print(
                f"  {pair.score:.3f}  {pair.from_id} -> {pair.to_id}  {label}"
                f"  | {pair.title_a[:60]}  <>  {pair.title_b[:60]}"
                f"  | {reason}"
            )
        print("dry-run: nada fusionado ni registrado (--apply para ejecutar)")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
