"""Digest v2: the editorial daily digest contract.

``content`` schema 2 stored on ``daily_summaries`` (one row per client/day):

    schema      int, always DIGEST_SCHEMA_VERSION
    window      {"from", "to"} ISO datetimes in the settings timezone
    coverage    {"total", "by_source", "by_topic", "gaps"} - deterministic
    noticias    [{topic, event_id, title, sources[{source,url,title}],
                  summary, why_it_matters, confidence, person_ids}]
    rectora     {actions[], tone, watch, gaps} - focus-person section
    redes       {<source>: {count, note}} - social sources incl. gaps
    personas    [{person_id, name, role, fact}]
    pendientes  [str] - silent keywords / uncovered events

Only the narrative fields (summary, why_it_matters, tone, watch) are
LL-authored; everything else is deterministic (see build_digest_facts and
confidence_for). validate_digest gates the LLM output: any error falls back
to the heuristic render, mirroring builder.py's mode contract.
"""

from datetime import timezone

DIGEST_SCHEMA_VERSION = 2

#: Fixed confidence scale; never free-form (auditability over prose).
CONFIDENCE_SCALE = ("alta", "media", "baja")

REQUIRED_SECTIONS = ("coverage", "noticias", "rectora", "redes", "personas", "pendientes")


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
) -> dict:
    """Deterministic facts for one client-day. No LLM, no prose.

    Window, source counts and the SQLite/PostgreSQL tz dance mirror
    builder.build_daily_summary (UTC walls over mentions.published_at).
    ``mentions`` optionally injects the day's rows (the composer already
    queried them); otherwise they are loaded here. Ordered by id so the
    section layout is stable across engines.
    """
    from collections import Counter

    from sqlalchemy import select

    from app.models import Event, Mention, Person
    from app.summaries.builder import day_window

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
                        "person_ids": sorted(
                            {p.id for p in mention.person_links}
                        ),
                        "why_it_matters": None,
                    }
                )
            continue
        topic_counts = Counter(
            c.label for m in items for c in m.classifications if c.classifier == "topic"
        )
        topic = topic_counts.most_common(1)[0][0] if topic_counts else None
        person_ids = sorted({p.id for m in items for p in m.person_links})
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
                "person_ids": person_ids,
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
    rectora: dict = {"person_id": focus_person_id, "actions": [], "mention_count": 0}
    if focus_person_id is not None:
        focus_mentions = [
            m for m in mentions if any(p.id == focus_person_id for p in m.person_links)
        ]
        rectora["mention_count"] = len(focus_mentions)
        rectora["actions"] = [
            {
                "title": m.title,
                "event_id": m.event_id,
                "sentiment": m.sentiment.value if m.sentiment else None,
            }
            for m in focus_mentions
        ]
        tones = Counter(
            m.sentiment.value for m in focus_mentions if m.sentiment is not None
        )
        rectora["tone"] = tones.most_common(1)[0][0] if tones else None
        if not focus_mentions:
            rectora["gaps"] = "sin menciones de la persona focal en la ventana"

    # --- personas: everyone linked to the day's mentions, by volume.
    person_counts: Counter[int] = Counter(
        p.id for m in mentions for p in m.person_links
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
        fact = next(
            (
                m.title
                for m in mentions
                if any(p.id == person_id for p in m.person_links) and m.title
            ),
            None,
        )
        personas.append(
            {
                "person_id": person_id,
                "name": person.name,
                "role": person.role,
                "org": person.org,
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
        "rectora": rectora,
        "redes": redes,
        "personas": personas,
        "pendientes": [],  # composed at T5: silent keywords + coverage gaps
    }


def apply_narrative(content: dict, payload: object) -> list[str]:
    """Merge LLM narrative fields into ``content``; return digest errors.

    Expected payload (anything missing or malformed is skipped; the
    deterministic sections are never rewritten):

        {"headline": str,
         "items": [{"index": int, "summary": str, "why_it_matters": str}],
         "rectora": {"tone": str, "watch": str}}
    """
    if not isinstance(content, dict) or not isinstance(payload, dict):
        return ["payload must be an object"]
    items = payload.get("items")
    noticias = content.get("noticias")
    if items is not None:
        if not isinstance(items, list):
            return ["items must be a list"]
        for entry in items:
            if not isinstance(entry, dict) or not isinstance(noticias, list):
                continue
            index = entry.get("index")
            if not isinstance(index, int) or not 0 <= index < len(noticias):
                continue
            target = noticias[index]
            if not isinstance(target, dict):
                continue
            for key in ("summary", "why_it_matters"):
                value = entry.get(key)
                if isinstance(value, str) and value.strip():
                    target[key] = value.strip()
    rectora = payload.get("rectora")
    if isinstance(rectora, dict) and isinstance(content.get("rectora"), dict):
        for key in ("tone", "watch"):
            value = rectora.get(key)
            if isinstance(value, str) and value.strip():
                content["rectora"][key] = value.strip()
    return validate_digest(content)


def render_plain_text(content: dict, narrative: str) -> str:
    """Sectioned plain text (RAG chunk + readable fallback), es mirrors UI."""
    lines = [narrative, ""]
    lines.append("NOTICIAS")
    for item in content.get("noticias") or []:
        confidence = item.get("confidence") or "?"
        lines.append(f"- [{confidence}] {item.get('title') or '(sin título)'}")
        if item.get("summary"):
            lines.append(f"  {item['summary']}")
        if item.get("why_it_matters"):
            lines.append(f"  Por qué importa: {item['why_it_matters']}")
        sources = ", ".join(
            f"{s.get('source')}" for s in item.get("sources") or []
        )
        if sources:
            lines.append(f"  Fuentes: {sources}")
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
