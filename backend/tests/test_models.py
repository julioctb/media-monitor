"""Domain model tests: schema constraints, client scoping, dedupe helper."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    AlertSettings,
    AlertDigest,
    Client,
    Keyword,
    Mention,
    MentionSource,
    Sentiment,
    make_url_hash,
    queries,
)


@pytest.fixture()
def client(session) -> Client:
    c = Client(name="acme")
    session.add(c)
    session.commit()
    return c


def _mention(client_id: int, url: str, **kwargs) -> Mention:
    defaults = dict(
        client_id=client_id,
        source=MentionSource.news_rss,
        url=url,
        url_hash=make_url_hash(url),
        title="Brand mentioned",
    )
    defaults.update(kwargs)
    return Mention(**defaults)


def test_create_full_mention_row(session, client) -> None:
    kw = Keyword(client_id=client.id, text="acme", language="es")
    session.add(kw)
    session.flush()

    m = _mention(
        client.id,
        "https://example.com/news/1",
        keyword_id=kw.id,
        external_id="ext-1",
        content="long text",
        author="author",
        lang="es",
        published_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        sentiment=Sentiment.positive,
        sentiment_score=0.87,
        reach=1500,
        raw={"foo": "bar"},
    )
    session.add(m)
    session.commit()

    stored = session.get(Mention, m.id)
    assert stored is not None
    assert stored.source == MentionSource.news_rss
    assert stored.sentiment is Sentiment.positive
    assert stored.raw == {"foo": "bar"}
    assert stored.ingested_at is not None
    assert stored.keyword_id == kw.id


def test_mention_keyword_nullable_and_cascade(session, client) -> None:
    kw = Keyword(client_id=client.id, text="acme")
    session.add(kw)
    session.flush()
    m = _mention(client.id, "https://example.com/a", keyword_id=kw.id)
    session.add(m)
    session.commit()

    session.delete(kw)
    session.commit()
    assert session.get(Mention, m.id).keyword_id is None


def test_keywords_unique_per_client(session, client) -> None:
    session.add(Keyword(client_id=client.id, text="acme"))
    session.add(Keyword(client_id=client.id, text="acme"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_mentions_url_hash_unique(session, client) -> None:
    # utm params are stripped by normalization: both URLs share one hash.
    session.add(_mention(client.id, "https://example.com/x"))
    session.commit()
    session.add(_mention(client.id, "https://example.com/x?utm_source=rss"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(_mention(client.id, "https://example.com/x"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_url_normalization_variants() -> None:
    assert (
        make_url_hash("https://Example.com/a/")
        == make_url_hash("https://example.com/a")
    )
    assert (
        make_url_hash("https://example.com/a?b=2&a=1")
        == make_url_hash("https://example.com/a?a=1&b=2")
    )
    assert make_url_hash("https://example.com/a") != make_url_hash(
        "https://example.com/b"
    )


def test_client_scoping_and_cascade(session) -> None:
    a = Client(name="a")
    b = Client(name="b")
    session.add_all([a, b])
    session.flush()
    session.add(_mention(a.id, "https://example.com/only-a"))
    session.flush()

    assert len(queries.list_mentions(session, a.id)) == 1
    assert len(queries.list_mentions(session, b.id)) == 0

    session.delete(a)
    session.commit()
    assert session.query(Mention).count() == 0


def test_list_mentions_filters(session, client) -> None:
    session.add_all(
        [
            _mention(
                client.id,
                "https://example.com/1",
                source=MentionSource.gdelt,
                sentiment=Sentiment.negative,
                published_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            ),
            _mention(
                client.id,
                "https://example.com/2",
                source=MentionSource.x_twitter,
                published_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
            ),
        ]
    )
    session.commit()

    only_gdelt = queries.list_mentions(session, client.id, source=MentionSource.gdelt)
    assert len(only_gdelt) == 1 and only_gdelt[0].source is MentionSource.gdelt

    only_negative = queries.list_mentions(
        session, client.id, sentiment=Sentiment.negative
    )
    assert len(only_negative) == 1

    ordered = queries.list_mentions(session, client.id)
    assert [m.url for m in ordered] == [
        "https://example.com/2",
        "https://example.com/1",
    ]

    since = datetime(2026, 10, 2, tzinfo=timezone.utc)
    assert len(queries.list_mentions(session, client.id, since=since)) == 1


def test_insert_mention_dedupes(session, client) -> None:
    first = queries.insert_mention(
        session,
        client_id=client.id,
        source=MentionSource.news_rss,
        url="https://example.com/story",
        title="Story",
    )
    assert first is not None

    dup = queries.insert_mention(
        session,
        client_id=client.id,
        source=MentionSource.news_rss,
        url="https://example.com/story",
        title="Story again",
    )
    assert dup is None
    assert session.query(Mention).count() == 1


def test_list_keywords_active_only(session, client) -> None:
    session.add_all(
        [
            Keyword(client_id=client.id, text="acme", is_active=True),
            Keyword(client_id=client.id, text="old", is_active=False),
        ]
    )
    session.commit()
    active = queries.list_keywords(session, client.id)
    assert [k.text for k in active] == ["acme"]


def test_alert_settings_defaults(session, client) -> None:
    settings = AlertSettings(client_id=client.id, recipient_email="j@example.com")
    session.add(settings)
    session.commit()

    found = queries.get_active_alert_settings(session, client.id)
    assert found is not None
    assert found.digest is AlertDigest.instant
    assert found.is_active is True


def test_get_or_create_client(session) -> None:
    first = queries.get_or_create_client(session, "default")
    second = queries.get_or_create_client(session, "default")
    assert first.id == second.id
    assert session.query(Client).count() == 1
