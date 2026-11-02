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


CONTEXTUAL_ATTENTION = "Observar si se publican nuevas propuestas vinculadas al asunto."
CONTEXTUAL_CONDITION = (
    "No se presuponen acuerdos, respaldo público ni responsabilidades no documentadas."
)


def contextual_reading(passage, source_ref=0, passage_index=0):
    """Explicit expected synthetic prose, independent of product rendering."""
    return (
        f"Premisa documental (fuente {source_ref}, pasaje {passage_index}): «{passage}». "
        "Interpretación política: El asunto documentado puede abrir un espacio de interlocución institucional. "
        "Consecuencia posible: Si hay continuidad documentada, podría ampliarse la coordinación. "
        "Pertinencia: La pertinencia depende de la relación documentada con el perfil monitoreado."
    )


def contextual_headline(passage, source_ref=0):
    return (
        contextual_reading(passage, source_ref)
        + f" Atención sugerida: {CONTEXTUAL_ATTENTION} Condición: {CONTEXTUAL_CONDITION}"
    )


def receive_legacy_content(content, payload):
    result = copy.deepcopy(content)
    assert apply_narrative(result, payload) == []
    apply_brief(result, payload)
    result["tarjetas"] = build_tarjetas(result["noticias"], content=result)
    headline = payload.get("headline", result.get("headline", ""))
    result["plain_text"] = render_plain_text(result, headline)
    return result
