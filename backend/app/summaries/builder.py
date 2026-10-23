"""Daily digest builder (T11 -> digest v2).

Pipeline, always run:

  1. day window in the settings timezone (zoneinfo) over mentions.published_at,
  2. deterministic facts via summaries.digest.build_digest_facts (events,
     personas, topics, rectora slice, redes counts, gaps),
  3. silent keywords become the PENDIENTES section,
  4. LLM narrative pass: the model ONLY fills headline / per-item
     summary+why_it_matters / rectora tone+watch, merged by
     digest.apply_narrative; any failure keeps the heuristic mode,
  5. digest.render_plain_text stores the sectioned plain text as
     content["plain_text"] for RAG and quick reading.

The structured content never depends on the LLM, which is also skipped for
empty days (nothing to summarize); mode stays ``heuristic`` then.
"""

import json
import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select

from app.enrich.llm import strip_code_fence

from app.models import Mention, queries
from app.models.settings import DEFAULT_OPENAI_BASE_URL
from app.settings_runtime import EffectiveSettings, resolve_effective_settings
from app.summaries.digest import (
    DIGEST_SCHEMA_VERSION,
    apply_narrative,
    build_digest_facts,
    render_plain_text,
)

log = logging.getLogger("summaries.builder")

#: Spanish month names for the heuristic headline.
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

#: Silent keywords shown inside the heuristic headline.
MAX_KEYWORDS_NARRATIVE = 5

# Chat-completions transport constants, mirroring app.sentiment.api_analyzer.
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
TIMEOUT_S = 60.0  # digest narrative is a long prompt+completion; 20s timed out under load
ATTEMPTS = 2
BACKOFF_S = 0.5

SYSTEM_PROMPT = (
    "Eres editor de monitoreo de medios. Recibes los HECHOS verificados del "
    "día en JSON (noticias, rectora, redes, personas). Devuelve EXCLUSIVAMENTE "
    "un objeto JSON con: headline (1-3 oraciones que tejen el día; el tono "
    "de cada noticia via facts.noticias[i].tone — dedica énfasis explícito "
    "a las de tono negativo dominante: nómbralas y explica la razón de su "
    "tono según sus hechos; las positivas y neutras se subordinan), items "
    "[{index, summary, why_it_matters, confidence_note}] para las noticias "
    "que lo requieran; confidence_note justifica la confianza en<=6 palabras "
    "(ej. «fuente oficial directa») y es opcional; y rectora {tone, watch, "
    "activity}: activity es el seguimiento narrativo de la persona focal, "
    "lista [{when, status, text, channel}] con cuándo/qué, estado y canal "
    "cuando aplique (omítela si no hay nada que vigilar). Incluye además "
    "agenda: lista [{when, status, title, source}] de eventos o citas futuras "
    "visibles en los datos (when y title literales, sin inventar fechas), y "
    "redes: {<fuente>: {note, cuentas}} donde note es la nota narrativa de la "
    "red y cuentas es la lista [{cuenta, nota}] con una entrada POR CUENTA "
    "rastreada con datos o hallazgos (estado, pendientes de verificación). "
    "En facebook la nota describe los hallazgos SIN nombrar páginas, grupos "
    "ni fuentes (el lector ya sabe cuáles se siguen) y sin bloque de "
    "cuentas. En TODAS las redes la nota es paráfrasis editorial: NUNCA "
    "citas textuales, sin emojis, sin URLs ni acortadores, sin menciones @; "
    "redacta el hecho con palabras propias. "
    "Nota vacía o ausente cuando nada sea fechable, y omite cuentas "
    "sin nada que decir. Prohibido inventar datos, fuentes o títulos: usa "
    "únicamente los hechos. Español periodístico, máximo 2 oraciones por "
    "campo."
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


#: Hours after midnight whose first cut reaches back into the previous
#: evening, rescuing notes published after that day's last digest cut.
MORNING_CUTOVER_HOUR = 12
PREVIOUS_EVENING_HOURS = 3  # 21:00 the day before


def resolve_digest_window(
    session,
    *,
    client_id: int,
    day: date,
    tz_name: str,
) -> tuple[datetime, datetime, bool]:
    """Window for the day's digest, stable across the day's cuts.

    First generation during the morning (before ``MORNING_CUTOVER_HOUR``)
    extends three hours into the previous evening so notes published after
    that day's last cut are not orphaned between digests. The choice is
    persisted on the stored row (``content.window_start``) so later cuts
    rebuild with the same bounds instead of dropping the tail.
    """
    start, end = day_window(day, tz_name)
    existing = queries.get_daily_summary(session, client_id, day)
    if existing is not None:
        stored = (existing.content or {}).get("window_start")
        if stored:
            try:
                return datetime.fromisoformat(stored), end, True
            except ValueError:
                pass
        return start, end, False
    now_hour = datetime.now(_zone(tz_name)).hour
    if now_hour < MORNING_CUTOVER_HOUR:
        return start - timedelta(hours=PREVIOUS_EVENING_HOURS), end, True
    return start, end, False


def _noun(count: int) -> str:
    return "mención" if count == 1 else "menciones"


def _human_day(day: date) -> str:
    return f"{day.day} de {MONTHS_ES[day.month - 1]} de {day.year}"


def _heuristic_headline(
    day: date, total: int, silent: list[str], by_source: dict, negative_events: int = 0
) -> str:
    """Fixed-template Spanish headline; deterministic for a given input."""
    human = _human_day(day)
    if total == 0:
        sentence = f"Hoy {human} no se registraron menciones."
        if silent:
            shown = ", ".join(silent[:MAX_KEYWORDS_NARRATIVE])
            sentence += f" Sin cobertura para: {shown}."
        return sentence

    parts = [f"Hoy {human} se registraron {total} {_noun(total)}."]
    if by_source:
        dominant = max(by_source.items(), key=lambda kv: (kv[1], kv[0]))[0]
        parts.append(f"La fuente con más notas fue {dominant}.")
    if negative_events:
        parts.append(
            f"{negative_events} {'nota' if negative_events == 1 else 'notas'} con tono "
            "negativo dominante."
        )
    if silent:
        shown = ", ".join(silent[:MAX_KEYWORDS_NARRATIVE])
        parts.append(f"Sin menciones: {shown}.")
    return " ".join(parts)


def _digest_prompt(day: date, facts: dict) -> str:
    repeats = any(n.get("repeat") for n in facts.get("noticias", []))
    extra = (
        "\nLas notas con repeat=true ya fueron cubiertas en ediciones "
        "anteriores: trátalas como reiteración breve, destacando solo el "
        "ángulo nuevo. En el summary de esas notas indica explícitamente que "
        "la historia se repite nuevamente respecto a ediciones previas. "
        "Destaca explícitamente los cambios de tono negativos del día."
        if repeats
        else ""
    )
    return (
        f"Digest del {day.isoformat()} (todas las cifras y títulos son datos "
        f"verificados; el items[i].index corres a noticias[i]):\n"
        f"{json.dumps(facts, ensure_ascii=False, default=str)}"
        f"{extra}"
    )


def _openai_generator(effective: EffectiveSettings) -> Callable[[str], str]:
    """Callable prompt->payload for the configured provider.

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
                raw_content = resp.json()["choices"][0]["message"]["content"]
                if not isinstance(raw_content, str) or not raw_content.strip():
                    # content:null becomes str "None" and breaks json.loads
                    # upstream; treat it as a failed attempt instead.
                    raise ValueError("empty summary content")
                # Models wrap the JSON in ``` fences; the digest json.loads
                # chokes on the leading backtick otherwise.
                payload = strip_code_fence(raw_content)
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


def build_daily_summary(
    session,
    *,
    client_id: int,
    day: date,
    generate: Callable[[str], str] | None = None,
):
    """Assemble digest v2 and upsert the DailySummary row.

    ``generate`` overrides the settings-driven LLM callable (tests,
    tooling). Returns the stored row; ``mode`` is ``llm`` only when the
    narrative pass applied cleanly.
    """
    effective = resolve_effective_settings(session, client_id)
    start, end, window_extended = resolve_digest_window(
        session, client_id=client_id, day=day, tz_name=effective.timezone
    )
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

    # Silent keywords -> PENDIENTES (v1 semantics: an active keyword whose
    # row never appears in the day's mentions; renamed rows still count).
    all_keywords = list(queries.list_keywords(session, client_id, active_only=False))
    keyword_text_by_id = {k.id: k.text for k in all_keywords}
    mentioned = {
        keyword_text_by_id[m.keyword_id]
        for m in mentions
        if m.keyword_id and m.keyword_id in keyword_text_by_id
    }
    silent = sorted({k.text for k in all_keywords if k.is_active} - mentioned)

    facts = build_digest_facts(
        session,
        client_id=client_id,
        day=day,
        tz=effective.timezone,
        focus_person_id=effective.digest_focus_person_id,
        mentions=mentions,
        window_start=start if window_extended else None,
    )
    content = {
        **facts,
        "schema": DIGEST_SCHEMA_VERSION,
        "date": day.isoformat(),
        "timezone": effective.timezone,
    }
    content["temas_sin_nota"] = silent
    # Limitaciones: the coverage gaps (tracked sources silent in the window).
    # Silent keywords moved to temas_sin_nota (Noticias block); legacy rows
    # keep keywords here and render unchanged.
    content["pendientes"] = list(content["coverage"]["gaps"])
    if window_extended:
        # Persist the extended bounds: later cuts rebuild with the same
        # window instead of dropping the rescued late-evening tail.
        content["window_start"] = start.isoformat()

    # Repeat detection: events whose earliest mention predates this
    # window were already circulating in previous editions; the narrative
    # must treat them as reiterations, not new stories.
    window_start_utc = start.astimezone(timezone.utc)
    for noticia in content["noticias"]:
        eid = noticia.get("event_id")
        if not eid:
            continue
        earliest = session.scalar(
            select(func.min(Mention.published_at)).where(
                Mention.client_id == client_id, Mention.event_id == eid
            )
        )
        if earliest is not None:
            # SQLite returns naive walls; normalize for the comparison.
            if earliest.tzinfo is None:
                earliest = earliest.replace(tzinfo=timezone.utc)
            if earliest < window_start_utc:
                noticia["repeat"] = True

    # Events whose mentions read negative-dominant, for the narrative emphasis
    # (the LLM gets tone per noticia; the heuristic names the count).
    negative_events = 0
    for noticia in content["noticias"]:
        tone = noticia.get("tone") or {}
        neg = tone.get("negative", 0)
        if neg > max(tone.get("positive", 0), tone.get("neutral", 0), 0):
            negative_events += 1

    narrative = _heuristic_headline(
        day, total, silent, content["coverage"]["by_source"], negative_events
    )
    mode = "heuristic"
    llm_ok = False
    if generate is None:
        generate = summary_generator(effective)
    if generate is not None and total > 0:
        try:
            payload = json.loads(generate(_digest_prompt(day, content)))
        except Exception as exc:  # noqa: BLE001 - heuristic is the contract
            log.warning("digest llm failed for %s (%s); heuristic fallback", day, exc)
        else:
            errors = apply_narrative(content, payload)
            headline = payload.get("headline") if isinstance(payload, dict) else None
            if not errors and isinstance(headline, str) and headline.strip():
                narrative, mode, llm_ok = headline.strip(), "llm", True
            else:
                log.warning("digest llm payload rejected for %s: %s", day, errors)

    if not llm_ok:
        # Failed (or skipped) regen of a digest that was llm-authored: keep
        # the previous narrative instead of downgrading a good digest to
        # template prose. Facts stay fresh; only the prose is inherited.
        previous = queries.get_daily_summary(session, client_id, day)
        if previous is not None and previous.mode == "llm":
            prev_content = previous.content or {}
            prev_by_event = {
                n.get("event_id"): n
                for n in prev_content.get("noticias") or []
                if n.get("event_id") is not None
            }
            for nota in content["noticias"]:
                old = prev_by_event.get(nota.get("event_id"))
                if old is None:
                    continue
                if not nota.get("summary") and old.get("summary"):
                    nota["summary"] = old["summary"]
                if not nota.get("why_it_matters") and old.get("why_it_matters"):
                    nota["why_it_matters"] = old["why_it_matters"]
            prev_rectora = prev_content.get("rectora") or {}
            rectora = content.get("rectora") or {}
            for key in ("tone", "watch"):
                if not rectora.get(key) and prev_rectora.get(key):
                    rectora[key] = prev_rectora[key]
            # home-digest-v2: the narrative blocks travel with the prose.
            prev_agenda = prev_content.get("agenda")
            if not content.get("agenda") and prev_agenda:
                content["agenda"] = prev_agenda
            prev_activity = prev_rectora.get("activity")
            if not rectora.get("activity") and prev_activity:
                rectora["activity"] = prev_activity
            for source, prev_data in (prev_content.get("redes") or {}).items():
                prev_note = prev_data.get("note") if isinstance(prev_data, dict) else None
                target = (content.get("redes") or {}).get(source)
                if prev_note and isinstance(target, dict) and not target.get("note"):
                    target["note"] = prev_note
            prev_plain = (prev_content.get("plain_text") or "").split("\n", 1)[0]
            if prev_plain:
                narrative = prev_plain
            mode = "llm"

    content["plain_text"] = render_plain_text(content, narrative)
    row = queries.upsert_daily_summary(
        session,
        client_id=client_id,
        day=day,
        content=content,
        narrative=narrative,
        mode=mode,
    )
    # Narrative revisions (summary-revisions): EVERY build appends an
    # immutable copy, so no prose is ever lost to the next cut. Best-effort:
    # a logging failure must not fail the digest (agenda-hook contract).
    try:
        from app.models import DailySummaryRevision

        last_seq = session.scalar(
            select(func.max(DailySummaryRevision.seq)).where(
                DailySummaryRevision.client_id == client_id,
                DailySummaryRevision.summary_date == day,
            )
        )
        session.add(
            DailySummaryRevision(
                client_id=client_id,
                summary_date=day,
                seq=(last_seq or 0) + 1,
                narrative=narrative,
                mode=mode,
            )
        )
        session.commit()
    except Exception as exc:  # noqa: BLE001 - history is best-effort
        log.warning("summary revision log failed for %s (%s)", day, exc)
    # Agenda auto-detect (agenda-detect): promote the digest's agenda
    # entries to real rows on EVERY build path (worker cut + API regen).
    # Idempotent by normalized title; failures never fail the digest.
    try:
        from app.summaries.agenda_detect import sync_agenda_from_digest

        sync_agenda_from_digest(session, client_id, content, reference=day)
    except Exception as exc:  # noqa: BLE001 - detection is best-effort
        log.warning("agenda detect failed for %s (%s)", day, exc)
    return row
