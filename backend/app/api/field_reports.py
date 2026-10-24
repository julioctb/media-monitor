"""Field reports API: the review queue behind the human channel.

Creation is open to the bot layer and admins alike; state moves are
explicit endpoints. Every route is client-scoped and returns plain dicts
shaped for the admin queue (no pydantic out-models yet — the surface is
internal; formalize when the bot lands).
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import ClientIdDep, SessionDep
from app.models import queries
from app.models.field import FieldOperator, FieldReportStatus
from app.field_bot import normalize_phone


class FieldOperatorCreate(BaseModel):
    display_name: str
    phone: str
    telegram_user_id: int | None = None


class FieldOperatorUpdate(BaseModel):
    display_name: str | None = None
    phone: str | None = None

router = APIRouter(tags=["field-reports"])


class FieldReportCreate(BaseModel):
    operator_id: int | None = None
    status: str = FieldReportStatus.REVIEW
    title: str | None = None
    content: str | None = None
    place: str | None = None
    happened_at: datetime | None = None
    intake: dict | None = None


class FieldReportUpdate(BaseModel):
    operator_id: int | None = None
    title: str | None = None
    content: str | None = None
    place: str | None = None
    happened_at: datetime | None = None
    intake: dict | None = None


class FieldReportReject(BaseModel):
    note: str | None = None


def _report_out(report) -> dict:
    return {
        "id": report.id,
        "status": report.status,
        "operator_id": report.operator_id,
        "title": report.title,
        "content": report.content,
        "place": report.place,
        "happened_at": report.happened_at.isoformat() if report.happened_at else None,
        "review_note": report.review_note,
        "enrichment": report.enrichment,
        "mention_id": report.mention_id,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "published_at": report.published_at.isoformat() if report.published_at else None,
    }


def _load(session, client_id: int, report_id: int):
    report = queries.get_field_report(session, client_id, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="field report not found")
    return report


@router.post("/field-operators")
def create_field_operator(payload: FieldOperatorCreate, session: SessionDep, client_id: ClientIdDep):
    if not payload.display_name.strip() or not normalize_phone(payload.phone):
        raise HTTPException(status_code=422, detail="display_name and phone are required")
    phone = normalize_phone(payload.phone)
    clash = (
        session.query(FieldOperator)
        .filter_by(client_id=client_id)
        .all()
    )
    if any(normalize_phone(o.phone) == phone for o in clash if o.phone):
        raise HTTPException(status_code=409, detail="that phone is already registered")
    operator = FieldOperator(
        client_id=client_id,
        display_name=payload.display_name.strip(),
        phone=phone,
        telegram_user_id=payload.telegram_user_id,
        active=True,
    )
    session.add(operator)
    session.commit()
    return _operator_out(operator)


@router.patch("/field-operators/{operator_id}")
def update_field_operator(
    operator_id: int,
    payload: FieldOperatorUpdate,
    session: SessionDep,
    client_id: ClientIdDep,
):
    operator = _load_operator(session, client_id, operator_id)
    if payload.display_name is not None and payload.display_name.strip():
        operator.display_name = payload.display_name.strip()
    if payload.phone is not None and normalize_phone(payload.phone):
        operator.phone = normalize_phone(payload.phone)
    session.commit()
    return _operator_out(operator)


@router.post("/field-operators/{operator_id}/invite")
def invite_field_operator(operator_id: int, session: SessionDep, client_id: ClientIdDep):
    """Single-use invite: token stored; the link carries it as deep-link.

    The token is a REFERENCE, never the credential — the binding proof is
    always the phone match against the allowlist.
    """
    operator = _load_operator(session, client_id, operator_id)
    import secrets

    if not operator.invite_token:
        operator.invite_token = secrets.token_urlsafe(8)
        from datetime import datetime, timezone

        operator.invited_at = datetime.now(timezone.utc)
        session.commit()
    return {
        "id": operator.id,
        "token": operator.invite_token,
        "link": _invite_link(operator.invite_token),
    }


def _invite_link(token: str) -> str | None:
    """t.me deep-link; None when the bot username is not resolvable."""
    import os

    username = os.environ.get("TELEGRAM_BOT_USERNAME", "").strip()
    if username:
        return f"https://t.me/{username}?start={token}"
    token_env = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token_env:
        return None
    try:
        import httpx

        resp = httpx.get(
            f"https://api.telegram.org/bot{token_env}/getMe", timeout=5.0
        )
        data = resp.json()
        username = data["result"]["username"]
        os.environ["TELEGRAM_BOT_USERNAME"] = username  # process cache
        return f"https://t.me/{username}?start={token}"
    except Exception:  # noqa: BLE001 - the token alone still works
        return None


def _operator_out(operator: FieldOperator) -> dict:
    return {
        "id": operator.id,
        "display_name": operator.display_name,
        "telegram_user_id": operator.telegram_user_id,
        "phone": operator.phone,
        "active": operator.active,
        "invited_at": operator.invited_at.isoformat() if operator.invited_at else None,
        "accepted_at": operator.accepted_at.isoformat() if operator.accepted_at else None,
    }


@router.get("/field-operators")
def list_field_operators(session: SessionDep, client_id: ClientIdDep):
    """Operators for the /campo access panel: pending activations first."""
    rows = (
        session.query(FieldOperator)
        .filter_by(client_id=client_id)
        .order_by(FieldOperator.active, FieldOperator.id.desc())
        .all()
    )
    return {"items": [_operator_out(operator) for operator in rows]}


@router.post("/field-operators/{operator_id}/activate")
def activate_field_operator(operator_id: int, session: SessionDep, client_id: ClientIdDep):
    operator = _load_operator(session, client_id, operator_id)
    operator.active = True
    session.commit()
    return {"id": operator.id, "active": True}


@router.post("/field-operators/{operator_id}/deactivate")
def deactivate_field_operator(operator_id: int, session: SessionDep, client_id: ClientIdDep):
    operator = _load_operator(session, client_id, operator_id)
    operator.active = False
    session.commit()
    return {"id": operator.id, "active": False}


def _load_operator(session, client_id: int, operator_id: int) -> FieldOperator:
    operator = session.query(FieldOperator).filter_by(client_id=client_id, id=operator_id).first()
    if operator is None:
        raise HTTPException(status_code=404, detail="field operator not found")
    return operator


@router.post("/field-reports")
def create_field_report(payload: FieldReportCreate, session: SessionDep, client_id: ClientIdDep):
    try:
        report = queries.create_field_report(
            session,
            client_id=client_id,
            operator_id=payload.operator_id,
            status=payload.status,
            title=payload.title,
            content=payload.content,
            place=payload.place,
            happened_at=payload.happened_at,
            intake=payload.intake,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return _report_out(report)


@router.get("/field-reports")
def list_field_reports(
    session: SessionDep,
    client_id: ClientIdDep,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        reports = queries.list_field_reports(session, client_id, status=status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"items": [_report_out(r) for r in reports]}


@router.get("/field-reports/{report_id}")
def get_field_report(report_id: int, session: SessionDep, client_id: ClientIdDep):
    return _report_out(_load(session, client_id, report_id))


@router.patch("/field-reports/{report_id}")
def update_field_report(
    report_id: int,
    payload: FieldReportUpdate,
    session: SessionDep,
    client_id: ClientIdDep,
):
    report = _load(session, client_id, report_id)
    changes = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        report = queries.update_field_report(session, report, changes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return _report_out(report)


@router.post("/field-reports/{report_id}/submit")
def submit_field_report(report_id: int, session: SessionDep, client_id: ClientIdDep):
    report = _load(session, client_id, report_id)
    try:
        report = queries.submit_field_report(session, report)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return _report_out(report)


@router.post("/field-reports/{report_id}/approve")
def approve_field_report(report_id: int, session: SessionDep, client_id: ClientIdDep):
    report = _load(session, client_id, report_id)
    try:
        report = queries.publish_field_report(session, report)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if report is None:
        raise HTTPException(
            status_code=409,
            detail="a field report with the same title was already published",
        )
    session.commit()
    return _report_out(report)


@router.post("/field-reports/{report_id}/reject")
def reject_field_report(
    report_id: int,
    payload: FieldReportReject,
    session: SessionDep,
    client_id: ClientIdDep,
):
    report = _load(session, client_id, report_id)
    try:
        report = queries.reject_field_report(session, report, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return _report_out(report)
