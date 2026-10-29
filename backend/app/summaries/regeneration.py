"""Generate detached candidates without committing into the source database."""

import copy
from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.queries import get_daily_summary, get_settings
from app.summaries.builder import build_daily_summary, day_window


def _preserved_window(content, day):
    try:
        tz_name = content["timezone"]
        ZoneInfo(tz_name)
        window = content["window"]
        start = datetime.fromisoformat(window["from"])
        end = datetime.fromisoformat(window["to"])
        canonical_end = day_window(day, tz_name)[1]
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("Naive stored window")
        if start >= end or end != canonical_end:
            raise ValueError("Stored window end cannot be reproduced")
        anchor = content.get("window_start")
        if anchor and datetime.fromisoformat(anchor) != start:
            raise ValueError("Conflicting stored window anchor")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid or unavailable stored report window") from exc
    return tz_name, start, end


class CandidateGenerationError(RuntimeError):
    """A failed current call is not an accepted historical replacement."""

    def __init__(self, calls):
        super().__init__("No fresh accepted model analysis was generated")
        self.calls = copy.deepcopy(calls)


def generate_candidate(
    source_engine: Engine,
    *,
    client_id: int,
    day: date,
    generate: Callable[[str], str] | None = None,
    generator_factory: Callable | None = None,
) -> dict:
    """Run all builder hooks in a fresh, disposable SQLite clone."""
    if not callable(generate) and not callable(generator_factory):
        raise TypeError("An explicit generation callable is required")
    if generate is not None and generator_factory is not None:
        raise TypeError("Choose one explicit generation callable or factory")
    if source_engine.dialect.name != "sqlite":
        raise ValueError("Candidate sources must be owned SQLite snapshots")
    clone = create_engine("sqlite://", poolclass=StaticPool)
    try:
        with source_engine.connect() as original, clone.connect() as destination:
            original.connection.driver_connection.backup(
                destination.connection.driver_connection
            )
        with Session(clone, expire_on_commit=False) as session:
            existing = get_daily_summary(session, client_id, day)
            if existing is None:
                raise ValueError("An existing target report is required")
            tz_name, start, end = _preserved_window(existing.content, day)
            get_settings(session, client_id).timezone = tz_name
            existing.content = {
                "date": day.isoformat(),
                "timezone": tz_name,
                "window": {"from": start.isoformat(), "to": end.isoformat()},
                "window_start": start.isoformat(),
            }
            existing.narrative = ""
            existing.mode = "heuristic"
            session.commit()
            calls = []

            def track(adapter, phase):
                def tracked(prompt: str) -> str:
                    session.commit()
                    call = {
                        "phase": phase,
                        "prompt": prompt,
                        "completion": None,
                        "error": None,
                    }
                    calls.append(call)
                    try:
                        text = adapter(prompt)
                        call["completion"] = text
                    except Exception as exc:
                        call["error"] = type(exc).__name__
                        raise
                    return text

                return tracked

            def tracked_factory(effective, **options):
                adapter = generator_factory(effective, **options)
                return track(adapter, options["phase"]) if callable(adapter) else None

            row = build_daily_summary(
                session,
                client_id=client_id,
                day=day,
                generate=track(generate, "proposal") if callable(generate) else None,
                generator_factory=tracked_factory
                if callable(generator_factory)
                else None,
            )
            receipt = row.content.get("generation", {})
            if (
                row.mode != "llm"
                or receipt.get("status") != "plan_applied"
                or (receipt.get("review") or {}).get("status") != "passed"
                or [call["phase"] for call in calls] != ["proposal", "review"]
                or any(call["error"] for call in calls)
            ):
                raise CandidateGenerationError(calls)
            return {
                "content": copy.deepcopy(row.content),
                "narrative": row.narrative,
                "mode": row.mode,
                "calls": copy.deepcopy(calls),
            }
    finally:
        clone.dispose()
