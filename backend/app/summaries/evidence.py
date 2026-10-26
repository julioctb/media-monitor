"""Versioned publication inputs, not proof of origin or factual verification."""

from datetime import UTC

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ingest.events import _aware
from app.ingest.facebook_public import strip_fb_chrome
from app.models.queries import _outlet_of

MATERIAL_LIMIT = 300


class _Source(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    index: int = Field(ge=0)
    mention_id: int = Field(gt=0)
    source: str
    url: str
    outlet: str
    author: str | None
    title: str | None
    published_at: str | None
    summary: str | None = Field(max_length=MATERIAL_LIMIT)
    excerpt: str | None = Field(max_length=MATERIAL_LIMIT)


class _Catalogue(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    version: int
    sources: list[_Source]


def catalogue_sources(evidence: object) -> list[dict] | None:
    """Read supported input metadata strictly; this grants no backed status."""
    try:
        catalogue = _Catalogue.model_validate(evidence)
    except ValidationError:
        return None
    if catalogue.version != 1:
        return None
    sources = [source.model_dump() for source in catalogue.sources]
    ids = [source["mention_id"] for source in sources]
    if ids != sorted(set(ids)) or any(
        source["index"] != index for index, source in enumerate(sources)
    ):
        return None
    return sources


def _text(value: str | None) -> str | None:
    """Missing and whitespace-only captured fields are explicitly null."""
    if value is None:
        return None
    return value.strip() or None


def freeze_sources(mentions: list) -> dict:
    """Snapshot only the already-selected cut; never query or fetch articles.

    ``summary`` is stored derivative enrichment, NOT a literal quotation.
    ``excerpt`` captures Mention.content, independently bounded, without
    falling back to a generated summary or inventing absent article text.
    """
    sources = []
    for index, mention in enumerate(sorted(mentions, key=lambda row: row.id)):
        summary = _text(mention.summary)
        excerpt = _text(mention.content)
        sources.append(
            {
                "index": index,
                "mention_id": mention.id,
                "source": mention.source.value,
                "url": mention.url,
                "outlet": _outlet_of(mention.url, mention.author),
                "author": _text(mention.author),
                "title": _text(strip_fb_chrome(mention.title)),
                "published_at": (
                    _aware(mention.published_at).astimezone(UTC).isoformat()
                    if mention.published_at is not None
                    else None
                ),
                "summary": summary[:MATERIAL_LIMIT] if summary else None,
                "excerpt": excerpt[:MATERIAL_LIMIT] if excerpt else None,
            }
        )
    return {"version": 1, "sources": sources}
