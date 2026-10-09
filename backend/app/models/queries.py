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
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AlertSettings,
    Client,
    ClientSettings,
    Keyword,
    Mention,
    MentionClassification,
    MentionSource,
    SavedSearch,
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
    sources: Sequence[MentionSource | str] | None = None,
    sentiment=None,
    sentiment_null: bool = False,
    keyword_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    q: str | None = None,
    ingested_since: datetime | None = None,
    classifier: str | None = None,
    label: str | None = None,
):
    """Single WHERE builder for every mention read: client scope first, then
    the optional filters shared by list/count/aggregation helpers."""
    stmt = stmt.where(Mention.client_id == client_id)
    if source is not None:
        stmt = stmt.where(Mention.source == source)
    if sources:
        # Multi-source saved searches; the values are tags, not enum members.
        stmt = stmt.where(Mention.source.in_(sources))
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
    if classifier is not None or label is not None:
        # Correlated EXISTS: mention carries a row for this classifier
        # (and label when given). Unique(mention, classifier) keeps it cheap.
        classification_probe = select(MentionClassification.id).where(
            MentionClassification.mention_id == Mention.id
        )
        if classifier is not None:
            classification_probe = classification_probe.where(
                MentionClassification.classifier == classifier
            )
        if label is not None:
            classification_probe = classification_probe.where(
                MentionClassification.label == label
            )
        stmt = stmt.where(classification_probe.exists())
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
    classifier: str | None = None,
    label: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[Mention]:
    """Client-scoped mention feed with filters, newest first.

    sentiment filters on an exact value; sentiment_null selects rows without
    a classification yet; q is a case-insensitive substring match over
    title/content; ingested_since filters on the ingest watermark;
    classifier/label require a matching mention_classifications row.
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
        classifier=classifier,
        label=label,
    )
    # Eager-load classifications: the API serializes them on every row and
    # selectinload keeps it at two queries regardless of page size.
    stmt = stmt.options(selectinload(Mention.classifications))
    stmt = stmt.order_by(Mention.published_at.desc().nullslast()).limit(limit).offset(
        offset
    )
    return session.scalars(stmt).all()


def count_mentions(
    session: Session,
    client_id: int,
    *,
    source: MentionSource | None = None,
    sources: Sequence[MentionSource | str] | None = None,
    sentiment: Sentiment | None = None,
    sentiment_null: bool = False,
    keyword_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    q: str | None = None,
    ingested_since: datetime | None = None,
    classifier: str | None = None,
    label: str | None = None,
) -> int:
    """Count of mentions matching the exact same filters as list_mentions."""
    stmt = _mention_filters(
        select(func.count()),
        client_id=client_id,
        source=source,
        sources=sources,
        sentiment=sentiment,
        sentiment_null=sentiment_null,
        keyword_id=keyword_id,
        since=since,
        until=until,
        q=q,
        ingested_since=ingested_since,
        classifier=classifier,
        label=label,
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


def mention_timestamps(
    session: Session,
    client_id: int,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    **filters: object,
) -> list[datetime]:
    """Publication timestamps under the shared filters (client-side bucketing).

    Used by the spike scan: hourly buckets are built in Python so no
    dialect-specific date truncation leaks into the WHERE layer. Extra
    kwargs forward to _mention_filters (source(s), q, classifier, ...).
    Rows without publication date cannot sit in a time bucket and are
    excluded here, not by the caller.
    """
    stmt = _mention_filters(
        select(Mention.published_at),
        client_id=client_id,
        since=since,
        until=until,
        **filters,
    ).where(Mention.published_at.is_not(None))
    return list(session.scalars(stmt))


# ------------------------------------------------------------ classifications


def upsert_classification(
    session: Session,
    *,
    mention_id: int,
    classifier: str,
    label: str,
    score: float,
) -> None:
    """Store one classifier's label for a mention, replacing any old value.

    Delete + insert scoped to (mention_id, classifier): other classifiers'
    rows are untouched. Does not commit; the caller owns the transaction
    boundary (pipeline commits per mention, backfill per batch).
    """
    session.execute(
        delete(MentionClassification).where(
            MentionClassification.mention_id == mention_id,
            MentionClassification.classifier == classifier,
        )
    )
    session.add(
        MentionClassification(
            mention_id=mention_id,
            classifier=classifier,
            label=label,
            score=score,
        )
    )


def classifications_by_mention(
    session: Session,
    mention_ids: Sequence[int],
    *,
    classifier: str | None = None,
) -> dict[int, list[MentionClassification]]:
    """Batch-load classifications grouped by mention id (no lazy N+1)."""
    if not mention_ids:
        return {}
    stmt = select(MentionClassification).where(
        MentionClassification.mention_id.in_(mention_ids)
    )
    if classifier is not None:
        stmt = stmt.where(MentionClassification.classifier == classifier)
    grouped: dict[int, list[MentionClassification]] = {}
    for row in session.scalars(stmt):
        grouped.setdefault(row.mention_id, []).append(row)
    return grouped


def classification_breakdown(
    session: Session, *, client_id: int, classifier: str
) -> dict[str, int]:
    """label -> mention count for one classifier, client-scoped.

    Labels absent from the result simply have no rows; callers zero-fill
    if they need a stable key set.
    """
    stmt = (
        select(MentionClassification.label, func.count())
        .join(Mention, MentionClassification.mention_id == Mention.id)
        .where(
            Mention.client_id == client_id,
            MentionClassification.classifier == classifier,
        )
        .group_by(MentionClassification.label)
    )
    return {label: count for label, count in session.execute(stmt).all()}


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


# ------------------------------------------------------------ saved searches
# Validation mirrors the settings _validate_* helpers: the queries layer owns
# the rules so every writer (API now, workers later) gets identical ones.

_SAVED_SOURCE_VALUES = frozenset(s.value for s in MentionSource)


def _validate_saved_search_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("name must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("name must not be empty")
    if len(cleaned) > 200:
        raise ValueError("name must be at most 200 characters")
    return cleaned


def _validate_saved_search_query(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("query must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("query must not be empty")
    if len(cleaned) > 500:
        raise ValueError("query must be at most 500 characters")
    return cleaned


def _validate_saved_search_sources(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("sources must be a list of source tags")
    sources: list[str] = []
    for entry in value:
        tag = entry.value if isinstance(entry, MentionSource) else entry
        if not isinstance(tag, str) or tag not in _SAVED_SOURCE_VALUES:
            raise ValueError(
                f"sources entries must be one of {', '.join(sorted(_SAVED_SOURCE_VALUES))}"
            )
        if tag not in sources:
            sources.append(tag)
    return sources


def _validate_saved_search_tag(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    cleaned = value.strip()
    if len(cleaned) > 32:
        raise ValueError(f"{field} must be at most 32 characters")
    return cleaned or None


def _validate_saved_search_range_days(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("range_days must be an integer")
    if not 1 <= value <= 365:
        raise ValueError("range_days must be between 1 and 365")
    return value


_SAVED_SEARCH_VALIDATORS = {
    "name": _validate_saved_search_name,
    "query": _validate_saved_search_query,
    "sources": _validate_saved_search_sources,
    "classifier": lambda v: _validate_saved_search_tag(v, "classifier"),
    "label": lambda v: _validate_saved_search_tag(v, "label"),
    "range_days": _validate_saved_search_range_days,
    "is_active": lambda v: _validate_bool(v, "is_active"),
}


def validated_saved_search_changes(
    changes: Mapping[str, object], *, partial: bool
) -> dict[str, object]:
    """Validate saved-search fields; raises ValueError on bad values.

    partial=False fills the documented defaults for absent optional fields
    (create path); partial=True only validates the keys present (update).
    Unknown keys are ignored, mirroring upsert_settings.
    """
    validated: dict[str, object] = {}
    for field, validator in _SAVED_SEARCH_VALIDATORS.items():
        if field in changes:
            validated[field] = validator(changes[field])
        elif not partial and field not in ("name", "query"):
            default = {
                "sources": [],
                "classifier": None,
                "label": None,
                "range_days": 7,
                "is_active": True,
            }[field]
            validated[field] = default
    return validated


def saved_search_filters(saved_search) -> dict[str, object]:
    """Keyword arguments for _mention_filters implementing this search.

    The single chokepoint between a stored SavedSearch and the shared WHERE
    builder: single-source searches use the `source` equality filter, larger
    sets the `sources` membership filter, and the query text maps to `q`.
    """
    filters: dict[str, object] = {}
    if saved_search.query:
        filters["q"] = saved_search.query
    sources = list(saved_search.sources or [])
    if len(sources) == 1:
        filters["source"] = sources[0]
    elif sources:
        filters["sources"] = sources
    if saved_search.classifier:
        filters["classifier"] = saved_search.classifier
    if saved_search.label:
        filters["label"] = saved_search.label
    return filters


def list_saved_searches(
    session: Session, client_id: int, *, active_only: bool = False
) -> Sequence[SavedSearch]:
    """Saved searches for one client, stable name order."""
    stmt = select(SavedSearch).where(SavedSearch.client_id == client_id)
    if active_only:
        stmt = stmt.where(SavedSearch.is_active.is_(True))
    return session.scalars(stmt.order_by(SavedSearch.name, SavedSearch.id)).all()


def get_saved_search(
    session: Session, saved_search_id: int, client_id: int
) -> SavedSearch | None:
    """One saved search owned by the client, else None."""
    return session.scalar(
        select(SavedSearch).where(
            SavedSearch.id == saved_search_id, SavedSearch.client_id == client_id
        )
    )
