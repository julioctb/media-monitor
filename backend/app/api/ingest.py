"""Ingest observability API: the per-adapter run ledger (T3).

GET /clients/{id}/ingest/runs surfaces the latest cycles per adapter so a
gap ("fuente caída") is visible in the dashboard, not just in logs.
"""

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.api.schemas import IngestRunOut
from app.models import Client, queries

router = APIRouter(prefix="/clients/{client_id}", tags=["ingest"])


@router.get("/ingest/runs", response_model=list[IngestRunOut])
def list_ingest_runs(
    client_id: int,
    session: SessionDep,
    limit: int = 100,
    adapter: str | None = None,
    status: str | None = None,
) -> list[IngestRunOut]:
    """Most recent ingest ledger rows, newest cycle first."""
    if session.get(Client, client_id) is None:
        raise HTTPException(status_code=404, detail="client not found")
    limit = max(1, min(500, limit))
    rows = queries.list_ingest_runs(
        session,
        client_id=client_id,
        adapter=adapter,
        status=status,
        limit=limit,
    )
    return [IngestRunOut.model_validate(row) for row in rows]
