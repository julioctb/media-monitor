"""Saved-search CRUD: /api/clients/{client_id}/saved-searches (T1).

Routes carry the client in the path (per the feature doc) instead of the
Client dependency: the endpoint is explicit about the tenant it touches
and still validates that the client exists before any query.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from fastapi import APIRouter, HTTPException

from app.api.schemas import SavedSearchCreate, SavedSearchOut, SavedSearchPatch
from app.models import Client, SavedSearch, queries
from app.api.deps import SessionDep

router = APIRouter(prefix="/clients/{client_id}", tags=["saved-searches"])


def _get_client_or_404(session, client_id: int) -> Client:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")
    return client


def _get_owned_or_404(
    session, saved_search_id: int, client_id: int
) -> SavedSearch:
    row = queries.get_saved_search(session, saved_search_id, client_id)
    if row is None:
        raise HTTPException(status_code=404, detail="saved search not found")
    return row


def _ensure_unique_name(
    session, client_id: int, name: str, exclude_id: int | None = None
) -> None:
    stmt = select(SavedSearch).where(
        SavedSearch.client_id == client_id, SavedSearch.name == name
    )
    if exclude_id is not None:
        stmt = stmt.where(SavedSearch.id != exclude_id)
    if session.scalar(stmt) is not None:
        raise HTTPException(status_code=409, detail=f"saved search {name!r} already exists")


@router.get("/saved-searches", response_model=list[SavedSearchOut])
def list_saved_searches(client_id: int, session: SessionDep) -> list[SavedSearchOut]:
    """All saved searches for the client, inactive included."""
    _get_client_or_404(session, client_id)
    return queries.list_saved_searches(session, client_id)


@router.get("/saved-searches/{saved_search_id}", response_model=SavedSearchOut)
def get_saved_search(
    saved_search_id: int, client_id: int, session: SessionDep
) -> SavedSearchOut:
    """One saved search, scoped to the client (404 across tenants)."""
    return _get_owned_or_404(session, saved_search_id, client_id)


@router.post("/saved-searches", response_model=SavedSearchOut, status_code=201)
def create_saved_search(
    client_id: int, payload: SavedSearchCreate, session: SessionDep
) -> SavedSearchOut:
    _get_client_or_404(session, client_id)
    try:
        changes = queries.validated_saved_search_changes(
            payload.model_dump(), partial=False
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _ensure_unique_name(session, client_id, changes["name"])
    row = SavedSearch(client_id=client_id, **changes)
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="saved search already exists")
    return row


@router.patch("/saved-searches/{saved_search_id}", response_model=SavedSearchOut)
def update_saved_search(
    saved_search_id: int,
    payload: SavedSearchPatch,
    client_id: int,
    session: SessionDep,
) -> SavedSearchOut:
    row = _get_owned_or_404(session, saved_search_id, client_id)
    sent = dict(payload.model_dump(exclude_unset=True))
    try:
        validated = queries.validated_saved_search_changes(sent, partial=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if "name" in validated:
        _ensure_unique_name(session, client_id, validated["name"], exclude_id=row.id)
    for field, value in validated.items():
        setattr(row, field, value)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="saved search already exists")
    return row


@router.delete("/saved-searches/{saved_search_id}", status_code=204)
def delete_saved_search(
    saved_search_id: int, client_id: int, session: SessionDep
) -> None:
    row = _get_owned_or_404(session, saved_search_id, client_id)
    session.delete(row)
    session.commit()
