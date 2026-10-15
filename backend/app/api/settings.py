"""Settings endpoints: read/update client configuration + probes (T9).

PUT validates through queries.upsert_settings; ValueError maps to 422.
The connectivity probes (Graph page token, AI completion) ALWAYS answer
200 with an ok/error payload — they exist to be rendered inline by the
dashboard, not to raise.
"""

import time

import httpx
from fastapi import APIRouter, HTTPException

from app.api.deps import ClientIdDep, SessionDep
from app.api.schemas import (
    AiProbeRequest,
    ClientSettingsOut,
    ClientSettingsUpdate,
    FacebookProbeRequest,
)
from app.config import settings as env_settings
from app.models import queries
from app.sentiment.api_analyzer import (
    DEFAULT_OPENAI_MODEL,
    ApiSentimentAnalyzer,
)

router = APIRouter(tags=["settings"])

FB_PROBE_TIMEOUT_S = 10.0
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


def probe_facebook_page(
    page_id: str, token: str, *, client: httpx.Client | None = None
) -> dict:
    """GET /{version}/{page_id}?fields=name,link with the page token."""
    owns_client = client is None
    client = client or httpx.Client(timeout=FB_PROBE_TIMEOUT_S)
    failure = {"ok": False, "error": None, "name": None, "link": None}
    try:
        resp = client.get(
            f"https://graph.facebook.com/{env_settings.fb_graph_api_version}/{page_id}",
            params={"fields": "name,link", "access_token": token},
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        failure["error"] = str(exc) or exc.__class__.__name__
        return failure
    finally:
        if owns_client:
            client.close()
    if not isinstance(data, dict):
        failure["error"] = "unexpected Graph response"
        return failure
    if "error" in data:
        message = (data.get("error") or {}).get("message") or "unknown Graph error"
        failure["error"] = message
        return failure
    return {
        "ok": True,
        "error": None,
        "name": data.get("name"),
        "link": data.get("link"),
    }


def probe_ai(payload: AiProbeRequest, *, client: httpx.Client | None = None) -> dict:
    """local -> engine ok without loading anything; openai -> minimal completion."""
    if payload.provider == "local":
        # Constructing LayaAnalyzer is lazy: no model download, no load.
        from app.sentiment.laya_analyzer import LayaAnalyzer

        LayaAnalyzer()
        return {
            "ok": True,
            "engine": "laya",
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


@router.post("/settings/test-facebook")
def test_facebook_endpoint(payload: FacebookProbeRequest) -> dict:
    """Validate a page token against Graph; always 200 with ok/error."""
    return probe_facebook_page(payload.page_id, payload.token)


@router.post("/settings/test-ai")
def test_ai_endpoint(payload: AiProbeRequest) -> dict:
    """Probe the sentiment provider; always 200 with ok/error."""
    return probe_ai(payload)
