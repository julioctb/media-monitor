"""FastAPI application factory."""

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.api import api_router
from app.api.deps import SessionDep
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0")

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/health", tags=["ops"])
    def api_health(session: SessionDep) -> dict[str, str]:
        """Liveness plus DB connectivity; 503 when the DB is unreachable."""
        try:
            session.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 - any DB failure degrades health
            raise HTTPException(status_code=503, detail="database unreachable")
        return {"status": "ok"}

    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
