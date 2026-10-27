"""Candidate generation must isolate every commit made by the public builder."""

import copy
import json
from datetime import UTC, date, datetime

import pytest
from app.models import Base, Client, DailySummary, Mention, MentionSource, make_url_hash
from app.models.queries import get_settings
from app.summaries.regeneration import generate_candidate
from sqlalchemy import select

DAY = date(2026, 10, 14)
WINDOW = {
    "from": "2026-10-13T21:00:00-06:00",
    "to": "2026-10-15T00:00:00-06:00",
}


def snapshot_tables(session):
    return copy.deepcopy(
        {
            table.name: session.execute(
                select(table).order_by(*table.primary_key.columns)
            ).all()
            for table in Base.metadata.sorted_tables
        }
    )


@pytest.fixture()
def baseline(session):
    client = Client(name="Synthetic regeneration tenant")
    foreign = Client(name="Unrelated tenant")
    session.add_all([client, foreign])
    session.flush()
    for owner in [client, foreign]:
        url = f"https://synthetic.example/{owner.id}"
        session.add(
            Mention(
                client_id=owner.id,
                source=MentionSource.news_rss,
                url=url,
                url_hash=make_url_hash(url),
                title=f"Synthetic budget hearing {owner.id}",
                content="A public budget hearing was announced for October 15.",
                published_at=datetime(2026, 10, 14, 12, tzinfo=UTC),
                ingested_at=datetime(2026, 10, 14, 13, tzinfo=UTC),
            )
        )
    session.add(
        DailySummary(
            client_id=client.id,
            summary_date=DAY,
            content={
                "date": DAY.isoformat(),
                "timezone": "America/Mexico_City",
                "window": copy.deepcopy(WINDOW),
                "window_start": WINDOW["from"],
            },
            narrative="Rejected original analysis",
            mode="llm",
        )
    )
    session.commit()
    get_settings(session, client.id)
    get_settings(session, foreign.id)
    return session.get_bind(), client.id, foreign.id


def completion(_prompt):
    return json.dumps(
        {
            "headline": "Fresh analysis",
            "agenda": [
                {
                    "when": "15 de octubre",
                    "title": "Synthetic hearing",
                    "status": "confirmed",
                    "source": "Synthetic newsroom",
                }
            ],
        }
    )


def test_candidate_preserves_every_source_table(session, baseline):
    engine, client_id, _ = baseline
    before = snapshot_tables(session)
    candidate = generate_candidate(
        engine, client_id=client_id, day=DAY, generate=completion
    )
    assert candidate["mode"] == "llm"
    assert candidate["narrative"] == "Fresh analysis"
    assert snapshot_tables(session) == before


@pytest.mark.parametrize("failure", ["timeout", "invalid_json", "empty_headline"])
def test_failed_current_call_cannot_publish_recovered_prose(session, baseline, failure):
    from app.summaries.builder import build_daily_summary

    engine, client_id, _ = baseline
    build_daily_summary(session, client_id=client_id, day=DAY, generate=completion)
    before = snapshot_tables(session)

    def failed(_prompt):
        if failure == "timeout":
            raise TimeoutError("Synthetic model timeout")
        if failure == "invalid_json":
            return "not JSON"
        return json.dumps({"headline": ""})

    with pytest.raises(RuntimeError, match="fresh"):
        generate_candidate(engine, client_id=client_id, day=DAY, generate=failed)
    assert snapshot_tables(session) == before


def test_stored_cut_timezone_survives_current_settings_drift(session, baseline):
    engine, client_id, _ = baseline
    settings = get_settings(session, client_id)
    settings.timezone = "UTC"
    session.commit()
    before = snapshot_tables(session)
    candidate = generate_candidate(
        engine, client_id=client_id, day=DAY, generate=completion
    )
    assert candidate["content"]["window"] == WINDOW
    assert candidate["content"]["timezone"] == "America/Mexico_City"
    assert snapshot_tables(session) == before


@pytest.mark.parametrize("problem", ["end", "naive_start", "anchor_conflict"])
def test_invalid_stored_window_is_rejected_before_model_call(
    session, baseline, problem
):
    from app.models.queries import get_daily_summary

    engine, client_id, _ = baseline
    stored = get_daily_summary(session, client_id, DAY)
    content = copy.deepcopy(stored.content)
    if problem == "end":
        content["window"]["to"] = "2026-10-15T01:00:00-06:00"
    elif problem == "naive_start":
        content["window"]["from"] = "2026-10-13T21:00:00"
    else:
        content["window_start"] = "2026-10-13T22:00:00-06:00"
    stored.content = content
    session.commit()
    before = snapshot_tables(session)
    calls = []

    def generate(prompt):
        calls.append(prompt)
        return completion(prompt)

    with pytest.raises(ValueError, match="window"):
        generate_candidate(engine, client_id=client_id, day=DAY, generate=generate)
    assert calls == []
    assert snapshot_tables(session) == before


@pytest.mark.parametrize("generate", [None, "not a callable"])
def test_explicit_generation_callable_is_required(session, baseline, generate):
    engine, client_id, _ = baseline
    before = snapshot_tables(session)
    with pytest.raises(TypeError, match="callable"):
        generate_candidate(engine, client_id=client_id, day=DAY, generate=generate)
    assert snapshot_tables(session) == before


@pytest.mark.parametrize("foreign_target", [False, True])
def test_missing_targets_never_activate_generation(session, baseline, foreign_target):
    engine, client_id, foreign_id = baseline
    before = snapshot_tables(session)
    calls = []
    with pytest.raises(ValueError, match="existing target"):
        generate_candidate(
            engine,
            client_id=foreign_id if foreign_target else client_id,
            day=DAY if foreign_target else date(2026, 10, 15),
            generate=lambda prompt: calls.append(prompt) or completion(prompt),
        )
    assert calls == []
    assert snapshot_tables(session) == before


def test_non_sqlite_source_is_rejected_before_connecting():
    from types import SimpleNamespace

    class ForbiddenSource:
        dialect = SimpleNamespace(name="postgresql")

        def connect(self):
            raise AssertionError("Shared database must never be opened")

    with pytest.raises(ValueError, match="SQLite"):
        generate_candidate(ForbiddenSource(), client_id=1, day=DAY, generate=completion)
