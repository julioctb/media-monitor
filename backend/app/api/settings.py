"""Settings endpoints: read/update client configuration + AI probe.

PUT validates through queries.upsert_settings; ValueError maps to 422.
The connectivity probe (AI completion) ALWAYS answers 200 with an
ok/error payload — it exists to be rendered inline by the dashboard, not
to raise.
"""

import time

import httpx
from fastapi import APIRouter, HTTPException

from app.api.deps import ClientIdDep, SessionDep
from app.api.schemas import AiProbeRequest, ClientSettingsOut, ClientSettingsUpdate
from app.models import queries
from app.sentiment.api_analyzer import (
    DEFAULT_OPENAI_MODEL,
    ApiSentimentAnalyzer,
)

router = APIRouter(tags=["settings"])

AI_PROBE_TIMEOUT_S = 10.0

# Local sentinel canary: short, clearly positive, exercises the full path.
_AI_PROBE_TEXT = "Excelente servicio, muy recomendable."


@router.get("/settings", response_model=ClientSettingsOut)
def get_client_settings(
    session: SessionDep, client_id: ClientIdDep
) -> ClientSettingsOut:
    """The client's stored settings (row created lazily on first read)."""
    return queries.get_settings(session, client_id)


@router.get("/clients/{client_id}/scrapers/available")
def available_scrapers(client_id: int) -> list[dict[str, str]]:
    """Scrapers that can be enabled, straight from the ingest registry."""
    from app.ingest.scrapers import SCRAPER_REGISTRY

    return [
        {"name": name, "base_url": spec.base_url}
        for name, spec in SCRAPER_REGISTRY.items()
    ]


@router.put("/settings", response_model=ClientSettingsOut)
def update_client_settings(
    payload: ClientSettingsUpdate, session: SessionDep, client_id: ClientIdDep
) -> ClientSettingsOut:
    """Partial update; semantic validation errors answer 422."""
    changes = payload.model_dump(exclude_unset=True)
    try:
        return queries.upsert_settings(session, client_id, changes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def probe_ai(payload: AiProbeRequest, *, client: httpx.Client | None = None) -> dict:
    """local -> nothing to reach (no local engine since the laya removal);
    openai -> minimal completion against the configured endpoint."""
    if payload.provider == "local":
        return {
            "ok": True,
            "engine": "local",
            "model": None,
            "latency_ms": None,
            "label": None,
            "error": None,
        }

    model = payload.model or DEFAULT_OPENAI_MODEL
    if not payload.api_key:
        return {
            "ok": False,
            "engine": "openai",
            "model": model,
            "latency_ms": None,
            "label": None,
            "error": "api_key is required for the openai provider",
        }
    started = time.perf_counter()
    try:
        analyzer = ApiSentimentAnalyzer(
            api_key=payload.api_key,
            base_url=payload.base_url,
            model=payload.model,
            fallback=None,
            client=client,
            timeout=AI_PROBE_TIMEOUT_S,
            attempts=1,
        )
        result = analyzer.analyze(_AI_PROBE_TEXT, "es")
    except Exception as exc:  # noqa: BLE001 - the probe reports, never raises
        return {
            "ok": False,
            "engine": "openai",
            "model": model,
            "latency_ms": None,
            "label": None,
            "error": str(exc) or exc.__class__.__name__,
        }
    return {
        "ok": True,
        "engine": "openai",
        "model": model,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "label": result.label.value,
        "error": None,
    }


@router.post("/settings/test-ai")
def test_ai_endpoint(payload: AiProbeRequest) -> dict:
    """Probe the sentiment provider; always 200 with ok/error."""
    return probe_ai(payload)
