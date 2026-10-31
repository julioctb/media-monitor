"""Llamadas mecánicas de chat: thinking desactivado por payload (31/oct).

El despliegue vLLM de Qwen híbrido trae razonamiento ENCENDIDO por defecto:
el razonamiento consume el max_tokens pedido (content vuelve null) y
multiplica la latencia, lo que tumbó el enriquecimiento (timeout 20 s) y
amenaza el digest. Todo payload de chat/completions de tarea mecánica
(clasificación, extracción, resumen, probe) debe mandar
``chat_template_kwargs={"enable_thinking": False}``.
"""

import json

import httpx

from app.api.schemas import AiProbeRequest
from app.api.settings import probe_ai
from app.enrich.llm import LLMEnricher
from app.sentiment.api_analyzer import ApiSentimentAnalyzer
from app.settings_runtime import EffectiveSettings
from app.spike import summary as spike_summary
from app.summaries import builder


def _capture_handler():
    """(bodies, handler): captura el JSON de cada POST completions."""
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"sentiment": "neutral"})}}
                ]
            },
        )

    return bodies, handler


def _assert_no_think(bodies: list[dict]) -> None:
    assert bodies, "el sitio nunca llamó a chat/completions"
    for body in bodies:
        kwargs = body.get("chat_template_kwargs")
        assert kwargs == {"enable_thinking": False}, (
            f"falta chat_template_kwargs.enable_thinking=false: {body.keys()}"
        )


def test_sentiment_analyzer_sends_no_think():
    bodies, handler = _capture_handler()
    analyzer = ApiSentimentAnalyzer(
        api_key="k",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        analyzer.analyze("La BUAP inauguró un laboratorio.", "es")
    except Exception:
        pass  # solo importa el payload enviado
    _assert_no_think(bodies)


def test_enricher_sends_no_think():
    bodies, handler = _capture_handler()
    enricher = LLMEnricher(
        api_key="k",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        enricher.enrich("Nota de prueba sobre BUAP.")
    except Exception:
        pass
    _assert_no_think(bodies)


def test_digest_generator_sends_no_think(monkeypatch):
    captured: list[dict] = []

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "hola"}}]}

    def fake_post(url, **kwargs):
        captured.append(kwargs.get("json") or {})
        return _Resp()

    monkeypatch.setattr(builder.httpx, "post", fake_post)
    cfg = EffectiveSettings(
        client_id=1,
        ai_base_url="https://fixture.invalid/v1",
        ai_model="fixture",
        ai_api_key="fixture-only",
    )
    builder._openai_generator(cfg)("prompt de prueba")
    _assert_no_think(captured)


def test_spike_summary_generator_sends_no_think(monkeypatch):
    captured: list[dict] = []

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "resumen"}}]}

    def fake_post(url, **kwargs):
        captured.append(kwargs.get("json") or {})
        return _Resp()

    monkeypatch.setattr(spike_summary.httpx, "post", fake_post)

    class _Row:
        ai_provider = "openai"
        ai_api_key = "k"
        ai_base_url = "https://fixture.invalid/v1"
        ai_model = "fixture"

    gen = spike_summary.build_summary_generator(_Row())
    assert gen is not None, "provider openai configurado debe generar callable"
    gen("prompt de pico")
    _assert_no_think(captured)


def test_ai_probe_sends_no_think():
    bodies, handler = _capture_handler()
    probe_ai(
        AiProbeRequest(
            provider="openai",
            api_key="k",
            base_url="https://fixture.invalid/v1",
            model="fixture",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    _assert_no_think(bodies)
