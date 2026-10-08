"""Client-scoped query and ingest helpers (multi-tenant boundary).

Every mention/keyword read or write in the codebase MUST go through these
helpers (or filter on client_id explicitly) so tenant isolation cannot be
forgotten by later writers (API endpoints, ingest adapters, alert engine).
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AlertSettings, Client, Keyword, Mention, MentionSource, Sentiment
from app.models.mention import make_url_hash


def get_or_create_client(session: Session, name: str) -> Client:
    """Fetch a client by name, creating it if missing."""
    client = session.scalar(select(Client).where(Client.name == name))
    if client is None:
        client = Client(name=name)
        session.add(client)
        session.commit()
    return client


def list_keywords(
    session: Session, client_id: int, *, active_only: bool = True
) -> Sequence[Keyword]:
    """Keywords for one client, optionally limited to active ones."""
    stmt = select(Keyword).where(Keyword.client_id == client_id)
    if active_only:
        stmt = stmt.where(Keyword.is_active.is_(True))
    stmt = stmt.order_by(Keyword.id)
    return session.scalars(stmt).all()


def _mention_filters(
    stmt,
    *,
    client_id: int,
    source=None,
    sentiment=None,
    sentiment_null: bool = False,
    keyword_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    q: str | None = None,
    ingested_since: datetime | None = None,
):
    """Single WHERE builder for every mention read: client scope first, then
    the optional filters shared by list/count/aggregation helpers."""
    stmt = stmt.where(Mention.client_id == client_id)
    if source is not None:
        stmt = stmt.where(Mention.source == source)
    if sentiment is not None:
        stmt = stmt.where(Mention.sentiment == sentiment)
    if sentiment_null:
        stmt = stmt.where(Mention.sentiment.is_(None))
    if keyword_id is not None:
        stmt = stmt.where(Mention.keyword_id == keyword_id)
    if since is not None:
        stmt = stmt.where(Mention.published_at >= since)
    if until is not None:
        stmt = stmt.where(Mention.published_at <= until)
    if ingested_since is not None:
        stmt = stmt.where(Mention.ingested_at >= ingested_since)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Mention.title.ilike(pattern), Mention.content.ilike(pattern))
        )
    return stmt


def list_mentions(
    session: Session,
    client_id: int,
    *,
    source: MentionSource | None = None,
    sentiment: Sentiment | None = None,
    sentiment_null: bool = False,
    keyword_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    q: str | None = None,
    ingested_since: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[Mention]:
    """Client-scoped mention feed with filters, newest first.

    sentiment filters on an exact value; sentiment_null selects rows without
    a classification yet; q is a case-insensitive substring match over
    title/content; ingested_since filters on the ingest watermark.
    """
    stmt = _mention_filters(
        select(Mention),
        client_id=client_id,
        source=source,
        sentiment=sentiment,
        sentiment_null=sentiment_null,
        keyword_id=keyword_id,
        since=since,
        until=until,
        q=q,
        ingested_since=ingested_since,
    )
    stmt = stmt.order_by(Mention.published_at.desc().nullslast()).limit(limit).offset(
        offset
    )
    return session.scalars(stmt).all()


def count_mentions(
    session: Session,
    client_id: int,
    *,
    source: MentionSource | None = None,
    sentiment: Sentiment | None = None,
    sentiment_null: bool = False,
    keyword_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    q: str | None = None,
    ingested_since: datetime | None = None,
) -> int:
    """Count of mentions matching the exact same filters as list_mentions."""
    stmt = _mention_filters(
        select(func.count()),
        client_id=client_id,
        source=source,
        sentiment=sentiment,
        sentiment_null=sentiment_null,
        keyword_id=keyword_id,
        since=since,
        until=until,
        q=q,
        ingested_since=ingested_since,
    )
    return session.scalar(stmt)


def sentiment_breakdown(
    session: Session, client_id: int, *, ingested_since: datetime | None = None
) -> dict[str, int]:
    """Counts per sentiment, zero-filled, plus a "null" bucket for rows the
    analyzer has not classified yet."""
    stmt = (
        select(Mention.sentiment, func.count())
        .where(Mention.client_id == client_id)
        .group_by(Mention.sentiment)
    )
    if ingested_since is not None:
        stmt = stmt.where(Mention.ingested_at >= ingested_since)
    counts: dict[str, int] = {s.value: 0 for s in Sentiment}
    counts["null"] = 0
    for value, count in session.execute(stmt).all():
        key = value.value if value is not None else "null"
        counts[key] = count
    return counts


def source_breakdown(session: Session, client_id: int) -> dict[str, int]:
    """Counts per source, zero-filled for stable chart keys."""
    stmt = (
        select(Mention.source, func.count())
        .where(Mention.client_id == client_id)
        .group_by(Mention.source)
    )
    counts = {source.value: 0 for source in MentionSource}
    for value, count in session.execute(stmt).all():
        counts[value.value] = count
    return counts


def published_dates(
    session: Session, client_id: int, *, since: datetime
) -> list[datetime]:
    """Publication timestamps since `since` (client-side day bucketing)."""
    stmt = (
        select(Mention.published_at)
        .where(
            Mention.client_id == client_id,
            Mention.published_at.is_not(None),
            Mention.published_at >= since,
        )
        .order_by(Mention.published_at)
    )
    return list(session.scalars(stmt))


def insert_mention(
    session: Session,
    *,
    client_id: int,
    source: MentionSource,
    url: str,
    keyword_id: int | None = None,
    external_id: str | None = None,
    title: str | None = None,
    content: str | None = None,
    author: str | None = None,
    lang: str | None = None,
    published_at: datetime | None = None,
    reach: int | None = None,
    raw: dict | None = None,
) -> Mention | None:
    """Insert a mention if its URL was never ingested; return None on dup.

    The url_hash dedupe key is computed here — adapters must NOT set it.
    """
    url_hash = make_url_hash(url)
    existing = session.scalar(select(Mention).where(Mention.url_hash == url_hash))
    if existing is not None:
        return None
    mention = Mention(
        client_id=client_id,
        keyword_id=keyword_id,
        source=source,
        external_id=external_id,
        url=url,
        url_hash=url_hash,
        title=title,
        content=content,
        author=author,
        lang=lang,
        published_at=published_at,
        reach=reach,
        raw=raw,
    )
    session.add(mention)
    try:
        session.commit()
    except IntegrityError:
        # Lost a race against the unique constraint: treat as duplicate.
        session.rollback()
        return None
    return mention


def get_active_alert_settings(session: Session, client_id: int) -> AlertSettings | None:
    """Active email alert configuration for a client, if any."""
    return session.scalar(
        select(AlertSettings).where(
            AlertSettings.client_id == client_id,
            AlertSettings.is_active.is_(True),
        )
    )


def get_alert_settings(session: Session, client_id: int) -> AlertSettings | None:
    """The client's alert configuration row regardless of active flag
    (the API reads it to prefill the settings form)."""
    return session.scalar(
        select(AlertSettings)
        .where(AlertSettings.client_id == client_id)
        .order_by(AlertSettings.id)
    )
