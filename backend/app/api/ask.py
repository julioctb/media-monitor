"""POST /api/clients/{id}/ask: natural-language Q&A over the corpus (F4).

Retrieval happens server-side and is deterministic; the configured AI
provider only narrates the retrieved context with [n] citations. Without a
provider the endpoint answers 503 — the UI shows the detail verbatim.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import SessionDep
from app.api.schemas import AskCitationOut, AskRequest, AskResponse
from app.ask import AskError, answer_question
from app.enrich.llm import LLMEnricher
from app.models import Client
from app.settings_runtime import load_cycle_settings

router = APIRouter(tags=["ask"])

ASK_TIMEOUT_S = 60.0


def _build_ask_client(session: Session, client_id: int) -> LLMEnricher | None:
    """Ask client from stored settings; None when no provider/key."""
    effective = load_cycle_settings(session, client_id=client_id)
    if effective.ai_provider != "openai" or not effective.ai_api_key:
        return None
    return LLMEnricher(
        api_key=effective.ai_api_key,
        base_url=effective.ai_base_url,
        model=effective.ai_model,
        timeout=ASK_TIMEOUT_S,
    )


@router.post("/clients/{client_id}/ask", response_model=AskResponse)
def ask(
    client_id: int,
    payload: AskRequest,
    session: SessionDep,
) -> AskResponse:
    if session.get(Client, client_id) is None:
        raise HTTPException(status_code=404, detail="client not found")

    enricher = _build_ask_client(session, client_id)
    if enricher is None:
        raise HTTPException(
            status_code=503,
            detail="No hay proveedor de IA configurado (settings): la consulta requiere uno.",
        )

    try:
        result = answer_question(
            session, client_id=client_id, question=payload.question, enricher=enricher
        )
    except AskError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    return AskResponse(
        answer=result.answer,
        citations=[AskCitationOut.model_validate(c) for c in result.citations],
        person=result.person,
        matched_mentions=result.matched_mentions,
    )
