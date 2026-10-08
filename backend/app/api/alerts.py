"""Alert settings: GET/PUT /api/alert/settings."""

from fastapi import APIRouter

from app.api.deps import ClientIdDep, SessionDep
from app.api.schemas import AlertSettingsOut, AlertSettingsUpdate
from app.models import AlertChannel, AlertDigest, AlertSettings, queries

router = APIRouter(tags=["alerts"])


@router.get("/alerts/settings", response_model=AlertSettingsOut)
def get_alert_settings(
    session: SessionDep, client_id: ClientIdDep
) -> AlertSettingsOut:
    """Current configuration; inactive defaults when never configured."""
    row = queries.get_alert_settings(session, client_id)
    if row is None:
        return AlertSettingsOut(
            digest=AlertDigest.instant, recipient_email=None, is_active=False
        )
    return row


@router.put("/alerts/settings", response_model=AlertSettingsOut)
def upsert_alert_settings(
    payload: AlertSettingsUpdate, session: SessionDep, client_id: ClientIdDep
) -> AlertSettingsOut:
    """Full-state upsert: creates the row on first PUT, updates it after."""
    row = queries.get_alert_settings(session, client_id)
    if row is None:
        row = AlertSettings(client_id=client_id, channel=AlertChannel.email)
    row.digest = payload.digest
    row.recipient_email = str(payload.recipient_email)
    row.is_active = payload.is_active
    session.add(row)  # no-op for an existing row, required for the insert path
    session.commit()
    return row
