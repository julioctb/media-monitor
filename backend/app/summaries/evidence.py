"""Versioned publication inputs, not proof of origin or factual verification."""

import hashlib
import json
from datetime import UTC
from typing import Literal

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


class _ComparisonStory(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    prior_index: int = Field(ge=0, lt=12)
    current_indexes: list[int]
    identity: Literal["registered", "title_fallback"]
    source_refs: list[int]
    material_ref: int | None


class _CoverageContext(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    title: str | None
    tone: dict[str, int] | None


class _ComparisonContext(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    version: int
    available: bool
    date: str | None
    timezone: str | None
    window_start: str | None
    evidence: dict | None
    stories: list[_ComparisonStory] = Field(max_length=12)
    current_source_scopes: list[list[int]]
    coverage_context: list[_CoverageContext] = Field(max_length=12)


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def comparison_context(content: dict) -> dict | None:
    """Validate complete original inputs before selecting namespaces or hashing.

    Foundational validator: comparison.py depends on this module, not vice versa.
    Missing B1 scopes are still usable by B1 recovery, never by two-cut readers.
    """
    try:
        snapshot = _ComparisonContext.model_validate(
            content.get("comparison")
        ).model_dump()
        current = catalogue_sources(content.get("evidence"))
        prior = catalogue_sources(snapshot["evidence"])
        if snapshot["version"] != 1 or current is None:
            return None
        if prior is None and (
            snapshot["evidence"] is not None
            or snapshot["available"]
            or snapshot["stories"]
        ):
            return None
        prior = prior or []
        current_all = [s["index"] for s in current]
        prior_all = [s["index"] for s in prior]
        scopes = snapshot["current_source_scopes"]
        if any(
            validated_refs(content["evidence"], scope, current_all) != scope
            for scope in scopes
        ):
            return None
        seen = set()
        for story in snapshot["stories"]:
            position = story["prior_index"]
            indexes = story["current_indexes"]
            refs = story["source_refs"]
            if (
                position in seen
                or position >= len(snapshot["coverage_context"])
                or any(type(i) is not int or not 0 <= i < len(scopes) for i in indexes)
                or indexes != sorted(set(indexes))
                or not refs
                or validated_refs(snapshot["evidence"], refs, prior_all) != refs
                or story["material_ref"] is not None
                and story["material_ref"] not in refs
            ):
                return None
            seen.add(position)
        if [s["prior_index"] for s in snapshot["stories"]] != sorted(seen):
            return None
        supplied = sorted(
            {ref for story in snapshot["stories"] for ref in story["source_refs"]}
        )
        available = any(
            source["index"] in supplied
            and any(source.get(k) for k in ("title", "summary", "excerpt"))
            for source in prior
        )
        if snapshot["available"] is not available:
            return None
        # Canonical known catalogue fields, never stored claimed hashes.
        snapshot["evidence"] = (
            {"version": 1, "sources": prior}
            if snapshot["evidence"] is not None
            else None
        )
        current_metadata = {
            key: content.get(key) for key in ("date", "timezone", "window_start")
        }
        if any(
            value is not None and not isinstance(value, str)
            for value in current_metadata.values()
        ):
            return None
        canonical = {
            "comparison": snapshot,
            "current": {
                **current_metadata,
                "evidence": {"version": 1, "sources": current},
            },
        }
        return {
            "snapshot": snapshot,
            "fingerprint": _canonical_hash(canonical),
            "current_fingerprint": catalogue_fingerprint(content["evidence"]),
            "prior_fingerprint": catalogue_fingerprint(snapshot["evidence"]),
            "supplied": supplied,
        }
    except (ValidationError, TypeError, ValueError, UnicodeError):
        return None


def _comparison_scope(context: dict | None, allowed: object, kind: str) -> list[int]:
    if context is None or context["snapshot"]["available"] is not True:
        return []
    if kind == "cut":
        return context["supplied"]
    if kind != "story" or not isinstance(allowed, list) or not allowed:
        return []
    scopes = context["snapshot"]["current_source_scopes"]
    positions = [i for i, scope in enumerate(scopes) if scope == allowed]
    return sorted(
        {
            ref
            for story in context["snapshot"]["stories"]
            if any(index in positions for index in story["current_indexes"])
            for ref in story["source_refs"]
        }
    )


_MISSING = object()


def make_binding(
    content: dict,
    text: object,
    refs: object,
    allowed: object,
    *,
    origin: str,
    comparison: object = _MISSING,
    comparison_scope: str = "unsupported",
) -> dict:
    """Backend-created exact-text binding. Linked is provenance, NOT truth."""
    evidence = content.get("evidence")
    validated = (
        validated_refs(evidence, refs, allowed)
        if isinstance(text, str) and text
        else []
    )
    binding = {
        "text": text,
        "source_refs": validated,
        "state": "linked" if validated else "unbacked",
        "origin": origin,
        "catalogue_fingerprint": catalogue_fingerprint(evidence),
    }
    if comparison is not _MISSING:
        context = comparison_context(content)
        raw = comparison if isinstance(comparison, dict) else {}
        current_refs = validated_refs(evidence, raw.get("current"), allowed)
        prior_refs = validated_refs(
            context["snapshot"]["evidence"] if context else None,
            raw.get("prior"),
            _comparison_scope(context, allowed, comparison_scope),
        )
        if set(raw) != {"current", "prior"} or not current_refs or not prior_refs:
            current_refs, prior_refs = [], []
        binding.update(state="unbacked", source_refs=[])
        binding["comparison"] = {
            "version": 1,
            "current": current_refs,
            "prior": prior_refs,
            "scope": comparison_scope,
            "current_catalogue_fingerprint": context["current_fingerprint"]
            if context
            else None,
            "prior_catalogue_fingerprint": context["prior_fingerprint"]
            if context
            else None,
            "context_fingerprint": context["fingerprint"] if context else None,
        }
    return binding


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
    comparison_refs = payload.get("comparison_references")
    comparison = (
        comparison_refs.get(path, _MISSING)
        if isinstance(comparison_refs, dict)
        else None
        if "comparison_references" in payload
        else _MISSING
    )
    kind = (
        "cut"
        if path == "headline"
        else "story"
        if path.startswith(("items.", "seleccion."))
        else "unsupported"
    )
    if (
        field == "angulo_nuevo"
        and isinstance(content.get("comparison"), dict)
        and content["comparison"].get("available") is True
        and comparison is _MISSING
    ):
        comparison = None
    target.setdefault("provenance", {})[field] = make_binding(
        content,
        text,
        refs,
        allowed,
        origin="model_output",
        comparison=comparison,
        comparison_scope=kind,
    )


def resolved_provenance(
    content: dict,
    target: dict,
    field: str,
    *,
    text: str | None = None,
    allowed: object = None,
    position: int | None = None,
    persist: bool = False,
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
    if isinstance(binding, dict) and "comparison" in binding:
        nested = binding["comparison"]
        kind = (
            "cut"
            if field == "headline"
            else "story"
            if field
            in (
                "summary",
                "why_it_matters",
                "confidence_note",
                "angulo_nuevo",
                "razon",
                "hecho",
                "por_que",
                "titulo",
                "title",
                "notas",
            )
            else "unsupported"
        )
        raw = (
            {key: nested.get(key) for key in ("current", "prior")}
            if isinstance(nested, dict)
            else {}
        )
        result = make_binding(
            content,
            value,
            [],
            scope,
            origin=origin,
            comparison=raw,
            comparison_scope=kind,
        )
        expected = result["comparison"]
        valid = (
            known_origin
            and binding.get("state") == "unbacked"
            and isinstance(value, str)
            and bool(value)
            and binding.get("text") == value
            and binding.get("source_refs") == []
            and binding.get("catalogue_fingerprint")
            == expected["current_catalogue_fingerprint"]
            and isinstance(nested, dict)
            and type(nested.get("version")) is int
            and nested == expected
            and bool(expected["current"])
            and bool(expected["prior"])
        )
        if not valid:
            result["comparison"]["current"] = []
            result["comparison"]["prior"] = []
        elif not persist:
            result["state"] = "linked"
            result["source_refs"] = expected["current"]
        return result
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
    comparison_bindings = [binding for binding in bindings if "comparison" in binding]
    if comparison_bindings:
        supported = bool(bindings) and all(
            binding["state"] == "linked" for binding in bindings
        )
        prior = (
            sorted(
                {
                    ref
                    for binding in comparison_bindings
                    for ref in binding["comparison"]["prior"]
                }
            )
            if supported
            else []
        )
        kinds = {binding["comparison"]["scope"] for binding in comparison_bindings}
        return make_binding(
            content,
            text,
            [],
            allowed,
            origin="derived",
            comparison={"current": refs if supported else [], "prior": prior},
            comparison_scope=kinds.pop() if len(kinds) == 1 else "unsupported",
        )
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
            binding = resolved_provenance(
                content, old, field, allowed=allowed, persist=True
            )
            target[field] = text
            target.setdefault("provenance", {})[field] = binding


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
