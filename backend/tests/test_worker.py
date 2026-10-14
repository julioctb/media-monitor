"""Worker adapter-wiring tests (no scheduler start, no network)."""

from datetime import datetime, timedelta, timezone

from app import worker
from app.ingest.facebook_page import FacebookPageCredentials
from app.models import Mention, MentionSource, queries
from app.settings_runtime import EffectiveSettings


def _effective(**overrides) -> EffectiveSettings:
    """Safe defaults: only Google News + GDELT, nothing else configured."""
    return EffectiveSettings(client_id=1, **overrides)


def test_x_provider_disabled_without_key(monkeypatch) -> None:
    monkeypatch.setattr(worker.settings, "x_provider_api_key", "")
    adapters = worker.build_adapters(_effective())
    names = [a.name for a in adapters]
    assert names == ["google_news", "gdelt"]


def test_x_provider_enabled_with_key(monkeypatch) -> None:
    monkeypatch.setattr(worker.settings, "x_provider_api_key", "secret")
    monkeypatch.setattr(
        worker.settings, "x_provider_base_url", "https://api.twitterapi.io"
    )
    monkeypatch.setattr(worker.settings, "x_provider_rate_per_min", 5.0)
    adapters = worker.build_adapters(_effective())
    names = [a.name for a in adapters]
    assert names == ["google_news", "gdelt", "x_twitter"]
    # Construction must not open connections.
    assert adapters[2].search_url == "https://api.twitterapi.io/twitter/tweet/advanced_search"


def test_gdelt_disabled_by_settings(monkeypatch) -> None:
    monkeypatch.setattr(worker.settings, "x_provider_api_key", "")
    adapters = worker.build_adapters(_effective(gdelt_enabled=False))
    assert [a.name for a in adapters] == ["google_news"]


def test_facebook_pages_disabled_without_config(monkeypatch) -> None:
    monkeypatch.setattr(worker.settings, "x_provider_api_key", "")
    adapters = worker.build_adapters(_effective())
    assert [a.name for a in adapters] == ["google_news", "gdelt"]


def test_facebook_pages_enabled_from_settings(monkeypatch) -> None:
    monkeypatch.setattr(worker.settings, "x_provider_api_key", "")
    pages = (FacebookPageCredentials(page_id="1001", token="t", label="L"),)
    adapters = worker.build_adapters(_effective(facebook_pages=pages))
    assert [a.name for a in adapters] == ["google_news", "gdelt", "facebook_page"]
    # Construction must not open connections; the URL carries the pin.
    assert (
        adapters[2].posts_url("1001")
        == "https://graph.facebook.com/v26.0/1001/posts"
    )


def test_rss_feeds_enabled_from_settings(monkeypatch) -> None:
    monkeypatch.setattr(worker.settings, "x_provider_api_key", "")
    adapters = worker.build_adapters(
        _effective(rss_feeds=("https://example.com/feed.xml",))
    )
    assert [a.name for a in adapters] == ["google_news", "gdelt", "rss_custom"]


def test_cycle_sentiment_analyzer_from_pinned_settings() -> None:
    from app.settings_runtime import _cycle_cache

    _cycle_cache[7] = EffectiveSettings(
        client_id=7, ai_provider="openai", ai_api_key="k", ai_fallback_local=False
    )
    try:
        analyzer = worker.cycle_sentiment_analyzer(7)
        assert analyzer.model_name  # ApiSentimentAnalyzer built from settings
    finally:
        _cycle_cache.pop(7, None)


def _pin(client_id: int, **overrides) -> None:
    from app.settings_runtime import _cycle_cache

    _cycle_cache[client_id] = EffectiveSettings(client_id=client_id, **overrides)


def _unpin(client_id: int) -> None:
    from app.settings_runtime import _cycle_cache

    _cycle_cache.pop(client_id, None)


def test_cycle_enricher_built_for_openai_provider() -> None:
    _pin(7, ai_provider="openai", ai_api_key="k", enrich_max_per_cycle=12)
    try:
        enricher, cap = worker.cycle_enricher(7)
        assert enricher is not None
        assert enricher.model_name
        assert cap == 12
        enricher.close()
    finally:
        _unpin(7)


def test_cycle_enricher_none_for_local_provider() -> None:
    _pin(7)  # defaults: ai_provider local, no key
    try:
        enricher, cap = worker.cycle_enricher(7)
        assert enricher is None
        assert cap == 50  # documented default cap
    finally:
        _unpin(7)


def test_cycle_enricher_none_without_key(monkeypatch) -> None:
    _pin(7, ai_provider="openai", ai_api_key="")
    try:
        enricher, _cap = worker.cycle_enricher(7)
        assert enricher is None
    finally:
        _unpin(7)


def _seed_mention(
    session,
    client_id: int,
    url: str,
    *,
    published: datetime | None,
    source=MentionSource.news_rss,
) -> Mention:
    mention = Mention(
        client_id=client_id,
        source=source,
        url=url,
        url_hash=f"hash-{url}",
        published_at=published,
    )
    session.add(mention)
    session.commit()
    return mention


def test_retention_purge_job_disabled_at_zero(monkeypatch, session) -> None:
    client = queries.get_or_create_client(session, "default")
    row = queries.get_settings(session, client.id)
    row.retention_days = 0
    session.commit()
    monkeypatch.setattr(worker, "SessionLocal", lambda: session)

    _seed_mention(
        session,
        client.id,
        "https://a/old",
        published=datetime.now(tz=timezone.utc) - timedelta(days=90),
    )

    assert worker.retention_purge_job() is None
    assert queries.count_mentions(session, client.id) == 1


def test_retention_purge_job_removes_only_old_rows(monkeypatch, session) -> None:
    client = queries.get_or_create_client(session, "default")
    row = queries.get_settings(session, client.id)
    row.retention_days = 7
    session.commit()
    monkeypatch.setattr(worker, "SessionLocal", lambda: session)
    now = datetime.now(tz=timezone.utc)

    _seed_mention(session, client.id, "https://a/old", published=now - timedelta(days=30))
    _seed_mention(session, client.id, "https://a/old-undated", published=None)
    kept = _seed_mention(session, client.id, "https://a/new", published=now - timedelta(days=1))

    removed = worker.retention_purge_job()

    # old + the undated row (no publication date -> swept) are removed.
    assert removed == 2
    remaining = queries.list_mentions(session, client.id)
    assert [m.id for m in remaining] == [kept.id]
