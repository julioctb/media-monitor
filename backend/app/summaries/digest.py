"""Digest v2: the editorial daily digest contract.

``content`` schema 2 stored on ``daily_summaries`` (one row per client/day):

    schema      int, always DIGEST_SCHEMA_VERSION
    window      {"from", "to"} ISO datetimes in the settings timezone
    coverage    {"total", "by_source", "by_topic", "gaps"} - deterministic
    noticias    [{topic, event_id, title, sources[{source,url,title}],
                  summary, why_it_matters, media_diversity, veracity, person_ids}]
    agenda      [{when, status?, title, source?}] - LLM narrative
    redes       {<source>: {count, note}} - social sources; note carries the
                LLM narrative when the day has data
    personas    [{person_id, name, role, fact}]
    pendientes  [str] - silent keywords / uncovered events

Only the narrative fields (summary, why_it_matters, agenda, redes note) are
LLM-authored; everything else is deterministic (see
build_digest_facts). validate_digest gates the LLM output:
any error falls back to the heuristic render, mirroring builder.py's mode
contract. Every v2 key is optional: rows authored before home-digest-v2 lack
them and must read back unchanged. Legacy rows that still carry a ``rectora``
key in their stored JSON are tolerated: the section is gone, the key is
ignored at read/render time.
"""

from datetime import datetime, timezone

import logging

from pydantic import ValidationError
from app.summaries.indicators import (
    indicator_line,
    read_indicators,
    story_indicators,
    uses_indicators,
)

from app.summaries.evidence import (
    bind_material_copies,
    bind_output,
    catalogue_sources,
    channel_refs,
    cut_refs,
    freeze_sources,
    resolved_provenance,
)
from app.summaries.digest_schema import (
    BRIEF_CATEGORIES,
    AgendaEntry,
    CuentaEntry,
    NarrativeItem,
    PersonFactEntry,
    SeleccionEntry,
    brief_shape_errors,
)

LOGGER = logging.getLogger(__name__)

DIGEST_SCHEMA_VERSION = 2

#: Fixed confidence scale; never free-form (auditability over prose).
CONFIDENCE_SCALE = ("alta", "media", "baja")

REQUIRED_SECTIONS = ("coverage", "noticias", "redes", "personas", "pendientes")

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
    """Legacy adapter-variety tiers; retained only for compatibility/order."""
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
    mentions: list | None = None,
    window_start: datetime | None = None,
    tracked_social: set[str] | None = None,
) -> dict:
    """Deterministic facts for one client-day. No LLM, no prose.

    ``tracked_social`` uses digest channel keys. Without explicit settings,
    only the always-supported X channel is assumed tracked; observed Facebook
    publications remain reportable without inventing a configured-source gap.

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
    from app.ingest.events import MEDIA_EVENT_SOURCES, is_aggregate_title
    from app.ingest.facebook_public import strip_fb_chrome
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

    evidence = freeze_sources(mentions)
    source_index = {s["mention_id"]: s["index"] for s in evidence["sources"]}
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

    def _representative_key(mention) -> tuple:
        published = mention.published_at
        if published is None:
            published = datetime.min.replace(tzinfo=timezone.utc)
        elif published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return mention.source in MEDIA_EVENT_SOURCES, published, mention.id

    grouped: dict[int | None, list] = {}
    for mention in mentions:
        grouped.setdefault(mention.event_id, []).append(mention)
    noticias: list[dict] = []
    for event_id, items in grouped.items():
        event = events_by_id.get(event_id) if event_id is not None else None
        if event is None:
            # Loose mentions: each its own story (grouping unrelated
            # rows would fabricate a story).
            for mention in items:
                if is_aggregate_title(mention.title):
                    continue
                noticias.append(
                    {
                        "event_id": None,
                        # Read-side chrome strip: rows ingested before the
                        # ingest-side normalization keep FB UI tails; the
                        # digest must render clean titles without a backfill.
                        "title": strip_fb_chrome(mention.title),
                        "summary": mention.summary,
                        "source_refs": [source_index[mention.id]],
                        "material_ref": source_index[mention.id],
                        "topic": _single_topic(mention),
                        "sources": [
                            {
                                "source": mention.source.value,
                                "url": mention.url,
                                "title": strip_fb_chrome(mention.title),
                            }
                        ],
                        **story_indicators(evidence, [source_index[mention.id]]),
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
        eligible = [m for m in items if not is_aggregate_title(m.title)]
        if not eligible:
            continue
        # Keep the full publication inventory and accounting, but never use
        # a multi-story showcase or event-global prose as cut material.
        representative = max(eligible, key=_representative_key)
        noticias.append(
            {
                "event_id": event_id,
                "title": strip_fb_chrome(representative.title),
                "summary": representative.summary,
                "source_refs": [source_index[m.id] for m in eligible],
                "material_ref": source_index[representative.id],
                "topic": topic,
                "sources": [
                    {
                        "source": m.source.value,
                        "url": m.url,
                        "title": strip_fb_chrome(m.title),
                    }
                    for m in items
                ],
                **story_indicators(evidence, [source_index[m.id] for m in eligible]),
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
            # Preserve the exact legacy saturated adapter-variety tiebreak,
            # without publishing it as reliability or ranking by outlets.
            CONFIDENCE_SCALE.index(
                confidence_for(len({s["source"] for s in n["sources"]}))
            ),
        )
    )

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
                "source_refs": [
                    source_index[m.id]
                    for m in mentions
                    if any(link.person_id == person_id for link in m.person_links)
                ],
            }
        )

    # --- redes: supported tracked channels and publications actually observed.
    social_labels = {"x": "X (Twitter)", "facebook_page": "Facebook"}
    social_scope = set(social_labels).intersection(
        {"x"} if tracked_social is None else tracked_social
    )
    social_counts = {
        source: len(channel_refs({"evidence": evidence}, source))
        for source in social_labels
    }
    redes = {
        source: {"count": social_counts[source], "note": ""}
        for source in social_labels
        if source in social_scope or social_counts[source] > 0
    }

    coverage = {
        "total": len(mentions),
        "by_source": dict(by_source),
        "by_topic": dict(by_topic),
        "gaps": gaps_for(counts=social_counts, social=social_scope, labels=social_labels),
    }

    content = {
        "indicators_version": 1,
        "evidence": evidence,
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "coverage": coverage,
        "noticias": noticias,
        "agenda": [],  # narrative, LLM-authored (home-digest-v2)
        "redes": redes,
        "personas": personas,
        "pendientes": [],  # composed at T5: silent keywords + coverage gaps
    }
    bind_material_copies(content)
    return content


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
    headline = _clean_str(payload.get("headline"))
    if headline:
        bind_output(
            content,
            content,
            "headline",
            headline,
            payload,
            "headline",
            cut_refs(content),
        )
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
            for key in ("summary", "why_it_matters", "confidence_note", "angulo_nuevo"):
                value = getattr(narrative_item, key)
                if isinstance(value, str) and value.strip():
                    target[key] = value.strip()
                    bind_output(
                        content,
                        target,
                        key,
                        target[key],
                        payload,
                        f"items.{narrative_item.index}.{key}",
                        target.get("source_refs"),
                    )
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
            for key, text in list(item.items()):
                bind_output(
                    content,
                    item,
                    key,
                    text,
                    payload,
                    f"agenda.{pos}.{key}",
                    cut_refs(content),
                )
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
                bind_output(
                    content,
                    target,
                    "note",
                    note,
                    payload,
                    f"redes.{source}.note",
                    channel_refs(content, source),
                )
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
                    for key, text in list(item.items()):
                        bind_output(
                            content,
                            item,
                            key,
                            text,
                            payload,
                            f"redes.{source}.cuentas.{pos}.{key}",
                            channel_refs(content, source, cuenta),
                        )
                    entries.append(item)
                if entries:
                    target["cuentas"] = entries
    personas = payload.get("personas")
    targets = content.get("personas")
    if isinstance(personas, list) and isinstance(targets, list):
        for pos, entry in enumerate(personas):
            try:
                validated = PersonFactEntry.model_validate(entry)
            except ValidationError as exc:
                _warn_skip(f"personas[{pos}]", exc)
                continue
            fact = _clean_str(validated.fact)
            if fact and pos < len(targets) and isinstance(targets[pos], dict):
                target = targets[pos]
                target["fact"] = fact
                bind_output(
                    content,
                    target,
                    "fact",
                    fact,
                    payload,
                    f"personas.{pos}.fact",
                    target.get("source_refs"),
                )
    return validate_digest(content)


def apply_brief(content: dict, payload: object) -> None:
    """Merge the brief ``seleccion`` into the esqueleto's fixed buckets.

    The selection only REFERENCEStarjetas by index (the model never invents
    structure): each valid entry lands in its categoria bucket. One healthy
    entry switches the buckets to the model's picks wholesale; an explicit
    empty list clears them. Missing/malformed or invalid-only selection
    leaves existing buckets unchanged. Tolerant by contract: malformed
    entries are logged and skipped.
    """
    if not isinstance(content, dict) or not isinstance(content.get("brief"), dict):
        return
    if not isinstance(payload, dict):
        return
    entradas = payload.get("seleccion")
    if not isinstance(entradas, list):
        return
    tarjetas = content.get("tarjetas")
    if isinstance(tarjetas, list):
        total = len(tarjetas)
    else:
        noticias = content.get("noticias")
        total = len(noticias) if isinstance(noticias, list) else 0
    buckets: dict[str, list] = {categoria: [] for categoria in BRIEF_CATEGORIES}
    got = not entradas
    for pos, entry in enumerate(entradas):
        try:
            validated = SeleccionEntry.model_validate(entry)
        except ValidationError as exc:
            _warn_skip(f"seleccion[{pos}]", exc)
            continue
        if not 0 <= validated.index < total:
            _warn_skip(
                "seleccion[%d]" % pos, IndexError(f"index {validated.index} out of range")
            )
            continue
        item: dict = {"index": validated.index}
        razon = _clean_str(validated.razon)
        if razon:
            item["razon"] = razon
            noticias = content.get("noticias") or []
            allowed = (
                noticias[validated.index].get("source_refs")
                if validated.index < len(noticias)
                else []
            )
            bind_output(
                content,
                item,
                "razon",
                razon,
                payload,
                f"seleccion.{validated.index}.razon",
                allowed,
            )
        buckets[validated.categoria].append(item)
        got = True
    if not got:
        return
    content["brief"]["decisiones"] = buckets["decision"]
    content["brief"]["riesgos"] = buckets["riesgo"]
    content["brief"]["ruido"] = buckets["ruido"]
    content["brief"]["a_favor"] = buckets["a_favor"]


def render_plain_text(content: dict, narrative: str) -> str:
    """Sectioned plain text (RAG chunk + readable fallback), es mirrors UI."""
    # Late import: presentation helper vive en builder (T8.C) y el import
    # module-level sería cycle builder->digest->builder.
    from app.summaries.builder import _zone, display_title

    emitted_refs: set[int] = set()

    def marked(target, field, *, text=None, allowed=None, feminine=False):
        value = target.get(field) if text is None else text
        if not isinstance(value, str) or not value:
            return value
        binding = resolved_provenance(
            content, target, field, text=value, allowed=allowed
        )
        if binding["state"] == "linked":
            refs = binding["source_refs"]
            emitted_refs.update(refs)
            citations = ", ".join(f"#{ref}" for ref in refs)
            return f"{value} [Fuentes vinculadas: {citations}]"
        label = "No respaldada" if feminine else "No respaldado"
        return f"{value} [{label}]"

    lines = [marked(content, "headline", text=narrative), ""]
    lines.append("NOTICIAS")
    for item in content.get("noticias") or []:
        indicators = indicator_line(content, item)
        confidence = item.get("confidence") or "?"
        repeat_tag = " (se repite nuevamente)" if item.get("repeat") else ""
        when = item.get("when_label")
        when_tag = f" ({when})" if when else ""
        # T8.C: el texto plano es capa de presentación — título sobrio.
        title = display_title(item.get("title")) or item.get("title") or "(sin título)"
        if indicators is None:
            lines.append(f"- [{confidence}]{when_tag}{repeat_tag} {title}")
        else:
            lines.append(f"-{when_tag}{repeat_tag} {title}")
            lines.append(f"  {indicators}")
        scope = item.get("source_refs") or []
        if item.get("summary"):
            note = (
                f" ({marked(item, 'confidence_note', allowed=scope, feminine=True)})"
                if item.get("confidence_note") and indicators is None
                else ""
            )
            lines.append(
                f"  {marked(item, 'summary', allowed=scope, feminine=True)}{note}"
            )
        if indicators is not None and item.get("confidence_note"):
            lines.append(
                f"  Nota del análisis: {marked(item, 'confidence_note', allowed=scope, feminine=True)}"
            )
        if item.get("why_it_matters"):
            lines.append(
                f"  Por qué importa: {marked(item, 'why_it_matters', allowed=scope, feminine=True)}"
            )
        if item.get("angulo_nuevo"):
            lines.append(
                f"  Ángulo nuevo: {marked(item, 'angulo_nuevo', allowed=scope)}"
            )
        sources = ", ".join(f"{s.get('source')}" for s in item.get("sources") or [])
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
            head = " · ".join(
                value
                for value in (
                    marked(item, "when", feminine=True),
                    marked(item, "status"),
                )
                if value
            )
            title = marked(item, "title", feminine=True)
            line = f"- {head}: {title}" if head else f"- {title}"
            if item.get("source"):
                line += f" Fuente: {marked(item, 'source', feminine=True)}"
            lines.append(line)
    lines.append("")
    lines.append("REDES")
    for source, data in (content.get("redes") or {}).items():
        note = (
            f" — {marked(data, 'note', allowed=channel_refs(content, source), feminine=True)}"
            if isinstance(data, dict) and data.get("note")
            else ""
        )
        count = data.get("count") if isinstance(data, dict) else data
        lines.append(f"- {source}: {count}{note}")
        cuentas = data.get("cuentas") if isinstance(data, dict) else None
        for entry in cuentas or []:
            scope = channel_refs(content, source, entry.get("cuenta"))
            cuenta = marked(entry, "cuenta", allowed=scope, feminine=True)
            nota = marked(entry, "nota", allowed=scope, feminine=True)
            line = f"    - {cuenta}" if cuenta else None
            if line and nota:
                line += f": {nota}"
            if line:
                lines.append(line)
    lines.append("")
    lines.append("PERSONAS")
    for person in content.get("personas") or []:
        role = " · ".join(p for p in (person.get("role"), person.get("org")) if p)
        suffix = f" ({role})" if role else ""
        fact = (
            f": {marked(person, 'fact', allowed=person.get('source_refs') or [], feminine=True)}"
            if person.get("fact")
            else ""
        )
        lines.append(
            f"- {person.get('name')}{suffix} — {person.get('mention_count', 0)} menciones{fact}"
        )
    brief = content.get("brief")
    if isinstance(brief, dict):
        from app.summaries.builder import descarte_label

        tarjetas = content.get("tarjetas")
        noticias = content.get("noticias") or []
        pool = tarjetas if isinstance(tarjetas, list) else noticias

        def _titulo(index: int) -> str:
            if isinstance(pool, list) and 0 <= index < len(pool):
                entry = pool[index]
                if isinstance(entry, dict) and entry.get("titulo"):
                    return display_title(entry["titulo"]) or entry["titulo"]
                if isinstance(entry, dict) and entry.get("title"):
                    return display_title(entry["title"]) or entry["title"]
            return f"#{index}"

        secciones = (
            ("Qué cambió", brief.get("delta"), None),
            ("Riesgos", brief.get("riesgos"), "razon"),
            ("Decisión / atención", brief.get("decisiones"), "razon"),
            ("Ruido", brief.get("ruido"), "razon"),
            ("A favor", brief.get("a_favor"), "razon"),
        )
        lines.append("")
        lines.append("BRIEF")
        descarte = descarte_label(brief.get("descarte"))
        if descarte:
            lines.append(descarte)
        for header, entries, razon_key in secciones:
            if not entries:
                continue
            lines.append(header)
            for entry in entries:
                if razon_key is None:
                    if isinstance(entry, str):
                        text = entry
                        target = {}
                    elif isinstance(entry, dict):
                        title = entry.get("titulo") or ""
                        angle = entry.get("giro")
                        text = (
                            f"{title} — {angle}" if title and angle else title or angle
                        )
                        target = entry
                    else:
                        continue
                    if text:
                        lines.append(
                            f"- {marked(target, 'delta', text=text, feminine=True)}"
                        )
                    continue
                if not isinstance(entry, dict):
                    continue
                index = entry.get("index")
                title = _titulo(index) if isinstance(index, int) else "?"
                scope = (
                    noticias[index].get("source_refs") or []
                    if type(index) is int and 0 <= index < len(noticias)
                    else []
                )
                razon = marked(entry, razon_key, allowed=scope, feminine=True)
                suffix = f" — {razon}" if razon else ""
                lines.append(f"- {title}{suffix}")
        fechas = brief.get("fechas") or []
        if fechas:
            lines.append("Fechas que obligan")
            for fecha in fechas:
                if not isinstance(fecha, dict):
                    continue
                estado = fecha.get("estado") or "?"
                lines.append(
                    f"- [{estado}] {marked(fecha, 'title', feminine=True)} "
                    f"({marked(fecha, 'when', feminine=True)})"
                )
    lines.append("")
    lines.append("PENDIENTES")
    for pending in content.get("pendientes") or []:
        lines.append(f"- {pending}")
    if not content.get("pendientes"):
        lines.append("- ninguno")
    if emitted_refs:
        sources = catalogue_sources(content.get("evidence")) or []
        lines.extend(
            (
                "",
                "FUENTES VINCULADAS",
                "Las referencias registran procedencia, no verificación de verdad.",
            )
        )
        for source in sources:
            if source["index"] not in emitted_refs:
                continue
            title = (
                "Publicación de Facebook"
                if source["source"] == "facebook_page"
                else source.get("title") or "Publicación sin título registrado"
            )
            lines.append(f"- #{source['index']}: {title} — {source['outlet']}")
            if source.get("published_at"):
                try:
                    published = datetime.fromisoformat(source["published_at"])
                    stamp = published.astimezone(
                        _zone(content.get("timezone") or "America/Mexico_City")
                    ).strftime("%d/%m/%Y %H:%M")
                except (ValueError, TypeError):
                    stamp = "fecha no interpretable"
                lines.append(f"  Fecha de publicación: {stamp}")
            lines.append(f"  URL: {source['url']}")
            if source.get("summary"):
                lines.append(f"  Resumen derivado almacenado: {source['summary']}")
            if source.get("excerpt"):
                lines.append(f"  Extracto capturado: {source['excerpt']}")
    return "\n".join(lines)


def validate_digest(content: object) -> list[str]:
    """Return human-readable errors; empty list means well-formed v2."""
    if not isinstance(content, dict):
        return ["digest must be a JSON object"]
    errors: list[str] = []
    if uses_indicators(content):
        if (
            type(content.get("indicators_version")) is not int
            or content["indicators_version"] != 1
        ):
            errors.append("indicators_version must be 1")
        for section in ("noticias", "tarjetas"):
            rows = content.get(section)
            for index, row in enumerate(rows if isinstance(rows, list) else []):
                if not isinstance(row, dict):
                    continue
                if section == "tarjetas" and "notas" in row:
                    notes, indicators = row.get("notas"), row.get("notas_indicators")
                    if (
                        not isinstance(notes, list)
                        or not isinstance(indicators, list)
                        or len(notes) != len(indicators)
                    ):
                        errors.append(f"tarjetas[{index}].notas_indicators must align with notas")
                        continue
                    targets = indicators
                else:
                    targets = [row]
                for target in targets:
                    reading = read_indicators(content, target)
                    if reading is None or reading["identified_outlet_count"] is None:
                        errors.append(f"{section}[{index}] has invalid indicators")
                        break
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
    # digest-brief-v3 keys are optional: absent = legacy row (no errors);
    # present-but-malformed means the build path regressed.
    errors.extend(brief_shape_errors(content))
    return errors
