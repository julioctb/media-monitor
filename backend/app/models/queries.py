"""Client-scoped query and ingest helpers (multi-tenant boundary).

Every mention/keyword read or write in the codebase MUST go through these
helpers (or filter on client_id explicitly) so tenant isolation cannot be
forgotten by later writers (API endpoints, ingest adapters, alert engine).
"""

import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AlertSettings,
    Client,
    ClientSettings,
    DailySummary,
    Event,
    IngestCursor,
    IngestRun,
    Keyword,
    Mention,
    MentionClassification,
    MentionPerson,
    MentionSource,
    Person,
    SavedSearch,
    Sentiment,
)
from app.models.mention import make_url_hash
from app.ingest.matching import fold_text
from app.models.settings import AI_PROVIDERS


def list_ingest_runs(
    session: Session,
    *,
    client_id: int,
    adapter: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list["IngestRun"]:
    """Most recent ledger rows, newest cycle first (gap visibility)."""
    stmt = select(IngestRun).where(IngestRun.client_id == client_id)
    if adapter:
        stmt = stmt.where(IngestRun.adapter_name == adapter)
    if status:
        stmt = stmt.where(IngestRun.status == status)
    return list(
        session.scalars(
            stmt.order_by(
                IngestRun.cycle_started.desc(), IngestRun.id.desc()
            ).limit(limit)
        )
    )


def ingest_since(
    session: Session, *, client_id: int, adapter_name: str
) -> datetime | None:
    """Resume watermark for one adapter: last success minus overlap.

    None when the adapter never succeeded (full window). The caller passes
    this to `SourceAdapter.fetch(keywords, since=...)`.
    """
    row = session.scalar(
        select(IngestCursor).where(
            IngestCursor.client_id == client_id,
            IngestCursor.adapter_name == adapter_name,
        )
    )
    if row is None or row.last_success_at is None:
        return None
    return row.last_success_at - timedelta(minutes=row.overlap_min)


def mark_ingest_success(
    session: Session, *, client_id: int, adapter_name: str, at: datetime
) -> None:
    """Advance the adapter's watermark to `at` (upsert); commit.

    Called ONLY after a clean adapter pass, so a failing source keeps its
    old watermark and its debt stays visible in the ingest ledger.
    """
    row = session.scalar(
        select(IngestCursor).where(
            IngestCursor.client_id == client_id,
            IngestCursor.adapter_name == adapter_name,
        )
    )
    if row is None:
        row = IngestCursor(client_id=client_id, adapter_name=adapter_name)
        session.add(row)
    row.last_success_at = at
    session.commit()


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
        # (and label when given). The (classifier, label) index keeps it cheap.
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


def upsert_classifications(
    session: Session,
    *,
    mention_id: int,
    classifier: str,
    results: Sequence[tuple[str, float]],
) -> None:
    """Store every label of one classifier pass, replacing its old rows.

    Delete + insert scoped to (mention_id, classifier): other classifiers'
    rows are untouched, and a multi-label classifier lands one row per
    label (an empty result just clears the classifier's rows). Does not
    commit; the caller owns the transaction boundary (pipeline commits
    per mention, backfill per batch).
    """
    session.execute(
        delete(MentionClassification).where(
            MentionClassification.mention_id == mention_id,
            MentionClassification.classifier == classifier,
        )
    )
    for label, score in results:
        session.add(
            MentionClassification(
                mention_id=mention_id,
                classifier=classifier,
                label=label,
                score=score,
            )
        )


def upsert_classification(
    session: Session,
    *,
    mention_id: int,
    classifier: str,
    label: str,
    score: float,
) -> None:
    """Store one classifier's label for a mention, replacing any old value.

    Single-label convenience over :func:`upsert_classifications`.
    """
    upsert_classifications(
        session,
        mention_id=mention_id,
        classifier=classifier,
        results=[(label, score)],
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


def _normalized_title(title: str) -> str:
    """Collapse a title to its comparable form: accent/case-folded, single-spaced.

    Shared key for the cross-URL dedupe: the same story syndicated under
    different news.google redirect tokens must collapse to one mention.
    Kept dependency-free (no ingest import) to avoid import cycles.
    """
    decomposed = unicodedata.normalize("NFD", title)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.casefold().split())


def dedupe_duplicate_titles(session: Session) -> int:
    """One-shot cleanup: collapse same client+source+normalized-title rows.

    Keeps the oldest row holding a sentiment score, else the oldest; cascade
    removes dependent classification rows. Returns the removed count.
    """
    removed = 0
    client_ids = session.scalars(select(Client.id)).all()
    for client_id in client_ids:
        rows = session.scalars(
            select(Mention).where(Mention.client_id == client_id)
        ).all()
        groups: dict[tuple, list[Mention]] = defaultdict(list)
        for mention in rows:
            if mention.title:
                key = (mention.source, _normalized_title(mention.title))
                groups[key].append(mention)
        for group in groups.values():
            if len(group) < 2:
                continue
            keep = min(group, key=lambda m: (m.sentiment is None, m.id))
            for mention in group:
                if mention.id != keep.id:
                    session.delete(mention)
                    removed += 1
    session.commit()
    return removed


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
    # Cross-URL dedupe: news.google hands the same article different redirect
    # tokens, so hash equality is not enough. Same client + source + normalized
    # title counts as already-ingested. O(n) scan per insert; revisit with a
    # stored title_norm column if the corpus grows past ~10k rows.
    if title:
        normalized = _normalized_title(title)
        for sibling in session.scalars(
            select(Mention).where(
                Mention.client_id == client_id,
                Mention.source == source,
                Mention.title.is_not(None),
            )
        ):
            if sibling.title and _normalized_title(sibling.title) == normalized:
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


def _validate_digest_hour(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("digest_hour must be an integer")
    if not 0 <= value <= 23:
        raise ValueError("digest_hour must be between 0 and 23")
    return value


def _validate_digest_hours(value: object) -> str:
    """Digest cut hours: 1..8 ints in 0..23, deduped, stored as sorted CSV."""
    if isinstance(value, str):
        # Tolerate hand-edited rows / CSV strings from tooling.
        candidates: list[object] = []
        for part in value.split(","):
            stripped = part.strip()
            if not stripped:
                continue
            try:
                candidates.append(int(stripped))
            except ValueError as exc:
                raise ValueError("digest_hours must be integers between 0 and 23") from exc
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        raise ValueError("digest_hours must be a list of integers")
    hours: list[int] = []
    for entry in candidates:
        if isinstance(entry, bool) or not isinstance(entry, int):
            raise ValueError("digest_hours must be integers between 0 and 23")
        if not 0 <= entry <= 23:
            raise ValueError("digest_hours hours must be between 0 and 23")
        if entry not in hours:
            hours.append(entry)
    if not 1 <= len(hours) <= 8:
        raise ValueError("digest_hours needs between 1 and 8 hours")
    return ",".join(str(h) for h in sorted(hours))


def _validate_focus_person(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("digest_focus_person_id must be a positive id or null")
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


def _validate_scrapers(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("scrapers must be a list of scraper names")
    names: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            raise ValueError("each scraper must be a string name")
        cleaned = entry.strip()
        if not cleaned:
            continue  # normalize: blank entries drop out silently
        names.append(cleaned)
    # Dedupe preserving order; unknown names are filtered by the worker
    # against SCRAPER_REGISTRY (forward-compatible stored values).
    return list(dict.fromkeys(names))


def _validate_ai_provider(value: object) -> str:
    if not isinstance(value, str) or value not in AI_PROVIDERS:
        raise ValueError(f"ai_provider must be one of {', '.join(AI_PROVIDERS)}")
    return value


def _validate_enrich_max(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("enrich_max_per_cycle must be an integer")
    if not 1 <= value <= 1000:
        raise ValueError("enrich_max_per_cycle must be between 1 and 1000")
    return value


def _validate_fetch_max(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("fetch_max_per_cycle must be an integer")
    if not 1 <= value <= 1000:
        raise ValueError("fetch_max_per_cycle must be between 1 and 1000")
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
    "digest_hour": _validate_digest_hour,
    "digest_hours": _validate_digest_hours,
    "digest_focus_person_id": _validate_focus_person,
    "gdelt_enabled": lambda v: _validate_bool(v, "gdelt_enabled"),
    "facebook_pages": _validate_facebook_pages,
    "rss_feeds": _validate_rss_feeds,
    "scrapers": _validate_scrapers,
    "ai_provider": _validate_ai_provider,
    "ai_api_key": lambda v: _validate_optional_str(v, "ai_api_key"),
    "ai_base_url": lambda v: _validate_optional_str(v, "ai_base_url", is_url=True),
    "ai_model": lambda v: _validate_optional_str(v, "ai_model"),
    "enrich_max_per_cycle": _validate_enrich_max,
    "fetch_max_per_cycle": _validate_fetch_max,
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
    # Legacy single hour and the cut list mirror each other when only one
    # of the two is updated, so either write path keeps a coherent row.
    if "digest_hour" in changes and "digest_hours" not in changes:
        row.digest_hours = _validate_digest_hours([row.digest_hour])
    elif "digest_hours" in changes and "digest_hour" not in changes:
        row.digest_hour = int(str(row.digest_hours).split(",")[0])
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


# ------------------------------------------------------------------- events


def list_events(
    session: Session,
    client_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
    since: datetime | None = None,
    min_mentions: int = 1,
) -> Sequence[Event]:
    """Client-scoped events, most recently seen first.

    `since` filters on last_seen_at (the event's window, not creation):
    an old event that received mentions after `since` is still listed.
    `min_mentions` keeps only events with at least N mentions — the UI's
    'con eco' view (single-mention events are bare feed duplicates).
    """
    stmt = select(Event).where(Event.client_id == client_id)
    if since is not None:
        stmt = stmt.where(Event.last_seen_at >= since)
    if min_mentions > 1:
        stmt = stmt.where(Event.mention_count >= min_mentions)
    return list(
        session.scalars(
            stmt.order_by(Event.last_seen_at.desc(), Event.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def get_client_event(
    session: Session, *, event_id: int, client_id: int
) -> Event | None:
    """One event owned by the client, else None (tenant-scoped detail)."""
    return session.scalar(
        select(Event).where(Event.id == event_id, Event.client_id == client_id)
    )


def event_mentions(
    session: Session, event_id: int, *, limit: int = 100
) -> Sequence[Mention]:
    """Mentions of one event, biggest reach first (corroborations ranking)."""
    stmt = (
        select(Mention)
        .where(Mention.event_id == event_id)
        .order_by(Mention.reach.desc().nullslast(), Mention.id)
        .limit(limit)
    )
    return list(session.scalars(stmt))


# ------------------------------------------------------------ daily summaries


def get_daily_summary(
    session: Session, client_id: int, day: date
) -> DailySummary | None:
    """The stored summary for one client-day, else None."""
    return session.scalar(
        select(DailySummary).where(
            DailySummary.client_id == client_id, DailySummary.summary_date == day
        )
    )


def list_daily_summaries(session: Session, client_id: int) -> Sequence[DailySummary]:
    """All stored summaries for one client, newest day first."""
    stmt = (
        select(DailySummary)
        .where(DailySummary.client_id == client_id)
        .order_by(DailySummary.summary_date.desc())
    )
    return session.scalars(stmt).all()


def upsert_daily_summary(
    session: Session,
    *,
    client_id: int,
    day: date,
    content: dict,
    narrative: str,
    mode: str,
) -> DailySummary:
    """Insert or overwrite the single summary row for (client, day).

    Regeneration is the documented contract (POST /summaries/generate and
    the nightly job share it), so an existing row gets its fields replaced
    and ``updated_at`` bumped. A concurrent insert losing the race is
    resolved by re-reading and updating instead of raising.
    """
    row = get_daily_summary(session, client_id, day)
    if row is None:
        row = DailySummary(
            client_id=client_id,
            summary_date=day,
            content=content,
            narrative=narrative,
            mode=mode,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            # Concurrent build inserted first: fold into the stored row.
            session.rollback()
            row = get_daily_summary(session, client_id, day)
            if row is None:  # pragma: no cover - row deleted mid-race
                raise
    if row.content != content or row.narrative != narrative or row.mode != mode:
        row.content = content
        row.narrative = narrative
        row.mode = mode
        row.updated_at = datetime.now(tz=timezone.utc)
        session.commit()
    return row


# ------------------------------------------------------------------ coverage


def _outlet_of(url: str | None, author: str | None) -> str:
    """Outlet identity of a mention: hostname of the URL, author fallback."""
    host = urlsplit(url or "").netloc.lower().removeprefix("www.")
    return host or (author or "").strip() or "unknown"


def event_coverage(session: Session, *, event_id: int) -> dict:
    """Coverage of one event: mentions and distinct outlets per source.

    The outlet is the domain of the mention URL (author handle when the
    URL carries no hostname). Events with no mentions return zeros, never
    an error. Rows are ordered by mention count, then source name.
    """
    rows = session.execute(
        select(Mention.source, Mention.url, Mention.author).where(
            Mention.event_id == event_id
        )
    ).all()
    outlets_per_source: dict[MentionSource, set[str]] = defaultdict(set)
    counts: dict[MentionSource, int] = defaultdict(int)
    all_outlets: set[str] = set()
    for source, url, author in rows:
        outlet = _outlet_of(url, author)
        outlets_per_source[source].add(outlet)
        counts[source] += 1
        all_outlets.add(outlet)
    return {
        "mention_count": len(rows),
        "outlet_count": len(all_outlets),
        "by_source": [
            {
                "source": source,
                "n_mentions": counts[source],
                "outlets": len(outlets_per_source[source]),
            }
            for source in sorted(outlets_per_source, key=lambda s: (-counts[s], s.value))
        ],
    }


def client_coverage_summary(
    session: Session, *, client_id: int, days: int = 30
) -> list[dict]:
    """Per-day repetition index: events, mentions, share with >=2 outlets.

    Days are taken from the mention timestamp (published_at, falling back
    to ingested_at) across the last `days` days; an event counts as
    multi-source on a day when its mentions that day span >=2 outlets.
    Days without activity are absent from the result; ascending by date.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rows = session.execute(
        select(Mention.published_at, Mention.ingested_at, Mention.event_id, Mention.url, Mention.author)
        .join(Event, Event.id == Mention.event_id)
        .where(Mention.client_id == client_id, Event.client_id == client_id)
    ).all()
    per_day: dict[date, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    mention_days: dict[date, int] = defaultdict(int)
    for published_at, ingested_at, event_id, url, author in rows:
        when = published_at or ingested_at
        if when is None or event_id is None:
            continue
        if when.tzinfo is None:  # SQLite returns naive datetimes
            when = when.replace(tzinfo=timezone.utc)
        if when < cutoff:
            continue
        day = when.date()
        per_day[day][event_id].add(_outlet_of(url, author))
        mention_days[day] += 1
    summary: list[dict] = []
    for day in sorted(per_day):
        events = per_day[day]
        multi = sum(1 for outlets in events.values() if len(outlets) >= 2)
        total = len(events)
        summary.append(
            {
                "date": day,
                "events": total,
                "mentions": mention_days[day],
                "multi_source_events": multi,
                "repetition_pct": round(100.0 * multi / total, 1) if total else 0.0,
            }
        )
    return summary


# ----------------------------------------------------------------- persons (F3)

PERSON_SORTS = ("mentions", "recent")


def list_persons(
    session: Session,
    client_id: int,
    *,
    sort: str = "mentions",
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Client's persons with mention_count; `mentions` or `recent` order.

    `q` filters by folded substring against the canonical name_key and the
    accumulated alias_keys, so accent-less partial names and alias variants
    both hit. Rows are plain dicts (Person columns + mention_count).
    """
    if sort not in PERSON_SORTS:
        raise ValueError(f"sort must be one of {PERSON_SORTS}")
    count_sq = (
        select(MentionPerson.person_id, func.count().label("mention_count"))
        .join(Mention, Mention.id == MentionPerson.mention_id)
        .where(Mention.client_id == client_id)
        .group_by(MentionPerson.person_id)
        .subquery()
    )
    stmt = select(Person, func.coalesce(count_sq.c.mention_count, 0).label("mention_count")).outerjoin(
        count_sq, count_sq.c.person_id == Person.id
    ).where(Person.client_id == client_id)
    if q:
        folded = fold_text(q.strip())
        if folded:
            pattern = f"%{folded}%"
            stmt = stmt.where(
                or_(Person.name_key.like(pattern), Person.alias_keys.like(pattern))
            )
    if sort == "mentions":
        stmt = stmt.order_by(
            func.coalesce(count_sq.c.mention_count, 0).desc(), Person.name
        )
    else:
        stmt = stmt.order_by(Person.last_seen_at.desc(), Person.id.desc())
    rows = session.execute(stmt.limit(limit).offset(max(0, offset))).all()
    return [
        {
            "id": person.id,
            "name": person.name,
            "name_key": person.name_key,
            "role": person.role,
            "org": person.org,
            "aliases": person.aliases,
            "first_seen_at": person.first_seen_at,
            "last_seen_at": person.last_seen_at,
            "mention_count": count,
        }
        for person, count in rows
    ]


def get_client_person(session: Session, *, person_id: int, client_id: int) -> Person | None:
    """Person row when it belongs to the client, else None (tenant guard)."""
    return session.scalar(
        select(Person).where(Person.id == person_id, Person.client_id == client_id)
    )


def digest_persons(
    session: Session, *, client_id: int, since: datetime, limit: int = 5
) -> list[dict]:
    """Most-mentioned persons inside the digest window, for the email section.

    Counts links whose mention was ingested at/after `since` (the digest
    watermark semantics), client-scoped; empty list when the window has
    none so the caller renders no section at all.
    """
    rows = session.execute(
        select(Person.name, func.count().label("mentions"))
        .select_from(MentionPerson)
        .join(Person, Person.id == MentionPerson.person_id)
        .join(Mention, Mention.id == MentionPerson.mention_id)
        .where(MentionPerson.person_id == Person.id)
        .where(Mention.client_id == client_id, Mention.ingested_at >= since)
        .group_by(Person.id, Person.name)
        .order_by(func.count().desc(), Person.name)
        .limit(limit)
    ).all()
    return [{"name": name, "mentions": count} for name, count in rows]


def person_mention_count(session: Session, *, person_id: int, client_id: int) -> int:
    """Total links for the person within the client (detail header count)."""
    return (
        session.query(func.count())
        .select_from(MentionPerson)
        .join(Mention, Mention.id == MentionPerson.mention_id)
        .filter(MentionPerson.person_id == person_id, Mention.client_id == client_id)
        .scalar()
    )


def person_timeline(
    session: Session,
    *,
    person_id: int,
    client_id: int,
    limit: int = 100,
) -> list[dict]:
    """Chronological footprint of one person (newest first).

    Each row: the mention (id/title/url/source/timestamps/sentiment), the
    per-mention role/org and verbatim quote (`context`), the canonical
    event title when the mention belongs to one, and the political label
    classifier's verdict for that mention (None when unclassified). The
    F3 exit gate: everything the chat answer needs, no inference.
    """
    stmt = (
        select(MentionPerson, Mention)
        .join(Mention, Mention.id == MentionPerson.mention_id)
        .where(
            MentionPerson.person_id == person_id,
            Mention.client_id == client_id,
        )
        .order_by(
            func.coalesce(Mention.published_at, Mention.ingested_at).desc(),
            Mention.id.desc(),
        )
        .limit(limit)
    )
    links = session.execute(stmt).all()
    mention_ids = [mention.id for _, mention in links]
    labels: dict[int, str | None] = {}
    if mention_ids:
        label_rows = session.execute(
            select(MentionClassification.mention_id, MentionClassification.label).where(
                MentionClassification.mention_id.in_(mention_ids),
                MentionClassification.classifier == "political",
            )
        ).all()
        labels = dict(label_rows)
    event_ids = {mention.event_id for _, mention in links if mention.event_id}
    titles: dict[int, str] = {}
    if event_ids:
        titles = dict(
            session.execute(
                select(Event.id, Event.title).where(Event.id.in_(event_ids))
            ).all()
        )
    return [
        {
            "mention_id": mention.id,
            "title": mention.title,
            "url": mention.url,
            "source": mention.source,
            "published_at": mention.published_at,
            "ingested_at": mention.ingested_at,
            "sentiment": mention.sentiment,
            "role": link.role,
            "org": link.org,
            "context": link.context,
            "event_id": mention.event_id,
            "event_title": titles.get(mention.event_id) if mention.event_id else None,
            "political_label": labels.get(mention.id),
        }
        for link, mention in links
    ]
