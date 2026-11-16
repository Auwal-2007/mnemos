"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1 import (
    agents,
    conversations,
    health,
    indexing,
    ingestion,
    knowledge,
    me,
    memory,
    retrieval,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(agents.router)
api_router.include_router(me.router)
api_router.include_router(workspaces.router)
api_router.include_router(knowledge.router)
api_router.include_router(ingestion.router)
api_router.include_router(indexing.router)
api_router.include_router(retrieval.router)
api_router.include_router(conversations.router)
api_router.include_router(memory.router)

__all__ = ["api_router"]
