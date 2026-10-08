"""REST API package. Feature routers (/mentions, /stats, /keywords, /alerts)
are registered on this router by the API writers."""

from fastapi import APIRouter

api_router = APIRouter()
