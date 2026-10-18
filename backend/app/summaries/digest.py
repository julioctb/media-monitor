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
