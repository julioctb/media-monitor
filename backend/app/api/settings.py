"""Settings endpoints: read/update client configuration + AI probe.

PUT validates through queries.upsert_settings; ValueError maps to 422.
The general connectivity probe (AI completion) ALWAYS answers 200 with an
ok/error payload — it exists to be rendered inline by the dashboard, not
to raise.
"""

import json
import time
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.api.deps import ClientIdDep, SessionDep
from app.api.schemas import AiProbeRequest, ClientSettingsOut, ClientSettingsUpdate
from app.enrich.llm import strip_code_fence
from app.llm_chat import NO_THINK_CHAT_KWARGS
from app.models import queries
from app.models.settings import DEFAULT_OPENAI_BASE_URL, ClientSettings
from app.sentiment.api_analyzer import (
    DEFAULT_OPENAI_MODEL,
    ApiSentimentAnalyzer,
)
from app.settings_runtime import EffectiveSettings, resolve_review_settings
from app.summaries.digest_schema import NarrativePayload, narrative_response_schema

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


def _reviewer_probe_client() -> httpx.Client:
    return httpx.Client(
        timeout=AI_PROBE_TIMEOUT_S, follow_redirects=False, trust_env=False
    )


def _provider_error_code(response: httpx.Response) -> str | None:
    """Machine-readable provider error code only; never its free-text message."""
    try:
        payload = response.json()
    except ValueError:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    if not isinstance(code, str):
        return None
    code = code.strip()
    return code[:200] or None


@router.post("/settings/test-reviewer")
def test_reviewer_endpoint(
    request: Request, session: SessionDep, client_id: ClientIdDep
) -> dict:
    """Probe saved configuration; the marker blocks simple cross-site form POSTs."""
    if request.headers.get("X-Reviewer-Probe") != "1":
        raise HTTPException(
            403, detail="La prueba debe iniciarse desde la configuración del revisor."
        )
    row = session.scalar(
        select(ClientSettings).where(ClientSettings.client_id == client_id)
    )
    failure = {
        "ok": False,
        "message": "Configura y guarda el revisor antes de probar.",
        "latency_ms": None,
        "status_code": None,
        "error_code": None,
    }
    if row is None:
        return failure
    fields = (
        "ai_provider",
        "ai_api_key",
        "ai_base_url",
        "ai_model",
        "digest_reviewer_provider",
        "digest_reviewer_base_url",
        "digest_reviewer_model",
        "digest_reviewer_api_key",
    )
    saved = EffectiveSettings(
        client_id=client_id, **{name: getattr(row, name) for name in fields}
    )
    effective = resolve_review_settings(saved)
    if (
        effective is None
        or effective.ai_provider != "openai"
        or not effective.ai_api_key
    ):
        return failure
    inherited = saved.digest_reviewer_provider == "inherit"
    base = (
        (effective.ai_base_url or (DEFAULT_OPENAI_BASE_URL if inherited else ""))
        .strip()
        .rstrip("/")
    )
    model = effective.ai_model or (DEFAULT_OPENAI_MODEL if inherited else None)
    try:
        url = urlsplit(base)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or any(char.isspace() for char in base)
        ):
            return failure
        url.port  # Validate an explicitly supplied port before dispatch.
    except ValueError:
        return failure
    if url.path.lower().endswith("/chat/completions"):
        # A base URL that already points at the chat operation would duplicate
        # the suffix; reject deterministically instead of spending a request.
        return {
            "ok": False,
            "message": "La URL base ya incluye /chat/completions; guarda solo la URL base del servicio.",
            "latency_ms": None,
            "status_code": None,
            "error_code": None,
        }
    if not model:
        return failure
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Responde solo OK."}],
        "max_tokens": 64,
    }
    if inherited:
        body["chat_template_kwargs"] = dict(NO_THINK_CHAT_KWARGS)
    started = time.perf_counter()
    client = None
    status_code: int | None = None
    error_code: str | None = None
    try:
        client = _reviewer_probe_client()
        response = client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {effective.ai_api_key}"},
            json=body,
            timeout=AI_PROBE_TIMEOUT_S,
            follow_redirects=False,
        )
        status_code = response.status_code
        if not response.is_success:
            error_code = _provider_error_code(response)
        if response.status_code in {401, 403}:
            message = "El proveedor rechazó la clave o sus permisos."
        elif response.is_redirect:
            message = "El servicio devolvió una redirección; revisa la URL base."
        elif response.status_code == 429:
            message = "El proveedor alcanzó su límite de solicitudes o cuota."
        elif not response.is_success:
            message = "El proveedor rechazó la prueba; revisa el modelo y la URL base."
        else:
            try:
                message_data = response.json()["choices"][0]["message"]
                content = message_data.get("content")
                reasoning = message_data.get("reasoning_content") or message_data.get(
                    "reasoning"
                )
                if isinstance(content, str) and content.strip():
                    return {
                        "ok": True,
                        "message": "Conexión correcta: el modelo respondió a la prueba.",
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                        "status_code": status_code,
                        "error_code": None,
                    }
                if isinstance(reasoning, str) and reasoning.strip():
                    return {
                        "ok": True,
                        "message": "Conexión correcta: el servicio aceptó el modelo, pero la prueba breve no obtuvo texto final.",
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                        "status_code": status_code,
                        "error_code": None,
                    }
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                pass
            message = "El servicio respondió sin un mensaje de chat válido."
    except httpx.TimeoutException:
        message = "El servicio no respondió dentro del tiempo de espera."
    except Exception:
        # Provider exceptions can contain URLs, credentials or response bodies.
        message = "No se pudo contactar el servicio del revisor."
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    return {
        "ok": False,
        "message": message,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "status_code": status_code,
        "error_code": error_code,
    }


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
        "chat_template_kwargs": NO_THINK_CHAT_KWARGS,
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
