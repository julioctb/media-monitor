"""Enrichment suggestions for field reports.

The LLM proposes a clean title, a summary and a tone; the module also flags
title-level duplicates against the live feed. EVERYTHING here is a
suggestion written to ``field_reports.enrichment``: state never changes and
the review queue decides. Failure is always non-fatal (best effort).
"""

import json
import logging

from pydantic import BaseModel

from app.enrich.llm import LLMEnricher, strip_code_fence
from app.models import Mention, queries
from app.settings_runtime import resolve_effective_settings

logger = logging.getLogger("field.enrich")

#: Recent mentions scanned for the duplicate flag.
DEDUPE_SCAN_LIMIT = 200


class FieldEnrichment(BaseModel):
    """The suggestion shape; extra keys are kept for diagnostics."""

    suggested_title: str | None = None
    summary: str | None = None
    tone: str | None = None
    duplicate: bool = False

    def clean(self) -> "FieldEnrichment":
        return FieldEnrichment(
            suggested_title=self.suggested_title.strip() if self.suggested_title else None,
            summary=self.summary.strip() if self.summary else None,
            tone=self.tone.strip().lower() if self.tone else None,
            duplicate=self.duplicate,
        )


ENRICH_SYSTEM = (
    "Eres editor de monitoreo. Recibes un reporte de campo crudo (texto de"
    " alguien en territorio). Devuelve EXCLUSIVAMENTE un JSON con:"
    ' {"suggested_title": titulo periodistico <=100 caracteres,'
    ' "summary": 1 o 2 oraciones con el hecho, "tone": "positive"|"negative"|'
    '"neutral"}. Usa SOLO la informacion dada; nada de datos nuevos.'
)


def build_enricher(session, client_id: int) -> LLMEnricher | None:
    """Provider gate: None when no OpenAI-compatible settings (silent skip)."""
    effective = resolve_effective_settings(session, client_id)
    provider = (effective.ai_provider or "").strip().lower()
    api_key = (effective.ai_api_key or "").strip()
    if provider != "openai" or not api_key:
        return None
    return LLMEnricher(
        api_key=api_key,
        base_url=effective.ai_base_url,
        model=effective.ai_model,
    )


def _has_duplicate_title(session, client_id: int, title: str) -> bool:
    normalized = queries._normalized_title(title)
    rows = session.query(Mention.id, Mention.title).filter_by(client_id=client_id).limit(200).all()
    return any(
        title_db and queries._normalized_title(title_db) == normalized
        for _id, title_db in rows
    )


def enrich_report(session, report) -> dict | None:
    """One enrichment pass; returns the dict written or None.

    Duplicate detection is mechanical (normalized-title match over the
    client's mentions); title/summary/tone come from the model. Never
    raises to the caller's flow.
    """
    try:
        enricher = build_enricher(session, report.client_id)
        if enricher is None:
            return None
        facts = {
            "titulo": report.title,
            "contenido": report.content,
            "lugar": report.place,
        }
        user = json.dumps(facts, ensure_ascii=False)
        raw = enricher.complete(ENRICH_SYSTEM, user, json_mode=True)
        if not raw:
            return None
        data = json.loads(strip_code_fence(raw))
        parsed = FieldEnrichment.model_validate(data).clean()
        if parsed.suggested_title:
            parsed.duplicate = _has_duplicate_title(session, report.client_id, parsed.suggested_title)
        return parsed.model_dump()
    except Exception as exc:  # noqa: BLE001 - suggestions are best effort
        logger.warning("field enrichment failed for report %s: %s", report.id, exc)
        return None


def enrich_report_by_id(db_factory, client_id: int, report_id: int) -> dict | None:
    """Session-owned variant for the bot loop; commits on success."""
    with db_factory() as db:
        report = queries.get_field_report(db, client_id, report_id)
        if report is None or report.status != "review":
            return None
        enrichment = enrich_report(db, report)
        if enrichment is None:
            return None
        report.enrichment = enrichment
        db.commit()
        return enrichment
