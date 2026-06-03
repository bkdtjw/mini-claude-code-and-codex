from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.middleware.auth import verify_token
from backend.schemas.workspace import (
    WorkspaceListResponse,
    WorkspaceRootsResponse,
    WorkspaceValidateResponse,
)
from .workspace_service import (
    is_project_dir,
    resolve_allowed_path,
    workspace_list_response,
    workspace_roots_response,
)

router = APIRouter(
    prefix="/api/workspaces",
    tags=["workspaces"],
    dependencies=[Depends(verify_token)],
)

@router.get("/roots", response_model=WorkspaceRootsResponse)
async def list_workspace_roots() -> WorkspaceRootsResponse:
    try:
        return workspace_roots_response()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"code": "WORKSPACE_ROOTS_ERROR", "message": str(exc)},
        ) from exc


@router.get("/list", response_model=WorkspaceListResponse)
async def list_workspace_directory(
    path: str | None = Query(default=None),
) -> WorkspaceListResponse:
    try:
        return workspace_list_response(path)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"code": "WORKSPACE_LIST_ERROR", "message": str(exc)},
        ) from exc


@router.get("/validate", response_model=WorkspaceValidateResponse)
async def validate_workspace(path: str = Query(...)) -> WorkspaceValidateResponse:
    try:
        target, _ = resolve_allowed_path(path)
        return WorkspaceValidateResponse(
            ok=True,
            path=str(target),
            is_project=is_project_dir(target),
            message="Workspace is available",
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return WorkspaceValidateResponse(
            ok=False,
            message=str(detail.get("message") or "Workspace is not available"),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"code": "WORKSPACE_VALIDATE_ERROR", "message": str(exc)},
        ) from exc

__all__ = ["router"]
