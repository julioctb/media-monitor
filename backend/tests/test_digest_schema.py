"""Digest v2 contract: section validation for the editorial daily digest."""

import pytest
from pydantic import ValidationError

from app.summaries.digest import DIGEST_SCHEMA_VERSION, validate_digest
from app.summaries.digest_schema import BRIEF_CATEGORIES, SeleccionEntry


def _valid_digest() -> dict:
    return {
        "schema": DIGEST_SCHEMA_VERSION,
        "window": {"from": "2026-10-17T09:00-06:00", "to": "2026-10-18T09:00-06:00"},
        "coverage": {"total": 2, "by_source": {}, "by_topic": {}, "gaps": []},
        "noticias": [],
        "rectora": {},
        "redes": {},
        "personas": [],
        "pendientes": [],
    }


def test_valid_digest_has_no_errors() -> None:
    assert validate_digest(_valid_digest()) == []


def test_missing_sections_and_wrong_schema_fail() -> None:
    errors = validate_digest({"schema": 1})
    assert any("schema" in e for e in errors)
    for section in ("coverage", "noticias", "redes", "personas", "pendientes"):
        assert any(section in e for e in errors)


def test_bad_confidence_and_shape_fail() -> None:
    digest = _valid_digest()
    digest["noticias"] = [{"topic": "institutional", "confidence": "sure"}]
    errors = validate_digest(digest)
    assert errors  # confidence not in the fixed scale

    digest["noticias"] = [{"topic": "institutional", "confidence": "alta", "sources": "oops"}]
    assert any("sources" in e for e in validate_digest(digest))


# ------------------------------------------------------- digest-brief-v3 (T1)


def test_seleccion_entry_validates_known_categories() -> None:
    entry = SeleccionEntry.model_validate({"index": 2, "categoria": "decision"})
    assert entry.index == 2
    assert entry.categoria == "decision"
    assert entry.razon is None
    assert set(BRIEF_CATEGORIES) == {"decision", "riesgo", "ruido", "a_favor"}


def test_seleccion_entry_rejects_unknown_category_and_type() -> None:
    with pytest.raises(ValidationError):
        SeleccionEntry.model_validate({"index": 0, "categoria": "importante"})
    # strict mode: a stringy index is dropped, never coerced
    with pytest.raises(ValidationError):
        SeleccionEntry.model_validate({"index": "2", "categoria": "ruido"})


def test_brief_shape_tolerates_absent_keys() -> None:
    # Legacy v2 rows carry none of the new keys: the brief/campo validation
    # must be silent on their absence (degrada, nunca rompe).
    assert validate_digest(_valid_digest()) == []
    legacy = _valid_digest()
    legacy["noticias"] = [{"confidence": "alta", "sources": []}]
    assert validate_digest(legacy) == []


def test_brief_shape_flags_malformed_sections() -> None:
    digest = _valid_digest()
    digest["noticias"] = [{"confidence": "alta", "sources": []}]
    digest["brief"] = "prose suelta"
    assert any("brief" in e for e in validate_digest(digest))

    digest["brief"] = {"delta": "no lista"}
    assert any("delta" in e for e in validate_digest(digest))

    digest["brief"] = {"decisiones": [{"index": 7, "razon": "fuera de rango"}]}
    assert any("index" in e for e in validate_digest(digest))

    digest["tarjetas"] = {"0": "not a list"}
    assert any("tarjetas" in e for e in validate_digest(digest))

    digest["tarjetas"] = ["tarjeta suelta"]
    assert any("tarjetas[0]" in e for e in validate_digest(digest))

    digest["campo"] = 3
    assert any("campo" in e for e in validate_digest(digest))


def test_reference_map_is_optional_strict_and_guided_by_same_schema():
    from app.summaries.digest_schema import NarrativePayload, narrative_response_schema

    assert NarrativePayload.model_validate({"headline": "Sin citas"}).references is None
    valid = NarrativePayload.model_validate({"references": {"items.0.summary": [0]}})
    assert valid.references == {"items.0.summary": [0]}
    assert "references" in narrative_response_schema()["properties"]
    for invalid in ([False], ["0"], "0"):
        with pytest.raises(ValidationError):
            NarrativePayload.model_validate({"references": {"headline": invalid}})
