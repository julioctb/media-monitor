"""The LLM narrative contract for the daily digest.

Single source of truth for the shape ``apply_narrative`` accepts (see
``docs/contrato-narrativa-del-digest.md``). The builder reuses these models
as the ``response_format`` json schema, so generation is guided toward the
same shape the merge validates.

Strict mode on purpose: the legacy merge drops mistyped values (an ``index``
sent as ``"2"`` is skipped, not coerced) and the models must preserve that
contract, not silently widen it. Extra keys are ignored so the model can
bling without breaking the merge.
"""

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class NarrativeItem(_Strict):
    """Prose for one seeded ``noticias[index]`` row."""

    index: int
    summary: str | None = None
    why_it_matters: str | None = None
    confidence_note: str | None = None


class ActivityEntry(_Strict):
    """Rectora activity line; ``text`` is the only required field."""

    text: str
    when: str | None = None
    status: str | None = None
    channel: str | None = None


class RectoraSection(_Strict):
    tone: str | None = None
    watch: str | None = None
    activity: list[ActivityEntry] | None = None


class AgendaEntry(_Strict):
    """Agenda guess from the day's facts; ``when`` + ``title`` required."""

    when: str
    title: str
    status: str | None = None
    source: str | None = None


class CuentaEntry(_Strict):
    cuenta: str
    nota: str | None = None


class RedesSourceNote(_Strict):
    note: str | None = None
    cuentas: list[CuentaEntry] | None = None


# --------------------------------------------------------- digest-brief-v3 --
# The brief esqueleto is CODE-BUILT (builder.py): fixed sections, references
# by index into ``tarjetas``/``noticias``. The LLM only picks (seleccion) and
# writes prose; it never invents structure. ``categoria`` is a closed set so
# the guided schema carries an enum and the merge can bucket by name.

BriefCategoria = Literal["decision", "ruido", "a_favor"]

#: The three brief buckets, in render order.
BRIEF_CATEGORIES = ("decision", "ruido", "a_favor")

#: content keys carrying the esqueleto's fixed section names, for the
#: shape validator below and the builder that fills them.
BRIEF_SECTIONS = ("delta", "decisiones", "ruido", "a_favor", "fechas")


class SeleccionEntry(_Strict):
    """One brief pick: the tarjeta index it references, never new data."""

    index: int
    categoria: BriefCategoria
    razon: str | None = None


class NarrativePayload(BaseModel):
    """Top-level envelope for guided generation (``response_format``).

    Nothing is required: the merge in ``apply_narrative`` tolerates missing
    sections. Entry models keep their required keys so guided output lands
    merge-ready. Generation-only — never used to validate the stored row.
    """

    model_config = ConfigDict(strict=True, extra="allow")

    headline: str | None = None
    items: list[NarrativeItem] = []
    rectora: RectoraSection | None = None
    agenda: list[AgendaEntry] = []
    redes: dict[str, str | RedesSourceNote] = {}
    seleccion: list[SeleccionEntry] = []


def brief_shape_errors(content: object) -> list[str]:
    """Tolerant shape check for the v3 keys (``brief``/``tarjetas``/``campo``).

    Absent keys are legacy v2 rows: no errors, the render degrades. Present
    but malformed sections ARE errors — the builder owns their shape, so a
    malformed stored brief means the build path regressed.
    """
    if not isinstance(content, dict):
        return []
    errors: list[str] = []
    tarjetas_len = None
    if isinstance(content.get("noticias"), list):
        tarjetas_len = len(content["noticias"])

    brief = content.get("brief")
    if "brief" in content and not isinstance(brief, dict):
        errors.append("brief must be an object")
        brief = None
    if isinstance(brief, dict):
        for section in BRIEF_SECTIONS:
            if section in brief and not isinstance(brief[section], list):
                errors.append(f"brief.{section} must be a list")
        for section in ("decisiones", "ruido", "a_favor"):
            entries = brief.get(section)
            if not isinstance(entries, list):
                continue
            for pos, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    errors.append(f"brief.{section}[{pos}] must be an object")
                    continue
                index = entry.get("index")
                if not isinstance(index, int) or isinstance(index, bool):
                    errors.append(f"brief.{section}[{pos}].index must be an int")
                elif tarjetas_len is not None and not 0 <= index < tarjetas_len:
                    errors.append(
                        f"brief.{section}[{pos}].index {index} out of range"
                    )

    if "tarjetas" in content and not isinstance(content["tarjetas"], list):
        errors.append("tarjetas must be a list")
    elif isinstance(content.get("tarjetas"), list):
        for pos, tarjeta in enumerate(content["tarjetas"]):
            if not isinstance(tarjeta, dict):
                errors.append(f"tarjetas[{pos}] must be an object")

    if "campo" in content and not isinstance(content["campo"], list):
        errors.append("campo must be a list")
    return errors


@lru_cache(maxsize=1)
def narrative_response_schema() -> dict:
    """JSON schema handed to the provider as ``response_format``.

    Derived from the models above so there is a single source of truth; the
    post-merge validation in ``apply_narrative`` remains the gate. The
    builder sends this on the first attempt only — providers without
    json_schema support degrade to the plain retry (see builder).
    """
    return NarrativePayload.model_json_schema()
