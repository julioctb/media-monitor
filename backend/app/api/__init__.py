"""REST API package: feature routers mounted by main under /api."""

from fastapi import APIRouter

from app.api import (
    alerts,
    ingest,
    keywords,
    mentions,
    saved_searches,
    settings,
    spikes,
    stats,
    summaries,
)

api_router = APIRouter()
api_router.include_router(mentions.router)
api_router.include_router(stats.router)
api_router.include_router(keywords.router)
api_router.include_router(alerts.router)
api_router.include_router(settings.router)
api_router.include_router(saved_searches.router)
api_router.include_router(spikes.router)
api_router.include_router(summaries.router)
api_router.include_router(ingest.router)
