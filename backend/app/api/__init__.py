"""REST API package: feature routers mounted by main under /api."""

from fastapi import APIRouter

from app.api import alerts, keywords, mentions, saved_searches, settings, stats

api_router = APIRouter()
api_router.include_router(mentions.router)
api_router.include_router(stats.router)
api_router.include_router(keywords.router)
api_router.include_router(alerts.router)
api_router.include_router(settings.router)
api_router.include_router(saved_searches.router)
