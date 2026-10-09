"""Client-scoped query and ingest helpers (multi-tenant boundary).

Every mention/keyword read or write in the codebase MUST go through these
helpers (or filter on client_id explicitly) so tenant isolation cannot be
forgotten by later writers (API endpoints, ingest adapters, alert engine).
"""

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AlertSettings,
    Client,
    ClientSettings,
    Keyword,
    Mention,
    MentionSource,
    Sentiment,
)
from app.models.mention import make_url_hash
from app.models.settings import AI_PROVIDERS


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

# ------------------------------------------------------------------ settings
# Lazy singleton row per client plus validated upsert. Validation lives here
# (not only in the API pydantic layer) so every writer gets the same rules.

_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def get_settings(session: Session, client_id: int) -> ClientSettings:
    """The client's settings row, created with defaults on first touch."""
    row = session.scalar(
        select(ClientSettings).where(ClientSettings.client_id == client_id)
    )
    if row is None:
        row = ClientSettings(client_id=client_id)
        session.add(row)
        session.commit()
    return row


def _validate_client_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("client_name must be a string")
    cleaned = value.strip()
    if len(cleaned) > 200:
        raise ValueError("client_name must be at most 200 characters")
    return cleaned


def _validate_timezone(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timezone must be a non-empty string")
    cleaned = value.strip()
    try:
        ZoneInfo(cleaned)
    except Exception as exc:  # ValueError / ZoneInfoNotFoundError family
        raise ValueError(f"unknown timezone {cleaned!r}") from exc
    return cleaned


def _validate_retention(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("retention_days must be an integer")
    # 0 disables retention; anything else must be a real window (>= 7 days).
    if value < 0 or 0 < value < 7:
        raise ValueError("retention_days must be 0 (disabled) or >= 7")
    return value


def _validate_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _validate_facebook_pages(value: object) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError("facebook_pages must be a list")
    pages: list[dict] = []
    for entry in value:
        if hasattr(entry, "model_dump"):  # accept pydantic credentials objects
            entry = entry.model_dump()
        if not isinstance(entry, dict):
            raise ValueError("each facebook page must be an object with page_id and token")
        page_id = entry.get("page_id")
        token = entry.get("token")
        label = entry.get("label") or ""
        if not isinstance(page_id, str) or not page_id.strip():
            raise ValueError("each facebook page needs a non-empty page_id")
        if not isinstance(token, str) or not token.strip():
            raise ValueError("each facebook page needs a non-empty token")
        if not isinstance(label, str):
            raise ValueError("facebook page label must be a string")
        pages.append(
            {
                "page_id": page_id.strip(),
                "token": token.strip(),
                "label": label.strip(),
            }
        )
    return pages


def _validate_rss_feeds(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("rss_feeds must be a list of URLs")
    feeds: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            raise ValueError("each rss feed must be a string URL")
        cleaned = entry.strip()
        if not cleaned:
            raise ValueError("rss feed URLs must not be empty")
        if not _URL_RE.match(cleaned):
            raise ValueError(f"rss feed must be an http(s) URL: {cleaned!r}")
        feeds.append(cleaned)
    return feeds


def _validate_ai_provider(value: object) -> str:
    if not isinstance(value, str) or value not in AI_PROVIDERS:
        raise ValueError(f"ai_provider must be one of {', '.join(AI_PROVIDERS)}")
    return value


def _validate_optional_str(value: object, field: str, *, is_url: bool = False) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    cleaned = value.strip()
    if not cleaned:
        return None
    if is_url and not _URL_RE.match(cleaned):
        raise ValueError(f"{field} must be an http(s) URL")
    return cleaned


_VALIDATORS = {
    "client_name": _validate_client_name,
    "timezone": _validate_timezone,
    "retention_days": _validate_retention,
    "gdelt_enabled": lambda v: _validate_bool(v, "gdelt_enabled"),
    "facebook_pages": _validate_facebook_pages,
    "rss_feeds": _validate_rss_feeds,
    "ai_provider": _validate_ai_provider,
    "ai_api_key": lambda v: _validate_optional_str(v, "ai_api_key"),
    "ai_base_url": lambda v: _validate_optional_str(v, "ai_base_url", is_url=True),
    "ai_model": lambda v: _validate_optional_str(v, "ai_model"),
    "ai_fallback_local": lambda v: _validate_bool(v, "ai_fallback_local"),
}


def upsert_settings(
    session: Session, client_id: int, changes: Mapping[str, object]
) -> ClientSettings:
    """Validate and apply a partial settings update, creating the row.

    Raises ValueError with a user-facing message on invalid values; the API
    maps that to 422. Unknown keys are ignored (forward-compatible partial
    updates).
    """
    row = get_settings(session, client_id)
    for field, value in changes.items():
        validator = _VALIDATORS.get(field)
        if validator is None:
            continue
        setattr(row, field, validator(value))
    row.updated_at = datetime.now(tz=timezone.utc)
    session.commit()
    return row


def purge_mentions_before(session: Session, *, client_id: int, older_than: datetime) -> int:
    """Delete client mentions outside the retention window; returns the count.

    Age is measured on the publication date. Rows with no publication date
    cannot be placed in the window and are dropped on the next sweep.
    """
    result = session.execute(
        delete(Mention).where(
            or_(
                Mention.published_at < older_than,
                Mention.published_at.is_(None),
            ),
            Mention.client_id == client_id,
        )
    )
    session.commit()
    return int(result.rowcount or 0)


def retention_cutoff(retention_days: int, *, now: datetime | None = None) -> datetime:
    """Cutoff for the retention purge (shared by the worker job)."""
    moment = now or datetime.now(tz=timezone.utc)
    return moment - timedelta(days=retention_days)
