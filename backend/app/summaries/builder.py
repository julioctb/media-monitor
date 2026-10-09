"""Daily summary builder (T11).

Deterministic pipeline, always run:

  1. day window in the settings timezone (zoneinfo) over mentions.published_at,
  2. per-source and per-keyword counts plus top titles (newest first, max 3),
  3. silent keywords: active keywords with no mention that day,
  4. Spanish heuristic narrative from a fixed template,
  5. a plain-text render of everything, stored as content["plain_text"]
     so the future RAG chat can chunk the day without parsing JSON.

LLM narrative: when the effective settings select the ``openai`` provider
with an API key, the same chat-completions request shape as the sentiment
analyzer (app.sentiment.api_analyzer) rewrites the narrative in 2-4
journalistic Spanish sentences based only on the computed stats. Any
failure — transport, shape, empty body — falls back to the heuristic
template and ``mode`` stays ``heuristic``. The structured content never
depends on the LLM, which is also skipped for empty days (the template
already says it all; there is nothing to summarize).
"""

import json
import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Mention, queries
from app.models.settings import DEFAULT_OPENAI_BASE_URL
from app.settings_runtime import EffectiveSettings, resolve_effective_settings

log = logging.getLogger("summaries.builder")

#: Spanish month names for the heuristic narrative.
MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

#: Top titles kept per source/keyword in the content JSON.
TOP_TITLES = 3

#: Keyword clauses (mentioned + silent) rendered inside the heuristic
#: narrative; the full lists always live in the content JSON.
MAX_KEYWORDS_NARRATIVE = 5

# Chat-completions transport constants, mirroring app.sentiment.api_analyzer.
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
TIMEOUT_S = 20.0
ATTEMPTS = 2
BACKOFF_S = 0.5

SYSTEM_PROMPT = (
    "Eres editor de monitoreo de medios. Redacta de 2 a 4 oraciones "
    "periodísticas en español sobre la jornada usando ÚNICAMENTE los datos "
    "del resumen. No inventes datos ni títulos que no estén en la lista."
)


def _zone(tz_name: str) -> ZoneInfo:
    """ZoneInfo for the settings tz; UTC fallback when invalid."""
    try:
        return ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 - a bad stored tz must not 500 the API
        log.warning("invalid timezone %r in settings; using UTC", tz_name)
        return ZoneInfo("UTC")


def today_in(tz_name: str) -> date:
    """Today's date as seen from the settings timezone."""
    return datetime.now(_zone(tz_name)).date()


def day_window(day: date, tz_name: str) -> tuple[datetime, datetime]:
    """``[start, next_start)`` bounds for the client-day.

    Computed in the settings timezone so "the day" means the client's day,
    not the server's or UTC's.
    """
    tz = _zone(tz_name)
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    return start, start + timedelta(days=1)


def _sort_stamp(mention) -> tuple:
    """Newest-first sort key; naive stamps are treated as UTC."""
    ts = mention.published_at
    if ts is None:
        return (0, datetime.min.replace(tzinfo=timezone.utc), mention.id)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (1, ts, mention.id)


def _source_tag(mention) -> str:
    value = mention.source
    return str(value.value) if hasattr(value, "value") else str(value)


def _human_day(day: date) -> str:
    return f"{day.day} de {MONTHS_ES[day.month - 1]} de {day.year}"


def _openai_generator(effective: EffectiveSettings) -> Callable[[str], str]:
    """Callable prompt->narrative for the configured provider.

    Same request shape as the sentiment analyzer: POST {base}/chat/
    completions, Bearer key, model from settings, temperature 0. Raises on
    any failure; the caller owns the heuristic fallback.
    """
    base_url = (effective.ai_base_url or DEFAULT_OPENAI_BASE_URL).rstrip("/")
    model = effective.ai_model or DEFAULT_OPENAI_MODEL
    api_key = effective.ai_api_key or ""

    def generate(prompt: str) -> str:
        payload: str | None = None
        last_error: Exception | None = None
        for attempt in range(ATTEMPTS):
            if attempt:
                time.sleep(BACKOFF_S * attempt)
            try:
                resp = httpx.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0,
                    },
                    timeout=TIMEOUT_S,
                )
                resp.raise_for_status()
                payload = str(resp.json()["choices"][0]["message"]["content"]).strip()
                break
            except (
                httpx.HTTPError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
            ) as exc:
                last_error = exc
                log.debug("summary llm attempt %d/%d failed", attempt + 1, ATTEMPTS)
                log.debug("error: %s", exc)
        if payload is None:
            raise RuntimeError(f"summary ll failed after {ATTEMPTS} attempts: {last_error}")
        return payload

    return generate


def summary_generator(effective: EffectiveSettings) -> Callable[[str], str] | None:
    """LLM narrative callable for the effective settings, else None.

    None is the documented 'no provider' state (local sentiment models
    cannot generate text), not an error.
    """
    provider = (effective.ai_provider or "").strip().lower()
    if provider != "openai" or not (effective.ai_api_key or "").strip():
        return None
    return _openai_generator(effective)


def _stats_prompt(day: date, stats: dict) -> str:
    return (
        f"Resumen del {day.isoformat()} (todas las cifras son datos "
        f"verificados):\n{json.dumps(stats, ensure_ascii=False)}"
    )


def _heuristic_narrative(
    day: date,
    total: int,
    per_source: dict,
    per_keyword: dict,
    silent: list[str],
) -> str:
    """Fixed-template Spanish narrative; deterministic for a given input."""
    human = _human_day(day)
    if total == 0:
        sentence = f"Hoy {human} no se registraron menciones."
        if silent:
            shown = ", ".join(silent[:MAX_KEYWORDS_NARRATIVE])
            sentence += f" Sin cobertura para: {shown}."
        return sentence

    parts = [f"Hoy {human} se registraron {total} menciones."]
    dominant, dominant_data = max(
        per_source.items(), key=lambda kv: (kv[1]["count"], kv[0])
    )
    parts.append(
        f"La fuente dominante fue {dominant}, "
        f"con {dominant_data['count']} de {total}."
    )
    for name, data in sorted(
        per_keyword.items(), key=lambda kv: (-kv[1]["count"], kv[0])
    ):
        count = data["count"]
        clause = f"Sobre {name} se registraron {count} {_noun(count)}."
        if data["top_titles"]:
            clause += f" Destacando «{data['top_titles'][0]}»."
        parts.append(clause)
    if silent:
        shown = ", ".join(silent[:MAX_KEYWORDS_NARRATIVE])
        parts.append(f"Sin menciones: {shown}.")
    return " ".join(parts)


def _noun(count: int) -> str:
    return "mención" if count == 1 else "menciones"


def _plain_text(
    narrative: str,
    total: int,
    per_source: dict,
    per_keyword: dict,
    silent: list[str],
) -> str:
    """Full plain-text render stored for the future RAG chat."""
    lines = [narrative, ""]
    if per_source:
        lines.append("Fuentes:")
        for name, data in sorted(per_source.items()):
            titles = "; ".join(f"«{t}»" for t in data["top_titles"])
            suffix = f" Titulares: {titles}." if titles else ""
            lines.append(f"- {name}: {data['count']} {_noun(data['count'])}.{suffix}")
        lines.append("")
    if per_keyword or silent:
        lines.append("Palabras clave:")
        for name, data in sorted(
            per_keyword.items(), key=lambda kv: (-kv[1]["count"], kv[0])
        ):
            titles = "; ".join(f"«{t}»" for t in data["top_titles"])
            suffix = f" Titulares: {titles}." if titles else ""
            lines.append(f"- {name}: {data['count']} {_noun(data['count'])}.{suffix}")
        for name in silent:
            lines.append(f"- {name}: sin menciones.")
        lines.append("")
    lines.append(f"Total: {total} {_noun(total)}.")
    return "\n".join(lines)


def build_daily_summary(
    session: Session,
    *,
    client_id: int,
    day: date,
    generate: Callable[[str], str] | None = None,
):
    """Aggregate the client-day and upsert the DailySummary row.

    ``generate`` overrides the settings-driven LLM callable (tests,
    tooling). Returns the stored row; ``mode`` is ``llm`` only when the
    LLM narrative was actually used.
    """
    effective = resolve_effective_settings(session, client_id)
    start, end = day_window(day, effective.timezone)
    # SQLite keeps datetimes as naive wall strings and compares them
    # lexically, so the bounds travel as UTC walls (the ingest pipeline
    # stores UTC); PostgreSQL compares true timestamps and reads the same
    # instants either way.
    utc_start = start.astimezone(timezone.utc)
    utc_end = end.astimezone(timezone.utc)
    mentions = list(
        session.scalars(
            select(Mention).where(
                Mention.client_id == client_id,
                Mention.published_at >= utc_start,
                Mention.published_at < utc_end,
            )
        )
    )

    total = len(mentions)
    by_source: dict[str, list] = {}
    for mention in mentions:
        by_source.setdefault(_source_tag(mention), []).append(mention)
    per_source: dict[str, dict] = {}
    for source, items in by_source.items():
        items.sort(key=_sort_stamp, reverse=True)
        per_source[source] = {
            "count": len(items),
            "top_titles": [m.title for m in items[:TOP_TITLES] if m.title],
        }

    all_keywords = list(queries.list_keywords(session, client_id, active_only=False))
    keyword_text_by_id = {k.id: k.text for k in all_keywords}
    by_keyword: dict[str, list] = {}
    for mention in mentions:
        text = keyword_text_by_id.get(mention.keyword_id) if mention.keyword_id else None
        if text:
            by_keyword.setdefault(text, []).append(mention)
    per_keyword: dict[str, dict] = {}
    for name, items in by_keyword.items():
        items.sort(key=_sort_stamp, reverse=True)
        per_keyword[name] = {
            "count": len(items),
            "top_titles": [m.title for m in items[:TOP_TITLES] if m.title],
        }
    # A mention whose keyword row was renamed still counts toward that
    # keyword's presence for the silent check.
    mentioned = set(per_keyword)
    for mention in mentions:
        if mention.keyword_id in keyword_text_by_id:
            mentioned.add(keyword_text_by_id[mention.keyword_id])
    silent = sorted({k.text for k in all_keywords if k.is_active} - mentioned)

    totals = {
        "mentions": total,
        "sources": len(per_source),
        "keywords_with_mentions": len(per_keyword),
        "silent_keywords": len(silent),
    }
    stats = {
        "per_source": per_source,
        "per_keyword": per_keyword,
        "silent_keywords": silent,
        "totals": totals,
    }

    narrative = _heuristic_narrative(day, total, per_source, per_keyword, silent)
    mode = "heuristic"
    if generate is None:
        generate = summary_generator(effective)
    if generate is not None and total > 0:
        try:
            text = str(generate(_stats_prompt(day, stats))).strip()
        except Exception as exc:  # noqa: BLE001 - heuristic is the contract
            log.warning(
                "daily summary llm failed for %s (%s); heuristic fallback", day, exc
            )
        else:
            if text:
                narrative, mode = text, "llm"

    content = {
        "date": day.isoformat(),
        "timezone": effective.timezone,
        "per_source": per_source,
        "per_keyword": per_keyword,
        "silent_keywords": silent,
        "totals": totals,
        "plain_text": _plain_text(narrative, total, per_source, per_keyword, silent),
    }
    return queries.upsert_daily_summary(
        session,
        client_id=client_id,
        day=day,
        content=content,
        narrative=narrative,
        mode=mode,
    )
