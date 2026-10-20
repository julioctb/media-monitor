"""Digest v2 contract: section validation for the editorial daily digest."""

from app.summaries.digest import DIGEST_SCHEMA_VERSION, validate_digest


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
    for section in ("coverage", "noticias", "rectora", "redes", "personas", "pendientes"):
        assert any(section in e for e in errors)


def test_bad_confidence_and_shape_fail() -> None:
    digest = _valid_digest()
    digest["noticias"] = [{"topic": "institutional", "confidence": "sure"}]
    errors = validate_digest(digest)
    assert errors  # confidence not in the fixed scale

    digest["noticias"] = [{"topic": "institutional", "confidence": "alta", "sources": "oops"}]
    assert any("sources" in e for e in validate_digest(digest))
