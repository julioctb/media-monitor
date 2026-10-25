"""Settings endpoints: read/update client configuration + AI probe.

PUT validates through queries.upsert_settings; ValueError maps to 422.
The connectivity probe (AI completion) ALWAYS answers 200 with an
ok/error payload — it exists to be rendered inline by the dashboard, not
to raise.
"""

import json
import time

import httpx
from fastapi import APIRouter, HTTPException

from app.api.deps import ClientIdDep, SessionDep
from app.api.schemas import AiProbeRequest, ClientSettingsOut, ClientSettingsUpdate
from app.enrich.llm import strip_code_fence
from app.models import queries
from app.sentiment.api_analyzer import (
    DEFAULT_OPENAI_MODEL,
    ApiSentimentAnalyzer,
)
from app.summaries.digest_schema import NarrativePayload, narrative_response_schema
from app.models.settings import DEFAULT_OPENAI_BASE_URL

router = APIRouter(tags=["settings"])

AI_PROBE_TIMEOUT_S = 10.0

# Local sentinel canary: short, clearly positive, exercises the full path.
_AI_PROBE_TEXT = "El servicio de la biblioteca fue excelente, muy recomendable."


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
    result = probe_ai(payload)
    if result["ok"] and payload.provider == "openai":
        # The digest narrative path has its own failure modes (guided
        # json_schema support, parseable shape); probe it in the same
        # click so Configuración is the single diagnostic surface.
        result["narrative"] = probe_narrative(payload)
    return result


_NARRATIVE_PROBE_PROMPT = 'Responde solo un JSON: {"items": [], "headline": "prueba"}'


def _narrative_body(payload: AiProbeRequest, response_format: dict | None) -> dict:
    body: dict = {
        "model": payload.model or DEFAULT_OPENAI_MODEL,
        "messages": [{"role": "user", "content": _NARRATIVE_PROBE_PROMPT}],
        "temperature": 0,
    }
    if response_format is not None:
        body["response_format"] = response_format
    return body


def probe_narrative(
    payload: AiProbeRequest,
    *,
    client: httpx.Client | None = None,
    timeout: float = AI_PROBE_TIMEOUT_S,
) -> dict:
    """Digest-narrative path probe: guided json_schema, plain fallback.

    ok + json_schema='supported' -> the endpoint took the schema and the
    answer parses as NarrativePayload (the exact builder contract).
    ok + 'unsupported' -> schema call failed, plain call worked: the
    builder retry covers this server; detail carries the schema error.
    ok False -> neither path worked; error carries the last exception.

    Never raises: the probe reports, the UI renders.
    """
    if not payload.api_key:
        return {"ok": False, "json_schema": None, "latency_ms": None, "detail": None,
                "error": "api_key is required for the openai provider"}
    base_url = (payload.base_url or DEFAULT_OPENAI_BASE_URL).rstrip("/")
    headers = {"Authorization": f"Bearer {payload.api_key}"}
    owned = client is None
    client = client or httpx.Client(timeout=timeout)

    def _post(body: dict) -> str:
        resp = client.post(f"{base_url}/chat/completions", headers=headers, json=body)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty narrative content")
        return strip_code_fence(content)

    def _elapsed(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    schema_body = {
        "type": "json_schema",
        "json_schema": {"name": "digest_narrative", "schema": narrative_response_schema()},
    }
    try:
        started = time.perf_counter()
        raw = _post(_narrative_body(payload, schema_body))
        NarrativePayload.model_validate(json.loads(raw))
        if owned:
            client.close()
        return {
            "ok": True,
            "json_schema": "supported",
            "latency_ms": _elapsed(started),
            "detail": None,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        detail = str(exc) or exc.__class__.__name__

    try:
        started = time.perf_counter()
        raw = _post(_narrative_body(payload, None))
        json.loads(raw)  # without guidance, a parseable object is enough
        return {
            "ok": True,
            "json_schema": "unsupported",
            "latency_ms": _elapsed(started),
            "detail": detail,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "json_schema": None,
            "latency_ms": None,
            "detail": detail,
            "error": str(exc) or exc.__class__.__name__,
        }
    finally:
        if owned:
            client.close()
