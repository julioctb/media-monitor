"""Digest v2: the editorial daily digest contract.

``content`` schema 2 stored on ``daily_summaries`` (one row per client/day):

    schema      int, always DIGEST_SCHEMA_VERSION
    window      {"from", "to"} ISO datetimes in the settings timezone
    coverage    {"total", "by_source", "by_topic", "gaps"} - deterministic
    noticias    [{topic, event_id, title, sources[{source,url,title}],
                  summary, why_it_matters, confidence, person_ids}]
    agenda      [{when, status?, title, source?}] - LLM narrative
    rectora     {actions[], activity[], tone, watch, gaps} - focus person;
                activity [{when?, status?, text, channel?}] is LLM narrative
    redes       {<source>: {count, note}} - social sources; note carries the
                LLM narrative when the day has data
    personas    [{person_id, name, role, fact}]
    pendientes  [str] - silent keywords / uncovered events

Only the narrative fields (summary, why_it_matters, tone, watch, activity,
agenda, redes note) are LLM-authored; everything else is deterministic (see
build_digest_facts and confidence_for). validate_digest gates the LLM output:
any error falls back to the heuristic render, mirroring builder.py's mode
contract. Every v2 key is optional: rows authored before home-digest-v2 lack
them and must read back unchanged.
"""

from datetime import datetime, timezone

import logging

from pydantic import ValidationError

from app.summaries.digest_schema import (
    ActivityEntry,
    AgendaEntry,
    CuentaEntry,
    NarrativeItem,
)

LOGGER = logging.getLogger(__name__)

DIGEST_SCHEMA_VERSION = 2

#: Fixed confidence scale; never free-form (auditability over prose).
CONFIDENCE_SCALE = ("alta", "media", "baja")

REQUIRED_SECTIONS = ("coverage", "noticias", "rectora", "redes", "personas", "pendientes")

#: Spanish short months for the per-news date label («17 oct.»).
ES_SHORT_MONTHS = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)


def es_short_label(dt: datetime, tz_name: str) -> str:
    """«17 oct.» — local-day label for a mention timestamp.

    The digest window spans one client-day, but the rescued evening tail
    (morning-cutover) belongs to the previous label, so the stamp comes from
    the timestamp itself, never from the digest day.
    """
    from zoneinfo import ZoneInfo

    try:
        local = dt.astimezone(ZoneInfo(tz_name))
    except Exception:  # noqa: BLE001 - a bad stored tz falls back to UTC
        local = dt.astimezone(timezone.utc)
    return f"{local.day} {ES_SHORT_MONTHS[local.month - 1]}."


def confidence_for(source_count: int) -> str:
    """Auditability rule: independent outlets decide, never the LLM."""
    if source_count >= 3:
        return "alta"
    if source_count == 2:
        return "media"
    return "baja"


def gaps_for(
    *, counts: dict[str, int], social: set[str], labels: dict[str, str]
) -> list[str]:
    """Human-readable gap lines for tracked social sources with zero mentions.

    Sorted by label so the section is stable across runs; sources missing
    from ``counts`` count as zero (no data ≠ covered).
    """
    return sorted(
        f"{labels.get(source, source)} sin cobertura en la ventana"
        for source in social
        if counts.get(source, 0) == 0
    )


def _single_topic(mention) -> str | None:
    """The mention's canonical topic label, else None."""
    for c in mention.classifications:
        if c.classifier == "topic":
            return c.label
    return None


def build_digest_facts(
    session,
    *,
    client_id: int,
    day,
    tz: str,
    focus_person_id: int | None = None,
    mentions: list | None = None,
    window_start: datetime | None = None,
) -> dict:
    """Deterministic facts for one client-day. No LLM, no prose.

    Window, source counts and the SQLite/PostgreSQL tz dance mirror
    builder.build_daily_summary (UTC walls over mentions.published_at).
    ``mentions`` optionally injects the day's rows (the composer already
    queried them); otherwise they are loaded here. Ordered by id so the
    section layout is stable across engines.
    """
    from collections import Counter
    from datetime import datetime

    from sqlalchemy import select

    from app.models import Event, Mention, Person
    from app.summaries.builder import day_window

    if window_start is not None:
        start = window_start
        _, end = day_window(day, tz)
    else:
        start, end = day_window(day, tz)
    utc_start = start.astimezone(timezone.utc)
    utc_end = end.astimezone(timezone.utc)
    if mentions is None:
        mentions = list(
            session.scalars(
                select(Mention)
                .where(
                    Mention.client_id == client_id,
                    Mention.published_at >= utc_start,
                    Mention.published_at < utc_end,
                )
                .order_by(Mention.id)
            )
        )
    else:
        mentions = sorted(mentions, key=lambda m: m.id)

    by_source: Counter[str] = Counter(m.source.value for m in mentions)
    by_topic: Counter[str] = Counter(
        c.label
        for m in mentions
        for c in m.classifications
        if c.classifier == "topic"
    )

    # --- noticias: event rows first, loose mentions as single items.
    event_ids = {m.event_id for m in mentions if m.event_id is not None}
    events_by_id = {
        e.id: e
        for e in session.scalars(
            select(Event).where(Event.id.in_(event_ids))
        ).all()
    } if event_ids else {}

    def _mention_person_ids(mention) -> list[int]:
        # person_links are MentionPerson rows; the person id lives on the link.
        return sorted({link.person_id for link in mention.person_links})

    grouped: dict[int | None, list] = {}
    for mention in mentions:
        grouped.setdefault(mention.event_id, []).append(mention)
    noticias: list[dict] = []
    for event_id, items in grouped.items():
        event = events_by_id.get(event_id) if event_id is not None else None
        if event is None:
            # Loose mentions: each its own baja item (grouping unrelated
            # rows would fabricate a story).
            for mention in items:
                noticias.append(
                    {
                        "event_id": None,
                        "title": mention.title,
                        "summary": None,
                        "topic": _single_topic(mention),
                        "sources": [
                            {
                                "source": mention.source.value,
                                "url": mention.url,
                                "title": mention.title,
                            }
                        ],
                        "confidence": "baja",
                        "person_ids": _mention_person_ids(mention),
                        "when_label": (
                            es_short_label(mention.published_at, tz)
                            if mention.published_at
                            else None
                        ),
                        "tone": (
                            {mention.sentiment.value: 1} if mention.sentiment else {}
                        ),
                        "why_it_matters": None,
                    }
                )
            continue
        topic_counts = Counter(
            c.label for m in items for c in m.classifications if c.classifier == "topic"
        )
        topic = topic_counts.most_common(1)[0][0] if topic_counts else None
        # Sentiment mix of the event's mentions: the narrative must know WHICH
        # events read negative (and how loudly) to weigh them in the headline.
        tone_counts = Counter(m.sentiment.value for m in items if m.sentiment is not None)
        person_ids = sorted({pid for m in items for pid in _mention_person_ids(m)})
        noticias.append(
            {
                "event_id": event_id,
                "title": event.title,
                "summary": event.summary,
                "topic": topic,
                "sources": [
                    {"source": m.source.value, "url": m.url, "title": m.title}
                    for m in items
                ],
                "confidence": confidence_for(len({m.source for m in items})),
                "tone": dict(tone_counts),
                "person_ids": person_ids,
                "when_label": max(
                    (
                        es_short_label(m.published_at, tz)
                        for m in items
                        if m.published_at is not None
                    ),
                    default=None,
                ),
                # narrative fields, filled by the composer (LLM or heuristic)
                "why_it_matters": None,
            }
        )
    noticias.sort(
        key=lambda n: (
            -len(n["sources"]),
            CONFIDENCE_SCALE.index(n["confidence"]),
        )
    )

    # --- rectora: focus person slice.
    rectora: dict = {
        "person_id": focus_person_id,
        "actions": [],
        "activity": [],  # narrative follow-up, LLM-authored (home-digest-v2)
        "mention_count": 0,
    }
    if focus_person_id is not None:
        focus_links = [
            (m, link)
            for m in mentions
            for link in m.person_links
            if link.person_id == focus_person_id
        ]
        rectora["mention_count"] = len(focus_links)
        rectora["actions"] = [
            {
                "title": m.title,
                "event_id": m.event_id,
                "sentiment": m.sentiment.value if m.sentiment else None,
                # As extracted on THIS mention (the aggregated view lives on
                # the person row); the digest shows the mention-level stance.
                "role": link.role,
                "org": link.org,
            }
            for m, link in focus_links
        ]
        tones = Counter(
            m.sentiment.value for m, _link in focus_links if m.sentiment is not None
        )
        rectora["tone"] = tones.most_common(1)[0][0] if tones else None
        if not focus_links:
            rectora["gaps"] = "sin menciones de la persona focal en la ventana"
        # Identity stamp (rectora-identity-stamp T1): same source the
        # personas entries use — link role/org as extracted on the mention,
        # falling back to the aggregated Person row. Absent when the focus
        # id has no person row (never invented).
        focus_person = session.get(Person, focus_person_id)
        if focus_person is not None:
            link = next((link for _m, link in focus_links), None)
            rectora["name"] = focus_person.name
            rectora["role"] = (link.role if link and link.role else None) or focus_person.role
            rectora["org"] = (link.org if link and link.org else None) or focus_person.org

    # --- personas: everyone linked to the day's mentions, by volume.
    person_counts: Counter[int] = Counter(
        link.person_id for m in mentions for link in m.person_links
    )
    persons_by_id = {
        p.id: p
        for p in session.scalars(
            select(Person).where(Person.id.in_(set(person_counts)))
        ).all()
    } if person_counts else {}
    personas = []
    for person_id, count in person_counts.most_common():
        person = persons_by_id[person_id]
        link = next(
            (
                link
                for m in mentions
                for link in m.person_links
                if link.person_id == person_id
            ),
            None,
        )
        fact = next(
            (
                m.title
                for m in mentions
                if any(link.person_id == person_id for link in m.person_links)
                and m.title
            ),
            None,
        )
        personas.append(
            {
                "person_id": person_id,
                "name": person.name,
                "role": (link.role if link and link.role else None) or person.role,
                "org": (link.org if link and link.org else None) or person.org,
                "mention_count": count,
                "fact": fact,
            }
        )

    # --- redes: tracked social sources, count + gaps when silent.
    social_labels = {"x": "X (Twitter)", "facebook_page": "Facebook", "instagram": "Instagram"}
    redes = {
        source: {"count": by_source.get(source, 0), "note": ""}
        for source in ("x", "facebook_page", "instagram")
    }

    coverage = {
        "total": len(mentions),
        "by_source": dict(by_source),
        "by_topic": dict(by_topic),
        "gaps": gaps_for(counts=dict(by_source), social=set(social_labels), labels=social_labels),
    }

    return {
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "coverage": coverage,
        "noticias": noticias,
        "agenda": [],  # narrative, LLM-authored (home-digest-v2)
        "rectora": rectora,
        "redes": redes,
        "personas": personas,
        "pendientes": [],  # composed at T5: silent keywords + coverage gaps
    }


def _clean_str(value: object) -> str | None:
    """Stripped non-empty string, else None (the tolerant-entry filter)."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _warn_skip(where: str, exc: Exception) -> None:
    """Skipped narrative entries are logged, never silent."""
    LOGGER.warning("digest narrative %s skipped: %s", where, exc)


def apply_narrative(content: dict, payload: object) -> list[str]:
    """Merge LLM narrative fields into ``content``; return digest errors.

    The payload shape is declared in ``app/summaries/digest_schema.py``
    (see docs/contrato-narrativa-del-digest.md): entries are validated with
    those models, and a malformed entry is logged and skipped — the merge
    stays tolerant, the deterministic sections are never rewritten. Only
    section-level shape errors are fatal (the return value).
    """
    if not isinstance(content, dict) or not isinstance(payload, dict):
        return ["payload must be an object"]
    items = payload.get("items")
    noticias = content.get("noticias")
    if items is not None:
        if not isinstance(items, list):
            return ["items must be a list"]
        for pos, entry in enumerate(items):
            try:
                narrative_item = NarrativeItem.model_validate(entry)
            except ValidationError as exc:
                _warn_skip(f"items[{pos}]", exc)
                continue
            if not isinstance(noticias, list):
                continue
            if not 0 <= narrative_item.index < len(noticias):
                _warn_skip(
                    "items[%d]" % pos, IndexError(f"index {narrative_item.index} out of range")
                )
                continue
            target = noticias[narrative_item.index]
            if not isinstance(target, dict):
                continue
            for key in ("summary", "why_it_matters", "confidence_note"):
                value = getattr(narrative_item, key)
                if isinstance(value, str) and value.strip():
                    target[key] = value.strip()
    rectora = payload.get("rectora")
    if isinstance(rectora, dict) and isinstance(content.get("rectora"), dict):
        for key in ("tone", "watch"):
            value = _clean_str(rectora.get(key))
            if value:
                content["rectora"][key] = value
        # home-digest-v2 follow-up entries; only into a seeded container so
        # pre-v2 rows keep their shape.
        activity = rectora.get("activity")
        if isinstance(activity, list) and isinstance(
            content["rectora"].get("activity"), list
        ):
            entries = []
            for pos, entry in enumerate(activity):
                try:
                    validated = ActivityEntry.model_validate(entry)
                except ValidationError as exc:
                    _warn_skip(f"rectora.activity[{pos}]", exc)
                    continue
                text = _clean_str(validated.text)
                if not text:
                    continue
                item: dict[str, str] = {"text": text}
                for optional in ("when", "status", "channel"):
                    value = _clean_str(getattr(validated, optional))
                    if value:
                        item[optional] = value
                entries.append(item)
            if entries:
                content["rectora"]["activity"] = entries
    # agenda: upcoming items gleaned from the day's facts; when+title
    # required (the mockup's strong-led fields), status/source optional.
    agenda = payload.get("agenda")
    if isinstance(agenda, list) and isinstance(content.get("agenda"), list):
        entries = []
        for pos, entry in enumerate(agenda):
            try:
                validated = AgendaEntry.model_validate(entry)
            except ValidationError as exc:
                _warn_skip(f"agenda[{pos}]", exc)
                continue
            when = _clean_str(validated.when)
            title = _clean_str(validated.title)
            if not when or not title:
                continue
            item = {"when": when, "title": title}
            for optional in ("status", "source"):
                value = _clean_str(getattr(validated, optional))
                if value:
                    item[optional] = value
            entries.append(item)
        if entries:
            content["agenda"] = entries
    # redes narrative note; only for sources the digest tracks, bare
    # strings tolerated. cuentas: optional per-account follow-ups
    # ({cuenta, nota}); merged only into seeded dict targets so pre-v2
    # rows keep their shape.
    redes_payload = payload.get("redes")
    if isinstance(redes_payload, dict) and isinstance(content.get("redes"), dict):
        for source, note_payload in redes_payload.items():
            target = content["redes"].get(source)
            if not isinstance(target, dict):
                continue
            note = note_payload
            cuentas = None
            if isinstance(note_payload, dict):
                note = note_payload.get("note")
                cuentas = note_payload.get("cuentas")
            note = _clean_str(note)
            if note:
                target["note"] = note
            if isinstance(cuentas, list):
                entries = []
                for pos, entry in enumerate(cuentas):
                    try:
                        validated = CuentaEntry.model_validate(entry)
                    except ValidationError as exc:
                        _warn_skip(f"redes[{source!r}].cuentas[{pos}]", exc)
                        continue
                    cuenta = _clean_str(validated.cuenta)
                    if not cuenta:
                        continue
                    item: dict[str, str] = {"cuenta": cuenta}
                    if validated.nota and validated.nota.strip():
                        item["nota"] = validated.nota.strip()
                    entries.append(item)
                if entries:
                    target["cuentas"] = entries
    return validate_digest(content)


def render_plain_text(content: dict, narrative: str) -> str:
    """Sectioned plain text (RAG chunk + readable fallback), es mirrors UI."""
    lines = [narrative, ""]
    lines.append("NOTICIAS")
    for item in content.get("noticias") or []:
        confidence = item.get("confidence") or "?"
        repeat_tag = " (se repite nuevamente)" if item.get("repeat") else ""
        when = item.get("when_label")
        when_tag = f" ({when})" if when else ""
        lines.append(f"- [{confidence}]{when_tag}{repeat_tag} {item.get('title') or '(sin título)'}")
        if item.get("summary"):
            note = f" ({item['confidence_note']})" if item.get("confidence_note") else ""
            lines.append(f"  {item['summary']}{note}")
        if item.get("why_it_matters"):
            lines.append(f"  Por qué importa: {item['why_it_matters']}")
        sources = ", ".join(
            f"{s.get('source')}" for s in item.get("sources") or []
        )
        if sources:
            lines.append(f"  Fuentes: {sources}")
    temas = content.get("temas_sin_nota") or []
    if temas:
        lines.append("")
        lines.append("TEMAS SIN NOTA")
        for name in temas:
            lines.append(f"- {name}: sin novedades identificadas en la ventana.")
    agenda = content.get("agenda") or []
    if agenda:
        lines.append("")
        lines.append("AGENDA")
        for item in agenda:
            if not isinstance(item, dict):
                continue
            head = " · ".join(p for p in (item.get("when"), item.get("status")) if p)
            line = f"- {head}: {item.get('title')}" if head else f"- {item.get('title')}"
            if item.get("source"):
                line += f" Fuente: {item['source']}"
            lines.append(line)
    lines.append("")
    lines.append("RECTORA")
    rectora = content.get("rectora") or {}
    if rectora.get("mention_count"):
        for action in rectora.get("actions") or []:
            lines.append(f"- {action.get('title')}")
        if rectora.get("tone"):
            lines.append(f"  Tono: {rectora['tone']}")
        if rectora.get("watch"):
            lines.append(f"  Vigilar: {rectora['watch']}")
    else:
        lines.append("- Sin menciones de la persona focal en la ventana.")
    for source, info in (content.get("redes") or {}).items():
        if isinstance(info, dict) and info.get("note"):
            lines.append(f"  {source}: {info['note']}")
        cuentas = info.get("cuentas") if isinstance(info, dict) else None
        for entry in cuentas or []:
            cuenta = entry.get("cuenta")
            nota = entry.get("nota")
            line = f"    - {cuenta}" if cuenta else None
            if line and nota:
                line += f": {nota}"
            if line:
                lines.append(line)
    for entry in rectora.get("activity") or []:
        if not isinstance(entry, dict) or not entry.get("text"):
            continue
        head = " · ".join(p for p in (entry.get("when"), entry.get("status")) if p)
        line = f"- {head}: {entry['text']}" if head else f"- {entry['text']}"
        if entry.get("channel"):
            line += f" ({entry['channel']})"
        lines.append(line)
    if rectora.get("gaps"):
        lines.append(f"  Gap: {rectora['gaps']}")
    lines.append("")
    lines.append("REDES")
    for source, data in (content.get("redes") or {}).items():
        note = f" — {data['note']}" if isinstance(data, dict) and data.get("note") else ""
        count = data.get("count") if isinstance(data, dict) else data
        lines.append(f"- {source}: {count}{note}")
    lines.append("")
    lines.append("PERSONAS")
    for person in content.get("personas") or []:
        role = " · ".join(p for p in (person.get("role"), person.get("org")) if p)
        suffix = f" ({role})" if role else ""
        fact = f": {person['fact']}" if person.get("fact") else ""
        lines.append(
            f"- {person.get('name')}{suffix} — {person.get('mention_count', 0)} menciones{fact}"
        )
    lines.append("")
    lines.append("PENDIENTES")
    for pending in content.get("pendientes") or []:
        lines.append(f"- {pending}")
    if not content.get("pendientes"):
        lines.append("- ninguno")
    return "\n".join(lines)


def validate_digest(content: object) -> list[str]:
    """Return human-readable errors; empty list means well-formed v2."""
    if not isinstance(content, dict):
        return ["digest must be a JSON object"]
    errors: list[str] = []
    if content.get("schema") != DIGEST_SCHEMA_VERSION:
        errors.append(f"schema must be {DIGEST_SCHEMA_VERSION}")
    for section in REQUIRED_SECTIONS:
        if section not in content:
            errors.append(f"missing section {section}")
    noticias = content.get("noticias")
    if isinstance(noticias, list):
        for index, item in enumerate(noticias):
            if not isinstance(item, dict):
                errors.append(f"noticias[{index}] must be an object")
                continue
            confidence = item.get("confidence")
            if confidence is not None and confidence not in CONFIDENCE_SCALE:
                errors.append(f"noticias[{index}].confidence must be one of {CONFIDENCE_SCALE}")
            sources = item.get("sources")
            if sources is not None and not (
                isinstance(sources, list) and all(isinstance(s, dict) for s in sources)
            ):
                errors.append(f"noticias[{index}].sources must be a list of objects")
    elif "noticias" in content:
        errors.append("noticias must be a list")
    return errors
