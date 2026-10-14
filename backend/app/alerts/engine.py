"""Alert engine: newly ingested mentions in, emails out.

Paths, driven by alert_settings.digest:
- instant: run right after every ingest cycle; ONE email batching the
  cycle's new mentions (body capped at MAX_INSTANT_MENTIONS).
- daily/weekly: the cycle only marks pending state; the scheduled jobs in
  app.worker (daily 08:00, Mondays 08:00 America/Mexico_City) send a
  digest with totals plus the latest mentions, then advance the
  last_digest_at watermark and clear digest_pending_since.

User-facing copy is Spanish; identifiers and logs are English.
"""

import html
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.alerts.transport import AlertTransport, SmtpTransport
from app.config import settings
from app.db import SessionLocal
from app.models import (
    AlertDigest,
    AlertSettings,
    Mention,
    MentionSource,
    Sentiment,
    queries,
)

log = logging.getLogger("alerts.engine")

MAX_INSTANT_MENTIONS = 20
DIGEST_TOP_MENTIONS = 5

DIGEST_WINDOW: dict[AlertDigest, timedelta] = {
    AlertDigest.daily: timedelta(days=1),
    AlertDigest.weekly: timedelta(days=7),
}
DIGEST_SUBJECT: dict[AlertDigest, str] = {
    AlertDigest.daily: "Resumen diario de menciones",
    AlertDigest.weekly: "Resumen semanal de menciones",
}

SOURCE_LABELS = {
    MentionSource.news_rss: "Noticias RSS",
    MentionSource.gdelt: "GDELT",
    MentionSource.x_twitter: "X (Twitter)",
    MentionSource.facebook_page: "Facebook",
    MentionSource.rss_custom: "RSS",
}
SENTIMENT_LABELS = {
    Sentiment.positive: "Positiva",
    Sentiment.negative: "Negativa",
    Sentiment.neutral: "Neutral",
}


def _sentiment_label(value: Sentiment | None) -> str:
    return SENTIMENT_LABELS.get(value, "Sin clasificar")


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _mention_rows(
    mentions: Sequence[Mention], group_by_event: bool = False
) -> list[tuple[str, str, str, str]]:
    """(source, title, url, sentiment) tuples for the renderers.

    group_by_event: mentions sharing an event_id collapse into ONE row with
    the canonical title and the event's source count; mentions without an
    event keep their own row (hybrid fallback, cero regresión). Event rows
    go first, loose mentions after, both stable-ordered.
    """
    if not group_by_event:
        return [
            (
                SOURCE_LABELS.get(mention.source, str(mention.source)),
                mention.title or "(sin título)",
                mention.url,
                _sentiment_label(mention.sentiment),
            )
            for mention in mentions
        ]

    def _plain(mention: Mention) -> tuple[str, str, str, str]:
        return (
            SOURCE_LABELS.get(mention.source, str(mention.source)),
            mention.title or "(sin título)",
            mention.url,
            _sentiment_label(mention.sentiment),
        )

    grouped: dict[int, list[Mention]] = {}
    loose: list[tuple[str, str, str, str]] = []
    for mention in mentions:
        if mention.event_id is None:
            loose.append(_plain(mention))
        else:
            grouped.setdefault(mention.event_id, []).append(mention)
    rows: list[tuple[str, str, str, str]] = []
    for members in grouped.values():
        event = members[0].event
        top_link = max(members, key=lambda m: m.reach or 0, default=members[0])
        sources = event.source_count if event is not None else len(members)
        rows.append(
            (
                "Evento",
                event.title if event is not None else members[0].title or "(sin título)",
                top_link.url,
                f"{sources} {'fuente' if sources == 1 else 'fuentes'}",
            )
        )
    rows.extend(loose)
    return rows


def _compose(
    *, intro: list[str], rows: list[tuple[str, str, str, str]], footer: str | None
) -> tuple[str, str]:
    """Plain-text and minimal-HTML bodies for the same content."""
    text_lines: list[str] = []
    html_parts: list[str] = []
    for paragraph in intro:
        text_lines.append(paragraph)
        html_parts.append(f"<p>{html.escape(paragraph)}</p>")
    text_lines.append("")
    html_parts.append("<ul>")
    for source_label, title, url, sentiment_label in rows:
        text_lines.append(f"- [{source_label}] {title} — {url} ({sentiment_label})")
        safe_url = html.escape(url, quote=True)
        html_parts.append(
            f'<li>[{html.escape(source_label)}] '
            f'<a href="{safe_url}">{html.escape(title)}</a> '
            f"({html.escape(sentiment_label)})</li>"
        )
    html_parts.append("</ul>")
    if footer:
        text_lines += ["", footer]
        html_parts.append(f"<p>{html.escape(footer)}</p>")
    return "\n".join(text_lines), "".join(html_parts)


def _send(
    cfg: AlertSettings,
    subject: str,
    text: str,
    html_body: str,
    transport: AlertTransport,
) -> None:
    transport.send(to=cfg.recipient_email, subject=subject, text=text, html=html_body)


def run_alert_cycle(
    session: Session,
    *,
    cycle_started_at: datetime,
    client_id: int | None = None,
    transport: AlertTransport | None = None,
) -> int:
    """Post-ingest hook. Returns the number of emails sent.

    instant: one batched email with this cycle's mentions (capped).
    daily/weekly: pending marker only; the scheduled job sends later.
    """
    client_id = settings.default_client_id if client_id is None else client_id
    cfg = queries.get_active_alert_settings(session, client_id)
    if cfg is None:
        return 0
    new_total = queries.count_mentions(
        session, client_id, ingested_since=cycle_started_at
    )
    if not new_total:
        return 0

    if cfg.digest is not AlertDigest.instant:
        if cfg.digest_pending_since is None:
            cfg.digest_pending_since = datetime.now(tz=timezone.utc)
            session.add(cfg)
            session.commit()
        return 0

    mentions = queries.list_mentions(
        session, client_id, ingested_since=cycle_started_at, limit=MAX_INSTANT_MENTIONS
    )
    subject = (
        f"{settings.app_name} — "
        f"{_plural(new_total, 'mención nueva', 'menciones nuevas')}"
    )
    intro = [
        f"Se detectaron {_plural(new_total, 'mención nueva', 'menciones nuevas')} "
        "para tus palabras clave:"
    ]
    footer = (
        f"…y {new_total - len(mentions)} más en el dashboard."
        if new_total > len(mentions)
        else None
    )
    text, html_body = _compose(intro=intro, rows=_mention_rows(mentions), footer=footer)
    _send(cfg, subject, text, html_body, transport or SmtpTransport.from_settings())
    return 1


def run_digest(
    digest: AlertDigest,
    *,
    session: Session | None = None,
    client_id: int | None = None,
    transport: AlertTransport | None = None,
    now: datetime | None = None,
) -> int:
    """Send the digest for clients configured with this cadence.

    Window: everything ingested since last_digest_at (full period on the
    first run). Advances the watermark and clears the pending marker.
    """
    owns_session = session is None
    session = session if session is not None else SessionLocal()
    now = now or datetime.now(tz=timezone.utc)
    resolved_client = settings.default_client_id if client_id is None else client_id
    try:
        cfg = queries.get_active_alert_settings(session, resolved_client)
        if cfg is None or cfg.digest is not digest:
            return 0
        window_start = cfg.last_digest_at or now - DIGEST_WINDOW[digest]
        total = queries.count_mentions(
            session, resolved_client, ingested_since=window_start
        )
        if not total:
            return 0
        breakdown = queries.sentiment_breakdown(
            session, resolved_client, ingested_since=window_start
        )
        mentions = queries.list_mentions(
            session, resolved_client, ingested_since=window_start,
            limit=DIGEST_TOP_MENTIONS,
        )

        counts_line = (
            f"Positivas: {breakdown['positive']} · "
            f"Neutras: {breakdown['neutral']} · "
            f"Negativas: {breakdown['negative']} · "
            f"Sin clasificar: {breakdown['null']}"
        )
        intro = [
            "Se registraron "
            f"{_plural(total, 'mención nueva', 'menciones nuevas')} "
            "desde el último envío.",
            counts_line,
            "Últimas menciones:",
        ]
        footer = (
            f"…y {total - len(mentions)} más en el dashboard."
            if total > len(mentions)
            else None
        )
        subject = (
            f"{settings.app_name} — {DIGEST_SUBJECT[digest]}: "
            f"{_plural(total, 'mención nueva', 'menciones nuevas')}"
        )
        text, html_body = _compose(
            intro=intro,
            # Hybrid rows: canonical events collapse their corroborations;
            # mentions without an event keep their own row.
            rows=_mention_rows(mentions, group_by_event=True),
            footer=footer,
        )
        _send(cfg, subject, text, html_body, transport or SmtpTransport.from_settings())

        cfg.last_digest_at = now
        cfg.digest_pending_since = None
        session.add(cfg)
        session.commit()
        return 1
    finally:
        if owns_session:
            session.close()


# ------------------------------------------------------- sentiment shift (T4)

#: Comparison window: current vs the immediately preceding window.
SHIFT_WINDOW = timedelta(hours=24)


def _net_share(
    session: Session,
    client_id: int,
    filters: dict,
    *,
    since: datetime,
    until: datetime,
) -> float | None:
    """positive% - negative% over classified mentions, or None if none."""
    counts = {
        sentiment: queries.count_mentions(
            session, client_id, sentiment=sentiment, since=since, until=until, **filters
        )
        for sentiment in Sentiment
    }
    classified = sum(counts.values())
    if not classified:
        return None
    return 100.0 * (counts[Sentiment.positive] - counts[Sentiment.negative]) / classified


def _shift_email(entries: list[tuple]) -> tuple[str, str]:
    """Plain-text + HTML for the shift digest; user-facing copy in Spanish."""
    text_lines = [
        "Cambios relevantes de sentimiento en tus búsquedas guardadas:",
    ]
    html_parts = ["<p>Cambios relevantes de sentimiento en tus búsquedas guardadas:</p><ul>"]
    for saved_search, previous, current, delta in entries:
        line = (
            f"{saved_search.name}: red {previous:+.0f}% → {current:+.0f} "
            f"(variación {delta:+.1f} puntos)"
        )
        text_lines.append(f"- {line}")
        html_parts.append(f"<li>{html.escape(line)}</li>")
    html_parts.append("</ul>")
    return "\n".join(text_lines), "".join(html_parts)


def check_sentiment_shift(
    session: Session,
    *,
    client_id: int,
    now: datetime,
    transport: AlertTransport | None = None,
    window: timedelta = SHIFT_WINDOW,
) -> int:
    """Saved-search sentiment-shift rule; returns 1 when an email went out.

    For every active saved search, the net share (positive% − negative%)
    of the window ending `now` is compared against the previous window; a
    swing >= the configured threshold (percentage points) for any search
    sends ONE batched email. The watermark on the alert settings row keeps
    the rule silent for one window after each send. Disabled
    configuration, missing searches or unclassified-only windows stay
    silent.
    """
    cfg = queries.get_active_alert_settings(session, client_id)
    if cfg is None or not cfg.sentiment_shift_enabled:
        return 0
    if cfg.sentiment_shift_last_sent is not None and now - cfg.sentiment_shift_last_sent < window:
        return 0
    threshold = (
        cfg.sentiment_shift_threshold
        if cfg.sentiment_shift_threshold is not None
        else AlertSettings.__table__.c.sentiment_shift_threshold.default.arg
    )

    entries: list[tuple] = []
    for saved_search in queries.list_saved_searches(session, client_id, active_only=True):
        filters = queries.saved_search_filters(saved_search)
        current = _net_share(
            session, client_id, filters, since=now - window, until=now
        )
        previous = _net_share(
            session, client_id, filters, since=now - 2 * window, until=now - window
        )
        if current is None or previous is None:
            continue
        delta = current - previous
        if abs(delta) >= threshold:
            entries.append((saved_search, previous, current, delta))
    if not entries:
        return 0

    subject = (
        f"{settings.app_name} — Cambio de sentimiento: "
        + ", ".join(saved_search.name for saved_search, _, _, _ in entries)
    )
    text, html_body = _shift_email(entries)
    _send(cfg, subject, text, html_body, transport or SmtpTransport.from_settings())

    cfg.sentiment_shift_last_sent = now
    session.add(cfg)
    session.commit()
    return 1
