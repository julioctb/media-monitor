"""Public text export keeps prose and distinguishes traceability from truth."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from app.models import MentionSource
from app.summaries.digest import render_plain_text
from app.summaries.evidence import freeze_sources, make_binding


def _report():
    return {
        "noticias": [
            {
                "title": "Titular de prueba",
                "summary": "Reseña de prueba.",
                "why_it_matters": "Importancia de prueba.",
                "confidence_note": "Nota documental.",
                "angulo_nuevo": "Detalle nuevo.",
                "confidence": "media",
                "sources": [{"source": "news_rss"}],
                "source_refs": [0],
            }
        ],
        "agenda": [
            {
                "when": "26 oct.",
                "title": "Actividad de prueba.",
                "status": "Pendiente.",
                "source": "Publicación de prueba.",
            }
        ],
        "redes": {
            "x": {
                "count": 1,
                "note": "Nota del canal.",
                "cuentas": [{"cuenta": "@prueba", "nota": "Nota de cuenta."}],
            }
        },
        "personas": [
            {
                "name": "Persona de prueba",
                "role": "Cargo registrado",
                "mention_count": 1,
                "fact": "Reseña de persona.",
                "source_refs": [0],
            }
        ],
        "brief": {
            "delta": [
                {"titulo": "Cambio de prueba", "giro": "Detalle del cambio."},
                "Cambio heredado.",
            ],
            "riesgos": [{"index": 0, "razon": "Riesgo de prueba."}],
            "decisiones": [{"index": 0, "razon": "Atención de prueba."}],
            "ruido": [{"index": 0, "razon": "Ruido de prueba."}],
            "a_favor": [{"index": 0, "razon": "Resultado de prueba."}],
        },
        "pendientes": [],
    }


def _with_sources():
    content = _report()
    content["evidence"] = freeze_sources(
        [
            SimpleNamespace(
                id=11,
                source=MentionSource.news_rss,
                url="https://source-one.test/nota",
                author=None,
                title="Publicación citada",
                published_at=datetime(2026, 10, 9, 15, tzinfo=timezone.utc),
                summary="Resumen derivado de prueba.",
                content="Extracto capturado de prueba.",
            ),
            SimpleNamespace(
                id=12,
                source=MentionSource.x_twitter,
                url="https://unused-source.test/nota",
                author="@prueba",
                title="Publicación no utilizada",
                published_at=datetime(2026, 10, 9, 16, tzinfo=timezone.utc),
                summary="Material sin referencia.",
                content="Texto no citado.",
            ),
        ]
    )
    return content


def _bind(content, target, field, text, refs):
    target.setdefault("provenance", {})[field] = make_binding(
        content, text, refs, [0, 1], origin="model_output"
    )


def test_plain_export_marks_uncited_fields_without_losing_prose():
    content = _report()
    plain = render_plain_text(content, "Lectura de prueba.")
    assert plain.startswith("Lectura de prueba. [No respaldado]\n")
    for text in (
        "Reseña de prueba.",
        "Importancia de prueba.",
        "Nota documental.",
        "Nota del canal.",
        "Nota de cuenta.",
        "Reseña de persona.",
        "Atención de prueba.",
        "Ruido de prueba.",
        "Resultado de prueba.",
        "26 oct.",
        "Actividad de prueba.",
    ):
        assert f"{text} [No respaldada]" in plain
    assert "Detalle nuevo. [No respaldado]" in plain
    assert "Persona de prueba (Cargo registrado) — 1 menciones" in plain
    assert "FUENTES VINCULADAS" not in plain


def test_plain_export_uses_only_emitted_valid_scoped_references():
    content = _with_sources()
    _bind(content, content, "headline", "Lectura de prueba.", [0])
    item = content["noticias"][0]
    _bind(content, item, "summary", item["summary"], [0])
    # This claimed linked binding is outside the channel's permitted scope.
    red = content["redes"]["x"]
    _bind(content, red, "note", red["note"], [0])
    plain = render_plain_text(content, "Lectura de prueba.")
    assert "Lectura de prueba. [Fuentes vinculadas: #0]" in plain
    assert "Reseña de prueba. [Fuentes vinculadas: #0]" in plain
    assert "Nota del canal. [No respaldada]" in plain
    assert "Publicación citada" in plain
    assert "https://source-one.test/nota" in plain
    assert "Publicación no utilizada" not in plain
    assert "https://unused-source.test/nota" not in plain
    assert "Resumen derivado" in plain
    assert "Extracto capturado" in plain


def test_plain_export_rechecks_changed_text_and_changed_catalogue():
    content = _with_sources()
    _bind(content, content, "headline", "Lectura de prueba.", [0])
    item = content["noticias"][0]
    _bind(content, item, "summary", item["summary"], [0])
    assert "Texto modificado. [No respaldado]" in render_plain_text(
        content, "Texto modificado."
    )
    changed = deepcopy(content)
    changed["evidence"]["sources"][0]["excerpt"] = "Otro material."
    plain = render_plain_text(changed, "Lectura de prueba.")
    assert "Lectura de prueba. [No respaldado]" in plain
    assert "Reseña de prueba. [No respaldada]" in plain
    assert "FUENTES VINCULADAS" not in plain


def test_plain_export_keeps_risk_and_typed_or_legacy_delta_as_prose():
    content = _report()
    plain = render_plain_text(content, "Lectura de prueba.")
    assert "Cambio de prueba — Detalle del cambio." in plain
    assert "Cambio heredado." in plain
    assert "{'titulo':" not in plain
    assert "Riesgos\n- Titular de prueba — Riesgo de prueba." in plain
    assert content["brief"]["riesgos"] == [{"index": 0, "razon": "Riesgo de prueba."}]


def test_plain_export_does_not_imply_derived_dates_are_referenced():
    content = _report()
    content["brief"]["fechas"] = [
        {"title": "Vencimiento de prueba", "when": "26 oct.", "estado": "próximo"}
    ]
    plain = render_plain_text(content, "Lectura de prueba.")
    assert "Vencimiento de prueba [No respaldada]" in plain
    assert "26 oct. [No respaldada]" in plain
