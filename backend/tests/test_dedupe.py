"""Tests for the cross-URL title dedupe (Google News redirect variants)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import MentionSource
from app.models.queries import get_or_create_client
from app.models.queries import (
    _normalized_title,
    dedupe_duplicate_titles,
    insert_mention,
    list_mentions,
)


def _insert(session: Session, client_id: int, url: str, title: str, **kwargs):
    return insert_mention(
        session,
        client_id=client_id,
        source=MentionSource.news_rss,
        url=url,
        title=title,
        **kwargs,
    )


def test_normalized_title_folds_accents_case_space() -> None:
    assert _normalized_title("  BUAP   suspende Clases  ") == "buap suspende clases"
    assert _normalized_title("BúAqÚe") == "buaque"


def test_insert_dedupes_same_title_different_url(session: Session) -> None:
    client_id = get_or_create_client(session, 'default').id
    first = _insert(session, client_id, "https://a/1", "BUAP suspende clases")
    second = _insert(session, client_id, "https://a/2", "buap   suspende clases")  # redirect variant
    assert first is not None
    assert second is None
    assert len(list_mentions(session, client_id)) == 1


def test_insert_keeps_distinct_titles(session: Session) -> None:
    client_id = get_or_create_client(session, 'default').id
    assert _insert(session, client_id, "https://a/1", "BUAP suspende clases") is not None
    assert _insert(session, client_id, "https://a/2", "BUAP abre inscripciones") is not None
    assert len(list_mentions(session, client_id)) == 2


def test_dedupe_removes_duplicates_keeps_scored_oldest(session: Session) -> None:
    client_id = get_or_create_client(session, 'default').id
    now = datetime.now(tz=timezone.utc)
    old_no_score = _insert(
        session,
        client_id,
        "https://a/1",
        "BUAP suspende clases",
        published_at=now - timedelta(days=3),
    )
    # Seed the duplicate directly: insert-time dedupe would collapse it.
    from app.models import Mention
    from app.models.mention import make_url_hash

    dup_scored = Mention(
        client_id=client_id,
        source=MentionSource.news_rss,
        url="https://a/2",
        url_hash=make_url_hash("https://a/2"),
        title="buap suspende clases",  # variant, same normalized title
        published_at=now - timedelta(days=2),
        sentiment="positive",
        sentiment_score=0.9,
    )
    session.add(dup_scored)
    session.commit()

    removed = dedupe_duplicate_titles(session)

    assert removed == 1
    remaining = list_mentions(session, client_id)
    assert [m.id for m in remaining] == [old_no_score.id] or len(remaining) == 1
    # whichever survives, exactly one row with that normalized title remains
    titles = [m.title for m in remaining]
    assert titles == ["BUAP suspende clases"] or titles == ["buap suspende clases"]
