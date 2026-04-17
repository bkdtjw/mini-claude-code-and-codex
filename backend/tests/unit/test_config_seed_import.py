from __future__ import annotations

import json

import pytest

from backend.adapters.provider_manager import ProviderManager
from backend.common.types import MCPServerConfig, ProviderConfig, ProviderType
from backend.core.s02_tools.mcp import MCPServerManager
from backend.core.s07_task_system.models import NotifyConfig, OutputConfig, ScheduledTask, TaskStoreData
from backend.core.s07_task_system.store import TaskStore
from backend.storage import MCPServerStore, ProviderStore, TaskConfigStore

from .storage_test_support import make_test_session_factory


def _provider_seed() -> dict[str, object]:
    return {
        "providers": [
            {
                "id": "provider-seed",
                "name": "Seed Provider",
                "provider_type": ProviderType.OPENAI_COMPAT.value,
                "base_url": "https://example.com",
                "api_key": "seed-key",
                "default_model": "seed-model",
                "available_models": ["seed-model"],
                "is_default": True,
                "enabled": True,
            }
        ]
    }


def _mcp_seed() -> dict[str, object]:
    return {
        "servers": [
            {
                "id": "seed-server",
                "name": "Seed Server",
                "transport": "stdio",
                "command": "npx",
                "args": ["demo"],
                "env": {},
                "enabled": False,
            }
        ]
    }


def _task_seed() -> TaskStoreData:
    return TaskStoreData(
        tasks=[
            ScheduledTask(
                id="seed-task",
                name="Seed Task",
                prompt="hello",
                notify=NotifyConfig(feishu=False),
                output=OutputConfig(save_markdown=False),
            )
        ]
    )


@pytest.mark.asyncio
async def test_provider_manager_seed_import_prefers_database_after_first_load(tmp_path) -> None:
    engine, factory = await make_test_session_factory(tmp_path, "provider_seed")
    seed_path = tmp_path / "providers.json"
    seed_path.write_text(json.dumps(_provider_seed(), ensure_ascii=False), encoding="utf-8")
    try:
        manager = ProviderManager(config_path=str(seed_path), store=ProviderStore(factory))
        providers = await manager.list_all()
        assert [item.id for item in providers] == ["provider-seed"]
        seed_path.write_text('{"providers":[]}', encoding="utf-8")
        restarted = ProviderManager(config_path=str(seed_path), store=ProviderStore(factory))
        assert [item.id for item in await restarted.list_all()] == ["provider-seed"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_mcp_server_manager_seed_import_prefers_database_after_first_load(tmp_path) -> None:
    engine, factory = await make_test_session_factory(tmp_path, "mcp_seed")
    seed_path = tmp_path / "mcp_servers.json"
    seed_path.write_text(json.dumps(_mcp_seed(), ensure_ascii=False), encoding="utf-8")
    try:
        manager = MCPServerManager(config_path=str(seed_path), store=MCPServerStore(factory))
        assert [item.id for item in await manager.list_servers()] == ["seed-server"]
        seed_path.write_text('{"servers":[]}', encoding="utf-8")
        restarted = MCPServerManager(config_path=str(seed_path), store=MCPServerStore(factory))
        assert [item.id for item in await restarted.list_servers()] == ["seed-server"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_store_seed_import_prefers_database_after_first_load(tmp_path) -> None:
    engine, factory = await make_test_session_factory(tmp_path, "task_seed")
    seed_path = tmp_path / "tasks.json"
    seed_path.write_text(_task_seed().model_dump_json(indent=2), encoding="utf-8")
    try:
        store = TaskStore(path=str(seed_path), store=TaskConfigStore(factory))
        assert [item.id for item in await store.list_tasks()] == ["seed-task"]
        seed_path.write_text('{"tasks":[]}', encoding="utf-8")
        restarted = TaskStore(path=str(seed_path), store=TaskConfigStore(factory))
        assert [item.id for item in await restarted.list_tasks()] == ["seed-task"]
    finally:
        await engine.dispose()
