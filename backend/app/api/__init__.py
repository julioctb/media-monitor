"""REST API package: feature routers mounted by main under /api."""

from fastapi import APIRouter

from app.api import alerts, keywords, mentions, stats

api_router = APIRouter()
api_router.include_router(mentions.router)
api_router.include_router(stats.router)
api_router.include_router(keywords.router)
api_router.include_router(alerts.router)
