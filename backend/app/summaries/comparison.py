"""Original prior-cut inputs, separate from current-cut evidence and conclusions."""

import copy
import json
from collections.abc import Callable

from app.summaries.evidence import catalogue_sources, validated_refs


PRIOR_STORY_LIMIT = 12


def comparison_compatible(content: dict, previous: dict) -> bool:
    """Known new contexts require exact typed equality, never a claimed hash.

    Legacy recovery retains its old meaning only without factual prior input;
    the caller must not stamp it with newly attributed comparison authorship.
    """
    current = content["comparison"]
    if "comparison" not in previous:
        return current["available"] is False
    old = previous["comparison"]
    if not isinstance(old, dict):
        return False
    try:
        return json.dumps(old, sort_keys=True, allow_nan=False) == json.dumps(
            current, sort_keys=True, allow_nan=False
        )
    except (TypeError, ValueError):
        return False


def freeze_comparison(previous, noticias: list, identity: Callable) -> dict:
    """Snapshot only the selected tenant-owned row; never load mutable sources.

    The complete original catalogue stays valid and retains its indexes.
    Only selected stories' own publications will enter the model projection.
    Availability concerns supplied material, not factual truth or change.
    """
    prior = previous.content if previous is not None else None
    prior = prior if isinstance(prior, dict) else {}
    news = prior.get("noticias")
    news = news if isinstance(news, list) else []
    sources = catalogue_sources(prior.get("evidence"))
    snapshot = {
        "version": 1,
        "available": False,
        "date": previous.summary_date.isoformat() if previous is not None else None,
        "timezone": prior.get("timezone")
        if isinstance(prior.get("timezone"), str)
        else None,
        "window_start": prior.get("window_start")
        if isinstance(prior.get("window_start"), str)
        else None,
        "evidence": copy.deepcopy(prior["evidence"]) if sources is not None else None,
        "stories": [],
        "coverage_context": [
            {"title": note.get("title"), "tone": copy.deepcopy(note.get("tone"))}
            for note in news[:PRIOR_STORY_LIMIT]
            if isinstance(note, dict)
        ],
    }
    if sources is None:
        return snapshot
    allowed = [source["index"] for source in sources]
    for position, note in enumerate(news[:PRIOR_STORY_LIMIT]):
        if not isinstance(note, dict):
            continue
        refs = validated_refs(prior["evidence"], note.get("source_refs"), allowed)
        if not refs:
            continue
        key = identity(note)
        material = note.get("material_ref")
        snapshot["stories"].append(
            {
                "prior_index": position,
                "current_indexes": [
                    index
                    for index, current in enumerate(noticias)
                    if key is not None and identity(current) == key
                ],
                "identity": "registered"
                if note.get("event_id") is not None
                else "title_fallback",
                "source_refs": refs,
                "material_ref": material
                if type(material) is int and material in refs
                else None,
            }
        )
    supplied = {ref for story in snapshot["stories"] for ref in story["source_refs"]}
    snapshot["available"] = any(
        source["index"] in supplied
        and any(source.get(field) for field in ("title", "summary", "excerpt"))
        for source in sources
    )
    return snapshot


def comparison_prompt_view(snapshot: dict) -> dict:
    """Use explicit prior names, with no IDs, URLs or previous authored prose."""
    stories = copy.deepcopy(snapshot["stories"])
    refs = {ref for story in stories for ref in story["source_refs"]}
    for story in stories:
        story["source_refs"] = [f"prior:{ref}" for ref in story["source_refs"]]
        if story["material_ref"] is not None:
            story["material_ref"] = f"prior:{story['material_ref']}"
    return {
        **{
            key: snapshot[key]
            for key in ("available", "date", "timezone", "window_start")
        },
        "stories": stories,
        "sources": [
            {
                **{
                    key: value
                    for key, value in source.items()
                    if key not in ("mention_id", "url", "index")
                },
                "index": f"prior:{source['index']}",
            }
            for source in catalogue_sources(snapshot["evidence"]) or []
            if source["index"] in refs
        ],
    }
