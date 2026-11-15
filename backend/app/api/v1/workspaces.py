"""Workspace endpoints (authenticated, RLS-scoped)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import IdentityDep, WorkspaceRepoDep
from app.schemas.workspace import (
    MemberListResponse,
    WorkspaceCreateRequest,
    WorkspaceMemberResponse,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
)
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", summary="List visible workspaces")
async def list_workspaces(
    identity: IdentityDep, workspaces: WorkspaceRepoDep
) -> list[WorkspaceResponse]:
    """List workspaces the caller may access (RLS enforces the scope)."""
    service = WorkspaceService(workspaces)
    rows = service.list_workspaces(identity.user_id)
    return [WorkspaceResponse.model_validate(row) for row in rows]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace",
)
async def create_workspace(
    payload: WorkspaceCreateRequest,
    identity: IdentityDep,
    workspaces: WorkspaceRepoDep,
) -> WorkspaceResponse:
    """Create a workspace owned by the caller."""
    service = WorkspaceService(workspaces)
    workspace = service.create_workspace(
        owner_id=identity.user_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
    )
    return WorkspaceResponse.model_validate(workspace)


@router.get("/{workspace_id}", summary="Get a workspace")
async def get_workspace(
    workspace_id: str,
    identity: IdentityDep,
    workspaces: WorkspaceRepoDep,
) -> WorkspaceResponse:
    """Return a workspace the caller belongs to."""
    service = WorkspaceService(workspaces)
    return WorkspaceResponse.model_validate(service.get_workspace(workspace_id, identity.user_id))


@router.patch("/{workspace_id}", summary="Update a workspace")
async def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdateRequest,
    identity: IdentityDep,
    workspaces: WorkspaceRepoDep,
) -> WorkspaceResponse:
    """Update a workspace (owner or editor)."""
    service = WorkspaceService(workspaces)
    workspace = service.update_workspace(
        workspace_id,
        identity.user_id,
        name=payload.name,
        description=payload.description,
    )
    return WorkspaceResponse.model_validate(workspace)


@router.delete(
    "/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workspace",
)
async def delete_workspace(
    workspace_id: str,
    identity: IdentityDep,
    workspaces: WorkspaceRepoDep,
) -> Response:
    """Delete a workspace (owner only)."""
    WorkspaceService(workspaces).delete_workspace(workspace_id, identity.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{workspace_id}/members", summary="List workspace members")
async def list_members(
    workspace_id: str,
    identity: IdentityDep,
    workspaces: WorkspaceRepoDep,
) -> MemberListResponse:
    """List members of a workspace the caller belongs to."""
    service = WorkspaceService(workspaces)
    members = service.list_members(workspace_id, identity.user_id)
    return MemberListResponse(
        items=[WorkspaceMemberResponse.model_validate(member) for member in members],
        total=len(members),
    )
