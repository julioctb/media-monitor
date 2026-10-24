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


@lru_cache(maxsize=1)
def narrative_response_schema() -> dict:
    """JSON schema handed to the provider as ``response_format``.

    Derived from the models above so there is a single source of truth; the
    post-merge validation in ``apply_narrative`` remains the gate. The
    builder sends this on the first attempt only — providers without
    json_schema support degrade to the plain retry (see builder).
    """
    return NarrativePayload.model_json_schema()
