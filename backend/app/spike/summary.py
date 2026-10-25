"""AI summaries for spike events (T3).

Provider rules mirror the sentiment stage: the configured `ai_provider`
must be an OpenAI-compatible chat endpoint with a key; `local` (or a
missing key) means NO summary generator — the event simply stays
summary-less. Provider failures degrade to None and never propagate:
alerting on the spike must not depend on the summary.
"""

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Mention, SavedSearch, queries
from app.models.settings import DEFAULT_OPENAI_BASE_URL

log = logging.getLogger("spike.summary")

#: Mentions fed to the summarizer, newest first.
DEFAULT_TOP_MENTIONS = 10
#: Used when the settings row carries no explicit model.
DEFAULT_SUMMARY_MODEL = "gpt-4o-mini"
#: Per-mention body snippet length inside the prompt.
SNIPPET_CHARS = 280
HTTP_TIMEOUT_S = 30

SYSTEM_PROMPT = (
    "You are a media analyst. Summarize what happened in this burst of "
    "mentions. Write 2-4 sentences, in Spanish, factual and neutral. "
    "Do not invent facts beyond the listed items."
)


def _prompt(mentions: list[Mention], event) -> str:
    lines = [
        f"Mentions in the spike window {event.window_start:%Y-%m-%d %H:%M}-"
        f"{event.window_end:%H:%M} UTC ({event.count} total, z={event.zscore:.1f}):"
    ]
    for mention in mentions:
        snippet = (mention.content or mention.title or "").strip()
        if len(snippet) > SNIPPET_CHARS:
            snippet = snippet[:SNIPPET_CHARS].rstrip() + "…"
        lines.append(f"- {mention.title or '(untitled)'} :: {snippet}")
    return "\n".join(lines)


def build_summary_generator(settings_row):
    """Callable prompt->text for the configured provider, else None.

    A None return is the documented 'no provider' degradation, not an
    error: local sentiment models cannot generate text.
    """
    provider = (getattr(settings_row, "ai_provider", "") or "").strip().lower()
    api_key = (getattr(settings_row, "ai_api_key", None) or "").strip()
    if provider != "openai" or not api_key:
        return None
    base_url = (
        getattr(settings_row, "ai_base_url", None) or DEFAULT_OPENAI_BASE_URL
    ).rstrip("/")
    model = getattr(settings_row, "ai_model", None) or DEFAULT_SUMMARY_MODEL

    def generate(prompt: str) -> str:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=HTTP_TIMEOUT_S,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]

    return generate


def summarize_spike(
    session: Session,
    event,
    *,
    top_n: int = DEFAULT_TOP_MENTIONS,
    generate=None,
    now: datetime | None = None,
) -> str | None:
    """Fill event.summary once; returns the summary or None.

    Dedupe: a stored summary is returned as is and the generator is not
    invoked again. Empty output or provider failure leaves the event
    summary-less (summary_created_at stays NULL).
    """
    if event.summary:
        return event.summary
    if generate is None:
        generate = build_summary_generator(queries.get_settings(session, event.client_id))
    if generate is None:
        return None

    saved_search = (
        session.get(SavedSearch, event.saved_search_id)
        if event.saved_search_id is not None
        else None
    )
    filters = queries.saved_search_filters(saved_search) if saved_search else {}
    mentions = list(
        session.scalars(
            select(Mention)
            .where(
                Mention.client_id == event.client_id,
                Mention.published_at >= event.window_start,
                Mention.published_at < event.window_end,
            )
            .order_by(Mention.published_at.desc())
        )
    )
    # Saved-search filters (source/label probes) are cheap to apply in
    # memory at this scale and keep the window query index-friendly.
    source_filter = filters.get("source") or filters.get("sources")
    if source_filter:
        allowed = set(
            source_filter if isinstance(source_filter, list) else [source_filter]
        )
        mentions = [m for m in mentions if str(m.source.value) in allowed]
    mentions = mentions[:top_n]
    if not mentions:
        return None

    try:
        text = str(generate(_prompt(mentions, event))).strip()
    except Exception as exc:  # noqa: BLE001 - summary must never break the scan
        log.warning("spike summary failed for event %s: %s", event.id, exc)
        return None
    if not text:
        return None
    event.summary = text
    event.summary_created_at = now or datetime.now(tz=timezone.utc)
    return text
