"""Presentation-only export changes preserve stored report semantics."""

from copy import deepcopy

import pytest

from app.models import MentionSource
from app.summaries.comparison import freeze_comparison
from app.summaries.digest import render_plain_text
from app.summaries.evidence import catalogue_fingerprint
from tests.test_digest_comparison_provenance import two_cut_content  # noqa: F401 -- registers fixture
from tests.test_digest_plain_provenance import _bind, _with_sources

SOURCE_LABELS = {
    "news_rss": "Noticias RSS",
    "gdelt": "GDELT",
    "x_twitter": "X (Twitter)",
    "facebook_page": "Facebook",
    "rss_custom": "RSS personalizado",
    "scraper": "Extracción web",
    "field_report": "Reporte de campo",
    "telegram_web": "Telegram",
    "instagram_web": "Instagram",
    "x": "X (Twitter)",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "telegram": "Telegram",
    "canal_local": "Canal Local",
    "https://brand.test/news_rss": "https://brand.test/news_rss",
    "": "Fuente no identificada",
    None: "Fuente no identificada",
}


@pytest.mark.parametrize("source,label", SOURCE_LABELS.items())
def test_source_labels_change_only_the_display_edge(source, label):
    content = _with_sources()
    assert {kind.value for kind in MentionSource} <= SOURCE_LABELS.keys()
    item = content["noticias"][0]
    item["sources"] = [{"source": source}, {"source": "news_rss"}, {"source": source}]
    content["redes"] = {
        source: {"count": 0, "note": "Nota conservada."},
        "canal_auxiliar": 2,
    }
    original = deepcopy(content)

    plain = render_plain_text(content, "Lectura conservada.")

    assert f"  Fuentes: {label}, Noticias RSS, {label}\n" in plain
    assert (
        f"REDES\n- {label}: 0 — Nota conservada. [No respaldada]\n- Canal Auxiliar: 2"
        in plain
    )
    assert content == original


@pytest.mark.parametrize(
    "metadata",
    [
        "unavailable",
        None,
        [],
        {},
        True,
        "invalid",
        {"available": True},
        {"version": 99, "available": True},
        {"version": 1, "available": "true"},
        "available",
        "legacy",
    ],
)
def test_delta_heading_requires_valid_available_comparison(two_cut_content, metadata):  # noqa: F811 -- pytest fixture injection
    content = two_cut_content
    content["brief"] = {
        "delta": [
            {"titulo": "Asunto retenido", "giro": "Etiqueta de tono heredada."},
            "Cambio heredado sin cita.",
        ]
    }
    if metadata == "legacy":
        content.pop("comparison")
    elif metadata == "unavailable":
        content["comparison"] = freeze_comparison(
            None, content["noticias"], lambda note: note["title"]
        )
    elif metadata != "available":
        content["comparison"] = metadata
    original = deepcopy(content)

    plain = render_plain_text(content, "Lectura conservada.")

    heading = (
        "Qué cambió" if metadata in ("available", "legacy") else "Novedades del corte"
    )
    assert f"BRIEF\n{heading}\n" in plain
    assert "- Asunto retenido — Etiqueta de tono heredada. [No respaldada]" in plain
    assert "- Cambio heredado sin cita. [No respaldada]" in plain
    assert content == original


def test_display_labels_preserve_raw_channel_scope_and_archival_material():
    content = _with_sources()
    source = content["evidence"]["sources"][1]
    source["summary"] = "news_rss: Atención sugerida: conservar el original."
    source["excerpt"] = "«Acción sugerida: revisar telegram_web e instagram_web»."
    content["evidence"]["catalogue_fingerprint"] = catalogue_fingerprint(
        content["evidence"]
    )
    channel = content["redes"]["x"]
    _bind(content, channel, "note", channel["note"], [1])
    original = deepcopy(content)

    plain = render_plain_text(content, "Lectura con news_rss sin traducción editorial.")

    assert "Lectura con news_rss sin traducción editorial. [No respaldado]" in plain
    assert "- X (Twitter): 1 — Nota del canal. [Fuentes vinculadas: #1]" in plain
    assert f"Resumen derivado almacenado: {source['summary']}" in plain
    assert f"Extracto capturado: {source['excerpt']}" in plain
    assert source["url"] in plain
    assert content == original


@pytest.mark.parametrize("empty", [None, ""])
def test_empty_export_keeps_zero_channels_without_empty_action_or_delta(empty):
    content = {
        "noticias": [],
        "redes": {"x": 0},
        "brief": {
            "delta": [],
            "decisiones": [{"index": 0, "accion_sugerida": empty}],
        },
        "comparison": {"available": False},
    }
    original = deepcopy(content)

    plain = render_plain_text(content, "")

    assert "NOTICIAS\n\nREDES\n- X (Twitter): 0" in plain
    assert "Acción sugerida:" not in plain
    assert "Qué cambió" not in plain
    assert "Novedades del corte" not in plain
    assert content == original
