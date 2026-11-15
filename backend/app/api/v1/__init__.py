"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1 import health, indexing, ingestion, knowledge, me, workspaces

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(me.router)
api_router.include_router(workspaces.router)
api_router.include_router(knowledge.router)
api_router.include_router(ingestion.router)
api_router.include_router(indexing.router)

__all__ = ["api_router"]
