from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI
import httpx
import pytest

from backend.api.routes import workspaces as workspaces_routes
from backend.config.settings import settings


@pytest.fixture
async def client(
    tmp_path: Path,
) -> AsyncGenerator[tuple[httpx.AsyncClient, Path], None]:
    original_secret = settings.auth_secret
    original_roots = settings.workspace_roots
    settings.auth_secret = "test-secret"
    root = tmp_path / "projects"
    root.mkdir()
    settings.workspace_roots = str(root)
    app = FastAPI()
    app.include_router(workspaces_routes.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client, root
    settings.auth_secret = original_secret
    settings.workspace_roots = original_roots


@pytest.mark.asyncio
async def test_workspace_roots_requires_auth(
    client: tuple[httpx.AsyncClient, Path],
) -> None:
    http_client, _ = client
    response = await http_client.get("/api/workspaces/roots")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_workspace_list_returns_real_project_directories(
    client: tuple[httpx.AsyncClient, Path],
) -> None:
    http_client, root = client
    project = root / "agent-app"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (root / "note.txt").write_text("not a directory\n", encoding="utf-8")

    response = await http_client.get(
        f"/api/workspaces/list?path={root}",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["path"] == str(root)
    assert payload["entries"] == [
        {
            "name": "agent-app",
            "path": str(project.resolve()),
            "is_directory": True,
            "is_project": True,
        }
    ]


@pytest.mark.asyncio
async def test_workspace_list_rejects_path_outside_roots(
    client: tuple[httpx.AsyncClient, Path],
) -> None:
    http_client, root = client
    outside = root.parent

    response = await http_client.get(
        f"/api/workspaces/list?path={outside}",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "WORKSPACE_PATH_FORBIDDEN"


@pytest.mark.asyncio
async def test_workspace_validate_reports_unavailable_path(
    client: tuple[httpx.AsyncClient, Path],
) -> None:
    http_client, root = client

    response = await http_client.get(
        f"/api/workspaces/validate?path={root / 'missing'}",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is False
