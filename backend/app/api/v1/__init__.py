"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1 import health, me, workspaces

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(me.router)
api_router.include_router(workspaces.router)

__all__ = ["api_router"]
