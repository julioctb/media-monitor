"""Offline integration of the composed report engine and role-safe transport."""

import copy
import importlib.util
from pathlib import Path

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect

from app.models import Base
from app.settings_runtime import resolve_effective_settings
from app.summaries import builder
from tests.test_digest_advisory_review import (
    configure,
    configure_reviewer,
    wire_response,
)
from tests.test_digest_factual_pipeline import DAY, _material

POLICY = "provider-default-v1"


def stored_settings(session):
    table = Base.metadata.tables["settings"]
    return [tuple(row) for row in session.execute(table.select().order_by(table.c.id))]


@pytest.mark.parametrize("dedicated", [False, True])
def test_public_report_transport_respects_review_role_without_mutating_settings(
    session, monkeypatch, dedicated
):
    client, _ = _material(session)
    configure(session, client)
    if dedicated:
        configure_reviewer(session, client)
    before = stored_settings(session)
    effective = resolve_effective_settings(session, client.id)
    kwargs_before = copy.deepcopy(builder.NO_THINK_CHAT_KWARGS)
    calls = []

    def respond(url, **options):
        calls.append((url, copy.deepcopy(options)))
        return wire_response(url, options)

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.mode == "llm"
    assert row.content["generation"]["review"]["status"] == "passed"
    assert len(calls) == row.content["generation"]["physical_requests"] == 2
    proposal, review = [options["json"] for _, options in calls]
    assert proposal["chat_template_kwargs"] == {"enable_thinking": False}
    if dedicated:
        assert "chat_template_kwargs" not in review
        assert row.content["generation"]["reviewer_transport_policy"] == POLICY
    else:
        assert review["chat_template_kwargs"] == {"enable_thinking": False}
        assert "reviewer_transport_policy" not in row.content["generation"]
    assert all(
        options["timeout"] == 120.0 and options["follow_redirects"] is False
        for _, options in calls
    )
    assert stored_settings(session) == before
    assert resolve_effective_settings(session, client.id) == effective
    assert builder.NO_THINK_CHAT_KWARGS == kwargs_before
    assert set(row.content["generation"]["review"]) == {
        "method",
        "status",
        "input_fingerprint",
        "scope",
        "raw_review",
        "error",
        "fallible",
        "external_truth",
    }


@pytest.mark.parametrize(
    "marker", [None, "generator-v1", "provider-default-v0", POLICY]
)
@pytest.mark.parametrize("dedicated", [False, True])
def test_policy_upgrade_invalidates_only_dedicated_approval_recovery(
    session, monkeypatch, marker, dedicated
):
    client, _ = _material(session)
    configure(session, client)
    if dedicated:
        configure_reviewer(session, client)
    calls = []

    def respond(url, **options):
        calls.append(url)
        return wire_response(url, options)

    monkeypatch.setattr(builder.httpx, "post", respond)
    first = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert first.mode == "llm"
    previous = copy.deepcopy(first.content)
    if marker is None:
        previous["generation"].pop("reviewer_transport_policy", None)
    else:
        previous["generation"]["reviewer_transport_policy"] = marker
    first.content = previous
    session.commit()
    receipt = copy.deepcopy(previous["generation"]["review"])
    before = stored_settings(session)

    def unavailable(_):
        raise RuntimeError("Synthetic proposal unavailable")

    result = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=unavailable
    )
    recover = not dedicated or marker == POLICY
    assert result.mode == ("llm" if recover else "heuristic")
    assert result.content["generation"]["status"] == (
        "plan_recovered" if recover else "source_fallback"
    )
    assert result.content["generation"]["prior_generation"]["review"] == receipt
    assert len(calls) == 2
    assert stored_settings(session) == before
    if recover:
        assert result.content["generation"]["review"] == receipt
        assert result.content["plain_text"] == previous["plain_text"]
    else:
        assert result.content["generation"]["plan"] is None
        assert result.content["brief"]["decisiones"] == []


def test_injected_phase_factory_keeps_existing_keyword_contract(session, monkeypatch):
    client, _ = _material(session)
    configure(session, client)
    configure_reviewer(session, client)
    phases = []

    def factory(effective, *, phase, budget, system_prompt, response_schema):
        phases.append((phase, effective, budget))
        return builder.summary_generator(
            effective,
            budget=budget,
            system_prompt=system_prompt,
            response_schema=response_schema,
        )

    monkeypatch.setattr(builder.httpx, "post", wire_response_adapter)
    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generator_factory=factory
    )
    assert row.mode == "llm"
    assert [phase for phase, _, _ in phases] == ["proposal", "review"]
    assert phases[0][2] is phases[1][2]
    assert phases[0][1].ai_api_key == "fixture-only"
    assert phases[1][1].ai_api_key == "synthetic-reviewer-key-only"


def wire_response_adapter(url, **options):
    return wire_response(url, options)


@pytest.mark.parametrize("plain_retry", [False, True])
def test_dedicated_review_retries_preserve_role_policy_and_hard_request_cap(
    session, monkeypatch, plain_retry
):
    client, _ = _material(session)
    configure(session, client)
    configure_reviewer(session, client)
    calls = []

    def respond(url, **options):
        calls.append((url, copy.deepcopy(options)))
        if not plain_retry or len(calls) == 1:
            return wire_response(url, options)
        raise httpx.ConnectError("Synthetic review unavailable")

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert len(calls) == row.content["generation"]["physical_requests"] == 2
    assert calls[0][1]["json"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "chat_template_kwargs" not in calls[1][1]["json"]
    assert row.mode == ("heuristic" if plain_retry else "llm")


def test_0032_migration_preserves_synthetic_0031_settings(tmp_path):
    """Exercise 0032 itself; historical SQLite FK DDL is a separate gate."""
    migration_path = (
        Path(__file__).parents[1]
        / "migrations/versions/20261031_0032_digest_reviewer_settings.py"
    )
    spec = importlib.util.spec_from_file_location(
        "reviewer_migration_fixture", migration_path
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "0032" and migration.down_revision == "0031"
    engine = create_engine(f"sqlite:///{tmp_path / 'reviewer-migration.sqlite'}")
    metadata = MetaData()
    table = Table(
        "settings",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("ai_model", String(100)),
        Column("ai_api_key", String(500)),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            table.insert(),
            {
                "id": 1,
                "ai_model": "generator-fixture",
                "ai_api_key": "synthetic-generator-only",
            },
        )
        migration.op = Operations(MigrationContext.configure(connection))
        for _ in range(2):
            migration.upgrade()
            actual = (
                connection.exec_driver_sql("SELECT * FROM settings").mappings().one()
            )
            assert dict(actual) == {
                "id": 1,
                "ai_model": "generator-fixture",
                "ai_api_key": "synthetic-generator-only",
                "digest_reviewer_provider": "inherit",
                "digest_reviewer_base_url": None,
                "digest_reviewer_model": None,
                "digest_reviewer_api_key": None,
                "digest_reviewer_revision": None,
            }
            assert len(inspect(connection).get_columns("settings")) == 8
            migration.downgrade()
            assert tuple(connection.execute(table.select()).one()) == (
                1,
                "generator-fixture",
                "synthetic-generator-only",
            )
    engine.dispose()
