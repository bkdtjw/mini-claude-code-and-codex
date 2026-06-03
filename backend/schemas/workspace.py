from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspaceEntry(BaseModel):
    name: str
    path: str
    is_directory: bool = True
    is_project: bool = False


class WorkspaceRoot(WorkspaceEntry):
    pass


class WorkspaceCrumb(BaseModel):
    name: str
    path: str


class WorkspaceRootsResponse(BaseModel):
    roots: list[WorkspaceRoot] = Field(default_factory=list)


class WorkspaceListResponse(BaseModel):
    root: str
    path: str
    parent: str | None = None
    breadcrumbs: list[WorkspaceCrumb] = Field(default_factory=list)
    entries: list[WorkspaceEntry] = Field(default_factory=list)
    truncated: bool = False


class WorkspaceValidateResponse(BaseModel):
    ok: bool
    path: str = ""
    is_project: bool = False
    message: str = ""


__all__ = [
    "WorkspaceCrumb",
    "WorkspaceEntry",
    "WorkspaceListResponse",
    "WorkspaceRoot",
    "WorkspaceRootsResponse",
    "WorkspaceValidateResponse",
]
