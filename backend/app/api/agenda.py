"""Agenda CRUD: /api/clients/{client_id}/agenda-items (feature agenda-page).

Routes carry the client in the path like saved-searches: the endpoint is
explicit about the tenant it touches and validates existence before any
query. Validation lives in app.models.queries (single chokepoint), the
router only maps ValueError -> 422.
"""

from fastapi import APIRouter, HTTPException

from app.api.schemas import AgendaItemCreate, AgendaItemOut, AgendaItemPatch
from app.models import AgendaItem, Client, queries
from app.api.deps import SessionDep

router = APIRouter(prefix="/clients/{client_id}", tags=["agenda"])


def _get_client_or_404(session, client_id: int) -> Client:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")
    return client


def _get_owned_or_404(session, item_id: int, client_id: int):
    row = queries.get_agenda_item(session, item_id, client_id)
    if row is None:
        raise HTTPException(status_code=404, detail="agenda item not found")
    return row


@router.get("/agenda-items", response_model=list[AgendaItemOut])
def list_agenda_items(client_id: int, session: SessionDep) -> list[AgendaItemOut]:
    """Client agenda; dated items first, «Sin fecha completa» last."""
    _get_client_or_404(session, client_id)
    return queries.list_agenda_items(session, client_id)


@router.post("/agenda-items", response_model=AgendaItemOut, status_code=201)
def create_agenda_item(
    client_id: int, payload: AgendaItemCreate, session: SessionDep
) -> AgendaItemOut:
    _get_client_or_404(session, client_id)
    try:
        changes = queries.validated_agenda_changes(payload.model_dump(), partial=False)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = AgendaItem(client_id=client_id, **changes)
    session.add(row)
    session.commit()
    return row


@router.delete("/agenda-items/{item_id}", status_code=204)
def delete_agenda_item(
    item_id: int, client_id: int, session: SessionDep
) -> None:
    row = _get_owned_or_404(session, item_id, client_id)
    session.delete(row)
    session.commit()


@router.patch("/agenda-items/{item_id}", response_model=AgendaItemOut)
def update_agenda_item(
    item_id: int, client_id: int, payload: AgendaItemPatch, session: SessionDep
):
    row = _get_owned_or_404(session, item_id, client_id)
    sent = payload.model_dump(exclude_unset=True)
    try:
        validated = queries.validated_agenda_changes(sent, partial=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for field, value in validated.items():
        setattr(row, field, value)
    session.commit()
    return row
