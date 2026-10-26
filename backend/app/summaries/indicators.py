"""Measured publication diversity, never truth or independent corroboration."""

from app.ingest.article_fetch import _is_google_news, _is_shortener
from app.ingest.events import MEDIA_EVENT_SOURCES
from app.summaries.evidence import catalogue_sources, validated_refs


# Platform identity is not publisher identity, even on a media adapter.
_PLATFORM_HOSTS = (
    "x.com", "twitter.com", "facebook.com", "instagram.com",
    "tiktok.com", "youtube.com", "youtu.be",
)


def _identified_media(source: dict) -> bool:
    outlet = source["outlet"]
    if (
        source["source"] not in MEDIA_EVENT_SOURCES
        or not outlet.strip()
        or outlet.casefold() == "unknown"
    ):
        return False
    # Outlet normalization belongs solely to freeze_sources/_outlet_of.
    # These existing predicates are pure string/URL checks, never resolvers.
    try:
        probe = f"https://{outlet}/rss/articles/"
        if _is_google_news(probe) or _is_shortener(probe):
            return False
    except ValueError:
        return False
    return not any(
        outlet == host or outlet.endswith(f".{host}") for host in _PLATFORM_HOSTS
    )


def story_indicators(evidence: object, refs: object) -> dict:
    """Count only identified frozen media outlets within this story's refs."""
    sources = catalogue_sources(evidence)
    valid = validated_refs(evidence, refs, refs)
    outlets = {
        sources[ref]["outlet"]
        for ref in valid
        if sources is not None and _identified_media(sources[ref])
    }
    return {
        "media_diversity": {"identified_outlet_count": len(outlets)},
        "veracity": "not_evaluated",
    }


_INDICATOR_KEYS = ("indicators_version", "media_diversity", "veracity", "notas_indicators")


def uses_indicators(content: dict, target: dict | None = None) -> bool:
    """Only wholly absent new metadata permits historical confidence views."""
    rows = [content, target or {}]
    for section in ("noticias", "tarjetas"):
        values = content.get(section)
        if isinstance(values, list):
            rows.extend(row for row in values if isinstance(row, dict))
    return any(key in row for row in rows for key in _INDICATOR_KEYS)


def read_indicators(content: dict, target: object) -> dict | None:
    """Strict new/legacy read boundary; malformed new data fails closed."""
    if not uses_indicators(content, target if isinstance(target, dict) else None):
        return None
    count = None
    if (
        type(content.get("indicators_version")) is int
        and content["indicators_version"] == 1
        and isinstance(target, dict)
        and target.get("veracity") == "not_evaluated"
        and isinstance(target.get("media_diversity"), dict)
    ):
        candidate = target["media_diversity"].get("identified_outlet_count")
        if type(candidate) is int and candidate >= 0:
            count = candidate
    return {"identified_outlet_count": count}


def indicator_line(content: dict, target: dict) -> str | None:
    """Spanish presentation of measured diversity, separate from provenance."""
    indicators = read_indicators(content, target)
    if indicators is None:
        return None
    count = indicators["identified_outlet_count"]
    diversity = "no disponible" if count is None else (
        f"{count} medio identificado" if count == 1 else f"{count} medios identificados"
    )
    return f"Diversidad de medios: {diversity}. Veracidad no evaluada"
