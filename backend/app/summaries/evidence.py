"""Versioned publication inputs, not proof of origin or factual verification."""

import hashlib
import json
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
    evidence = {"version": 1, "sources": sources}
    evidence["catalogue_fingerprint"] = catalogue_fingerprint(evidence)
    return evidence


def catalogue_fingerprint(evidence: object) -> str | None:
    """Hash validated v1 material, ignoring any claimed fingerprint/extra keys."""
    sources = catalogue_sources(evidence)
    if sources is None:
        return None
    canonical = json.dumps(
        {"version": 1, "sources": sources},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validated_refs(evidence: object, refs: object, allowed: object) -> list[int]:
    """All-or-nothing strict reference validation; never salvage a bad set."""
    sources = catalogue_sources(evidence)
    if sources is None or not isinstance(allowed, list) or not isinstance(refs, list):
        return []
    size = len(sources)
    if any(type(ref) is not int or not 0 <= ref < size for ref in allowed):
        return []
    if any(type(ref) is not int or ref not in allowed for ref in refs):
        return []
    return sorted(set(refs))


def make_binding(
    content: dict,
    text: object,
    refs: object,
    allowed: object,
    *,
    origin: str,
) -> dict:
    """Backend-created exact-text binding. Linked is provenance, NOT truth."""
    evidence = content.get("evidence")
    validated = (
        validated_refs(evidence, refs, allowed)
        if isinstance(text, str) and text
        else []
    )
    return {
        "text": text,
        "source_refs": validated,
        "state": "linked" if validated else "unbacked",
        "origin": origin,
        "catalogue_fingerprint": catalogue_fingerprint(evidence),
    }


def cut_refs(content: dict) -> list[int]:
    sources = catalogue_sources(content.get("evidence"))
    return [source["index"] for source in sources or []]


def channel_refs(content: dict, channel: str, account: str | None = None) -> list[int]:
    sources = catalogue_sources(content.get("evidence"))
    return [
        source["index"]
        for source in sources or []
        if source["source"] == ("x_twitter" if channel == "x" else channel)
        and (account is None or source["author"] == account)
    ]


def bind_output(
    content: dict,
    target: dict,
    field: str,
    text: str,
    payload: dict,
    path: str,
    allowed: object,
) -> None:
    """Bind already-normalized prose; reference errors never reject prose.

    Exact dotpaths (decimal zero-based indexes, no brackets):
      headline
      items.<index>.summary|why_it_matters|confidence_note|angulo_nuevo
      seleccion.<index>.razon
      agenda.<position>.when|title|status|source
      redes.<channel>.note
      redes.<channel>.cuentas.<position>.cuenta|nota
      personas.<position>.fact
    A vertical bar lists separate allowed final field names, not a literal
    path. index is the seeded news/card semantic index; position is the raw
    input array position BEFORE validation/skipping. Card hecho/por_que/
    angulo_nuevo derive from items summary/why_it_matters/angulo_nuevo;
    tarjetas is not an alternative model prose input. Unknown paths ignored.
    """
    references = payload.get("references")
    refs = references.get(path) if isinstance(references, dict) else None
    target.setdefault("provenance", {})[field] = make_binding(
        content,
        text,
        refs,
        allowed,
        origin="model_output",
    )


def resolved_provenance(
    content: dict,
    target: dict,
    field: str,
    *,
    text: str | None = None,
    allowed: object = None,
    position: int | None = None,
) -> dict:
    """Resolve stored metadata against RAW applied text, before UI cleaning.

    Missing/legacy/stale/unsupported bindings are unbacked. ``position``
    reads an individual compiled ``notas`` binding, never their shared union.
    Callers rendering a headline pass the actual narrative as ``text``.
    """
    value = target.get(field) if text is None else text
    provenance = target.get("provenance")
    binding = provenance.get(field) if isinstance(provenance, dict) else None
    if position is not None:
        value = (
            value[position]
            if isinstance(value, list) and 0 <= position < len(value)
            else None
        )
        binding = (
            binding[position]
            if isinstance(binding, list) and 0 <= position < len(binding)
            else None
        )
    scope = cut_refs(content) if allowed is None else allowed
    origin = binding.get("origin") if isinstance(binding, dict) else None
    known_origin = origin in (
        "model_output",
        "source_material",
        "derived",
        "revision_restore",
        "fallback",
    )
    if not known_origin:
        origin = "fallback"
    valid = (
        known_origin
        and isinstance(binding, dict)
        and binding.get("state") == "linked"
        and binding.get("text") == value
        and binding.get("catalogue_fingerprint") is not None
        and binding["catalogue_fingerprint"]
        == catalogue_fingerprint(content.get("evidence"))
    )
    refs = binding.get("source_refs") if valid and isinstance(binding, dict) else []
    return make_binding(content, value, refs, scope, origin=origin)


def derive_provenance(
    content: dict, text: str, parents: list[tuple[dict, str]], allowed: object
) -> dict:
    """Only explicit, known code transformations may use ALL their parents."""
    bindings = [
        resolved_provenance(content, target, field, allowed=allowed)
        for target, field in parents
    ]
    refs = sorted({ref for binding in bindings for ref in binding["source_refs"]})
    if not bindings or any(binding["state"] != "linked" for binding in bindings):
        refs = []
    return make_binding(content, text, refs, allowed, origin="derived")


def compiled_provenance(content: dict, tarjeta: dict, text: str) -> dict:
    """Known bullet formatting uses BOTH prose and frozen channel labels."""
    allowed = tarjeta.get("source_refs")
    scope = validated_refs(content.get("evidence"), allowed, allowed)
    parents = [(tarjeta, "titulo" if tarjeta.get("titulo") else "hecho")]
    sources = catalogue_sources(content.get("evidence")) or []
    for name in tarjeta.get("fuentes") or []:
        refs = [
            source["index"]
            for source in sources
            if source["index"] in scope and source["source"] == name
        ]
        source_copy = {
            "source": name,
            "provenance": {
                "source": make_binding(
                    content,
                    name,
                    refs,
                    scope,
                    origin="source_material",
                )
            },
        }
        parents.append((source_copy, "source"))
    return derive_provenance(content, text, parents, scope)


def inherit_fields(
    content: dict, target: dict, old: dict, fields: tuple, allowed: object
) -> None:
    """Carry prose only after the builder's complete-cut material guard."""
    for field in fields:
        text = old.get(field)
        if isinstance(text, str) and text:
            binding = resolved_provenance(content, old, field, allowed=allowed)
            target[field] = text
            target.setdefault("provenance", {})[field] = make_binding(
                content,
                text,
                binding["source_refs"],
                allowed,
                origin=binding["origin"],
            )


def bind_material_copies(content: dict) -> None:
    """Explicit source-copy path, never a text-match search over publications.

    A full summary longer than the frozen input remains unbacked. Legacy
    person facts lack a selected frozen material ref and remain unbacked;
    never guess one by matching names or coincidentally equal wording.
    """
    sources = catalogue_sources(content.get("evidence")) or []
    for target in content.get("noticias", []) + content.get("personas", []):
        ref = target.get("material_ref")
        for field in ("title", "summary") if "material_ref" in target else ("fact",):
            text = target.get(field)
            if not isinstance(text, str) or not text:
                continue
            source_field = "title" if field in ("title", "fact") else "summary"
            matches = (
                type(ref) is int
                and 0 <= ref < len(sources)
                and text.strip() == sources[ref][source_field]
            )
            target.setdefault("provenance", {})[field] = make_binding(
                content,
                text,
                [ref] if matches else [],
                target.get("source_refs"),
                origin="source_material",
            )
