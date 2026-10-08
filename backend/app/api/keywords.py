"""Keywords CRUD: /api/keywords (client-scoped)."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fastapi import APIRouter, HTTPException

from app.api.deps import ClientIdDep, SessionDep
from app.api.schemas import KeywordCreate, KeywordOut, KeywordUpdate
from app.models import Keyword, queries
from sqlalchemy import select

router = APIRouter(tags=["keywords"])


def _get_owned_keyword(session: Session, keyword_id: int, client_id: int) -> Keyword:
    keyword = session.scalar(
        select(Keyword).where(Keyword.id == keyword_id, Keyword.client_id == client_id)
    )
    if keyword is None:
        raise HTTPException(status_code=404, detail="keyword not found")
    return keyword


def _ensure_unique_text(
    session: Session, client_id: int, text: str, exclude_id: int | None = None
) -> None:
    stmt = select(Keyword).where(Keyword.client_id == client_id, Keyword.text == text)
    if exclude_id is not None:
        stmt = stmt.where(Keyword.id != exclude_id)
    if session.scalar(stmt) is not None:
        raise HTTPException(status_code=409, detail=f"keyword {text!r} already exists")


@router.get("/keywords", response_model=list[KeywordOut])
def list_keywords(session: SessionDep, client_id: ClientIdDep) -> list[KeywordOut]:
    """All keywords for the client; inactive included so the UI can re-enable."""
    return queries.list_keywords(session, client_id, active_only=False)


@router.post("/keywords", response_model=KeywordOut, status_code=201)
def create_keyword(
    session: SessionDep, client_id: ClientIdDep, payload: KeywordCreate
) -> KeywordOut:
    _ensure_unique_text(session, client_id, payload.text)
    keyword = Keyword(
        client_id=client_id, text=payload.text, language=payload.language
    )
    session.add(keyword)
    try:
        session.commit()
    except IntegrityError:
        # Lost a race against the unique constraint.
        session.rollback()
        raise HTTPException(status_code=409, detail="keyword already exists")
    return keyword


@router.patch("/keywords/{keyword_id}", response_model=KeywordOut)
def update_keyword(
    keyword_id: int,
    payload: KeywordUpdate,
    session: SessionDep,
    client_id: ClientIdDep,
) -> KeywordOut:
    keyword = _get_owned_keyword(session, keyword_id, client_id)
    # Partial update: ignore absent fields and explicit nulls.
    changes = {
        key: value
        for key, value in payload.model_dump(exclude_unset=True).items()
        if value is not None
    }
    if "text" in changes:
        _ensure_unique_text(session, client_id, changes["text"], exclude_id=keyword.id)
    for field in ("text", "language", "is_active"):
        if field in changes:
            setattr(keyword, field, changes[field])
    session.commit()
    return keyword


@router.delete("/keywords/{keyword_id}", status_code=204)
def delete_keyword(
    keyword_id: int, session: SessionDep, client_id: ClientIdDep
) -> None:
    keyword = _get_owned_keyword(session, keyword_id, client_id)
    referenced = queries.count_mentions(session, client_id, keyword_id=keyword_id)
    if referenced:
        raise HTTPException(
            status_code=409,
            detail=(
                f"keyword referenced by {referenced} mention(s); "
                "reassign or delete them first"
            ),
        )
    session.delete(keyword)
    session.commit()
