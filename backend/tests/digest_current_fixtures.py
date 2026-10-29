"""Explicit current-plan expectations and historical receiver fixtures.

No producer translation or acceptance bypass: historical prose is exercised
only through the existing tolerant receiver over detached synthetic content.
"""

import copy

from app.summaries.builder import build_tarjetas
from app.summaries.digest import apply_brief, apply_narrative, render_plain_text


def visibility_reading(title):
    return (
        f"Lectura política sobre «{title}»: la visibilidad de este asunto "
        "puede abrir espacio de posicionamiento; no acredita respaldo público."
    )


VERIFY_ATTENTION = (
    "Atención sugerida: contrastar el registro original antes de dar por "
    "adoptados acuerdos o compromisos."
)


def receive_legacy_content(content, payload):
    result = copy.deepcopy(content)
    assert apply_narrative(result, payload) == []
    apply_brief(result, payload)
    result["tarjetas"] = build_tarjetas(result["noticias"], content=result)
    headline = payload.get("headline", result.get("headline", ""))
    result["plain_text"] = render_plain_text(result, headline)
    return result
