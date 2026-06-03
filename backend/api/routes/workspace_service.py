from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException

from backend.config.settings import settings
from backend.schemas.workspace import (
    WorkspaceCrumb,
    WorkspaceEntry,
    WorkspaceListResponse,
    WorkspaceRoot,
    WorkspaceRootsResponse,
)

PROJECT_MARKERS = {
    ".git",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "requirements.txt",
}
SENSITIVE_ROOTS = {
    Path("/"),
    Path("/boot"),
    Path("/dev"),
    Path("/etc"),
    Path("/proc"),
    Path("/root"),
    Path("/run"),
    Path("/sys"),
}
MAX_ENTRIES = 300


def workspace_roots_response() -> WorkspaceRootsResponse:
    roots = _allowed_roots()
    return WorkspaceRootsResponse(roots=[_root_entry(path) for path in roots])


def workspace_list_response(path: str | None) -> WorkspaceListResponse:
    target, root = resolve_allowed_path(path)
    entries, truncated = _list_directories(target)
    return WorkspaceListResponse(
        root=str(root),
        path=str(target),
        parent=_parent_path(target, root),
        breadcrumbs=_breadcrumbs(target, root),
        entries=entries,
        truncated=truncated,
    )


def resolve_allowed_path(raw_path: str | None) -> tuple[Path, Path]:
    roots = _allowed_roots()
    if not roots:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "WORKSPACE_ROOTS_EMPTY",
                "message": "No workspace roots are configured",
            },
        )
    target = Path(raw_path).expanduser().resolve() if raw_path else roots[0]
    if not target.exists() or not target.is_dir():
        raise HTTPException(
            status_code=404,
            detail={"code": "WORKSPACE_NOT_FOUND", "message": f"Directory not found: {target}"},
        )
    for root in roots:
        if _is_under_root(target, root):
            return target, root
    raise HTTPException(
        status_code=403,
        detail={
            "code": "WORKSPACE_PATH_FORBIDDEN",
            "message": "Path is outside configured workspace roots",
        },
    )


def is_project_dir(path: Path) -> bool:
    return any((path / marker).exists() for marker in PROJECT_MARKERS)


def _allowed_roots() -> list[Path]:
    raw = settings.workspace_roots.strip()
    candidates = [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]
    if not candidates:
        candidates = [os.getcwd()]
    roots: list[Path] = []
    for candidate in candidates:
        path = Path(candidate).expanduser().resolve()
        if not path.exists() or not path.is_dir() or _is_sensitive_root(path):
            continue
        if path not in roots:
            roots.append(path)
    return roots


def _list_directories(path: Path) -> tuple[list[WorkspaceEntry], bool]:
    entries: list[WorkspaceEntry] = []
    children = sorted(path.iterdir(), key=lambda item: item.name.lower())
    for child in children:
        if len(entries) >= MAX_ENTRIES:
            return entries, True
        try:
            if not child.is_dir():
                continue
            entries.append(
                WorkspaceEntry(
                    name=child.name,
                    path=str(child.resolve()),
                    is_project=is_project_dir(child),
                )
            )
        except OSError:
            continue
    return entries, False


def _root_entry(path: Path) -> WorkspaceRoot:
    return WorkspaceRoot(
        name=_display_name(path),
        path=str(path),
        is_project=is_project_dir(path),
    )


def _breadcrumbs(target: Path, root: Path) -> list[WorkspaceCrumb]:
    crumbs = [WorkspaceCrumb(name=_display_name(root), path=str(root))]
    relative_parts = target.relative_to(root).parts
    current = root
    for part in relative_parts:
        current = current / part
        crumbs.append(WorkspaceCrumb(name=part, path=str(current)))
    return crumbs


def _parent_path(target: Path, root: Path) -> str | None:
    if target == root:
        return None
    parent = target.parent.resolve()
    return str(parent) if _is_under_root(parent, root) else None


def _is_sensitive_root(path: Path) -> bool:
    return path in SENSITIVE_ROOTS


def _is_under_root(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _display_name(path: Path) -> str:
    return path.name or str(path)


__all__ = [
    "is_project_dir",
    "resolve_allowed_path",
    "workspace_list_response",
    "workspace_roots_response",
]
