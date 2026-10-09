"""AI spike-summary tests: mocked provider, degraded paths, dedupe (T3)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Client, SavedSearch, queries
from app.spike.summary import (
    DEFAULT_TOP_MENTIONS,
    build_summary_generator,
    summarize_spike,
)

NOW = datetime(2026, 10, 11, 12, 30, tzinfo=timezone.utc)


@pytest.fixture()
def env(session):
    client = Client(name="acme")
    session.add(client)
    session.commit()
    saved = SavedSearch(client_id=client.id, name="brand", query="brand")
    session.add(saved)
    session.commit()
    from app.models import SpikeEvent

    event = SpikeEvent(
        client_id=client.id,
        saved_search_id=saved.id,
        window_start=NOW - timedelta(hours=1),
        window_end=NOW,
        count=12,
        baseline_mean=1.0,
        baseline_stddev=0.0,
        zscore=11.0,
    )
    session.add(event)
    session.commit()
    from app.models import Mention, MentionSource
    from app.models.mention import make_url_hash

    url = f"https://example.com/seed/{NOW.isoformat()}"
    session.add(
        Mention(
            client_id=client.id,
            source=MentionSource.news_rss,
            url=url,
            url_hash=make_url_hash(url),
            title="Brand seed mention",
            content="body",
            published_at=NOW - timedelta(minutes=30),
        )
    )
    session.commit()
    return client, saved, event


def test_summary_stored_on_event(session, env):
    client, saved, event = event_row = env
    calls = []

    def fake_generate(prompt: str) -> str:
        calls.append(prompt)
        return "  Coverage of the launch surged.  "

    result = summarize_spike(session, event, generate=fake_generate, now=NOW)
    assert result == "Coverage of the launch surged."
    assert event.summary == "Coverage of the launch surged."
    assert event.summary_created_at == NOW
    assert len(calls) == 1
    # The prompt carries the spike context for the model.
    assert "12" in calls[0] and "mentions" in calls[0].lower()


def test_dedupe_one_summary_per_event(session, env):
    client, saved, event = env
    calls = []

    def fake_generate(prompt: str) -> str:
        calls.append(prompt)
        return "summary"

    assert summarize_spike(session, event, generate=fake_generate, now=NOW) == "summary"
    assert summarize_spike(session, event, generate=fake_generate, now=NOW) == "summary"
    assert len(calls) == 1  # second call reused the stored summary


def test_empty_generator_output_stays_summary_less(session, env):
    _, _, event = env
    assert summarize_spike(session, event, generate=lambda p: "  ", now=NOW) is None
    assert event.summary is None


def test_provider_failure_degrades_without_raising(session, env):
    _, _, event = env

    def boom(prompt: str) -> str:
        raise RuntimeError("provider down")

    assert summarize_spike(session, event, generate=boom, now=NOW) is None
    assert event.summary is None  # event stays summary-less
    assert event.summary_created_at is None


def test_no_usable_provider_returns_none(session, env):
    client, _, event = env
    queries.upsert_settings(session, client.id, {"ai_provider": "local"})
    assert summarize_spike(session, event, now=NOW) is None
    assert event.summary is None


def test_top_n_caps_prompt_mentions(session, env):
    from app.models import Mention, MentionSource
    from app.models.mention import make_url_hash

    client, saved, event = env
    for index in range(DEFAULT_TOP_MENTIONS + 4):
        url = f"https://example.com/m{index}"
        session.add(
            Mention(
                client_id=client.id,
                source=MentionSource.news_rss,
                url=url,
                url_hash=make_url_hash(url),
                title=f"Brand item {index}",
                content="body",
                published_at=event.window_start + timedelta(minutes=index),
            )
        )
    session.commit()

    prompts: list[str] = []

    def fake_generate(prompt: str) -> str:
        prompts.append(prompt)
        return "s"

    summarize_spike(session, event, generate=fake_generate, now=NOW)
    # Capped at 10 mention lines (seed fixture included).
    assert prompts[0].count("\n- ") == DEFAULT_TOP_MENTIONS


def test_build_summary_generator_openai(monkeypatch, session, env):
    from app.spike import summary

    client, _, _ = env
    queries.upsert_settings(
        session,
        client.id,
        {
            "ai_provider": "openai",
            "ai_api_key": "k",
            "ai_base_url": "https://api.example.com/v1",
            "ai_model": "test-model",
        },
    )
    row = queries.get_settings(session, client.id)
    generate = build_summary_generator(row)
    assert callable(generate)

    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "The summary"}}]}

    def fake_post(url, *, headers=None, json=None, timeout=None):  # noqa: A002
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(summary.httpx, "post", fake_post)
    assert generate("prompt body") == "The summary"
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert captured["json"]["model"] == "test-model"
    assert captured["json"]["messages"][-1]["content"] == "prompt body"


def test_build_summary_generator_none_without_key(session, env):
    client, _, _ = env
    queries.upsert_settings(session, client.id, {"ai_provider": "openai"})
    assert build_summary_generator(queries.get_settings(session, client.id)) is None
