from __future__ import annotations

from datetime import datetime

import pytest

from backend.common.errors import AgentError
from backend.common.types import MCPServerConfig, ProviderConfig, ProviderType
from backend.core.s07_task_system.models import NotifyConfig, OutputConfig, ScheduledTask
from backend.storage import MCPServerStore, ProviderStore, TaskConfigStore

from .storage_test_support import make_test_session_factory


@pytest.fixture
async def session_factory(tmp_path):
    engine, factory = await make_test_session_factory(tmp_path, "config_store")
    try:
        yield factory
    finally:
        await engine.dispose()


def _provider(provider_id: str = "provider-1", is_default: bool = False) -> ProviderConfig:
    return ProviderConfig(
        id=provider_id,
        name=f"Provider {provider_id}",
        provider_type=ProviderType.OPENAI_COMPAT,
        base_url="https://example.com",
        api_key="secret",
        default_model="model-a",
        available_models=["model-a", "model-b"],
        extra_headers={"X-Test": "1"},
        is_default=is_default,
    )


def _server(server_id: str = "server-1") -> MCPServerConfig:
    return MCPServerConfig(
        id=server_id,
        name=f"Server {server_id}",
        transport="stdio",
        command="npx",
        args=["demo"],
        env={"TOKEN": "secret"},
        enabled=True,
    )


def _task(task_id: str = "task-1") -> ScheduledTask:
    return ScheduledTask(
        id=task_id,
        name=f"Task {task_id}",
        cron="0 7 * * *",
        prompt="hello",
        notify=NotifyConfig(feishu=False),
        output=OutputConfig(save_markdown=True, output_dir="reports"),
        created_at=datetime(2026, 1, 1, 7, 0, 0),
    )


@pytest.mark.asyncio
async def test_provider_store_add_and_list(session_factory) -> None:
    store = ProviderStore(session_factory)
    await store.add(_provider())
    assert [item.id for item in await store.list_all()] == ["provider-1"]


@pytest.mark.asyncio
async def test_provider_store_add_duplicate_raises(session_factory) -> None:
    store = ProviderStore(session_factory)
    await store.add(_provider())
    with pytest.raises(AgentError, match="PROVIDER_EXISTS"):
        await store.add(_provider())


@pytest.mark.asyncio
async def test_provider_store_update(session_factory) -> None:
    store = ProviderStore(session_factory)
    await store.add(_provider())
    updated = await store.update("provider-1", name="Updated", enabled=False)
    assert updated is not None
    assert updated.name == "Updated"
    assert updated.enabled is False


@pytest.mark.asyncio
async def test_provider_store_remove(session_factory) -> None:
    store = ProviderStore(session_factory)
    await store.add(_provider())
    assert await store.remove("provider-1") is True
    assert await store.get("provider-1") is None


@pytest.mark.asyncio
async def test_provider_store_set_default(session_factory) -> None:
    store = ProviderStore(session_factory)
    await store.add(_provider("provider-1", is_default=True))
    await store.add(_provider("provider-2"))
    await store.set_default("provider-2")
    providers = {item.id: item for item in await store.list_all()}
    assert providers["provider-1"].is_default is False
    assert providers["provider-2"].is_default is True


@pytest.mark.asyncio
async def test_provider_store_import_from_json(session_factory) -> None:
    store = ProviderStore(session_factory)
    count = await store.import_from_json([_provider("provider-1"), _provider("provider-2", is_default=True)])
    assert count == 2
    assert len(await store.list_all()) == 2


@pytest.mark.asyncio
async def test_mcp_server_store_add_and_list(session_factory) -> None:
    store = MCPServerStore(session_factory)
    await store.add(_server())
    assert [item.id for item in await store.list_all()] == ["server-1"]


@pytest.mark.asyncio
async def test_mcp_server_store_get(session_factory) -> None:
    store = MCPServerStore(session_factory)
    await store.add(_server())
    loaded = await store.get("server-1")
    assert loaded is not None
    assert loaded.args == ["demo"]


@pytest.mark.asyncio
async def test_mcp_server_store_add_duplicate_raises(session_factory) -> None:
    store = MCPServerStore(session_factory)
    await store.add(_server())
    with pytest.raises(AgentError, match="MCP_SERVER_EXISTS"):
        await store.add(_server())


@pytest.mark.asyncio
async def test_mcp_server_store_remove(session_factory) -> None:
    store = MCPServerStore(session_factory)
    await store.add(_server())
    assert await store.remove("server-1") is True
    assert await store.get("server-1") is None


@pytest.mark.asyncio
async def test_mcp_server_store_import_from_json(session_factory) -> None:
    store = MCPServerStore(session_factory)
    assert await store.import_from_json([_server("server-1"), _server("server-2")]) == 2
    assert len(await store.list_all()) == 2


@pytest.mark.asyncio
async def test_task_config_store_add_and_list(session_factory) -> None:
    store = TaskConfigStore(session_factory)
    await store.add_task(_task())
    assert [item.id for item in await store.list_tasks()] == ["task-1"]


@pytest.mark.asyncio
async def test_task_config_store_get(session_factory) -> None:
    store = TaskConfigStore(session_factory)
    await store.add_task(_task())
    loaded = await store.get_task("task-1")
    assert loaded is not None
    assert loaded.output.output_dir == "reports"


@pytest.mark.asyncio
async def test_task_config_store_update(session_factory) -> None:
    store = TaskConfigStore(session_factory)
    await store.add_task(_task())
    updated = await store.update_task("task-1", name="Renamed", enabled=False)
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.enabled is False


@pytest.mark.asyncio
async def test_task_config_store_remove(session_factory) -> None:
    store = TaskConfigStore(session_factory)
    await store.add_task(_task())
    assert await store.remove_task("task-1") is True
    assert await store.get_task("task-1") is None


@pytest.mark.asyncio
async def test_task_config_store_update_run_status(session_factory) -> None:
    store = TaskConfigStore(session_factory)
    await store.add_task(_task())
    await store.update_run_status("task-1", "success", "done")
    loaded = await store.get_task("task-1")
    assert loaded is not None
    assert loaded.last_run_status == "success"
    assert loaded.last_run_output == "done"
    assert loaded.last_run_at is not None


@pytest.mark.asyncio
async def test_task_config_store_import_from_json(session_factory) -> None:
    store = TaskConfigStore(session_factory)
    assert await store.import_from_json([_task("task-1"), _task("task-2")]) == 2
    assert len(await store.list_tasks()) == 2
