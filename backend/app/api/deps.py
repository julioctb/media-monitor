"""Shared FastAPI dependencies: DB session and tenant scope."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db

SessionDep = Annotated[Session, Depends(get_db)]


def get_client_id() -> int:
    """Client scope for every endpoint.

    MVP is single-tenant: all rows belong to the client configured via
    DEFAULT_CLIENT_ID (seeded as id=1 by the initial migration). The
    data model stays multi-tenant; this dependency is the single place
    to change when tenant selection arrives (e.g. from an auth token).
    """
    return settings.default_client_id


ClientIdDep = Annotated[int, Depends(get_client_id)]
