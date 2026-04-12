from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from backend.cli_support.models import CliSession, CliState
from backend.cli_support.session import run_request
from backend.common.types import MCPServerConfig, MCPToolInfo
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.mcp import MCPClient, MCPServerManager, MCPToolBridge


class FakeMCPClient(MCPClient):
    def __init__(self, server_config: MCPServerConfig) -> None:
        self._server_config = server_config
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def list_tools(self) -> list[MCPToolInfo]:
        return [
            MCPToolInfo(
                name="echo",
                description="Echo",
                input_schema={"type": "object"},
                server_id=self._server_config.id,
            )
        ]


class FakeLoop:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, user_input: str) -> None:
        self.calls.append(user_input)

    def abort(self) -> None:
        return None


class RecordingBridge:
    def __init__(self) -> None:
        self.sync_calls = 0

    def needs_sync(self) -> bool:
        return True

    async def sync_if_needed(self) -> int:
        self.sync_calls += 1
        return 0


def _make_config_path() -> str:
    root = Path(__file__).resolve().parents[1] / ".tmp_mcp_versions"
    root.mkdir(exist_ok=True)
    temp_dir = root / uuid4().hex
    temp_dir.mkdir()
    path = temp_dir / "mcp_servers.json"
    path.write_text(json.dumps({"servers": []}), encoding="utf-8")
    return str(path)


def _server_config(server_id: str, enabled: bool = True) -> MCPServerConfig:
    return MCPServerConfig(
        id=server_id,
        name=server_id,
        transport="stdio",
        command="npx",
        args=["demo"],
        enabled=enabled,
    )


@pytest.mark.asyncio
async def test_server_manager_version_increments_on_state_changes() -> None:
    manager = MCPServerManager(config_path=_make_config_path(), client_factory=FakeMCPClient)
    assert manager.version == 0
    await manager.add_server(_server_config("versioned", enabled=False))
    assert manager.version == 1
    await manager.connect_server("versioned")
    assert manager.version == 2
    await manager.disconnect_server("versioned")
    assert manager.version == 3
    await manager.remove_server("versioned")
    assert manager.version == 4


@pytest.mark.asyncio
async def test_bridge_detects_version_changes_and_resyncs() -> None:
    manager = MCPServerManager(config_path=_make_config_path(), client_factory=FakeMCPClient)
    bridge = MCPToolBridge(manager, ToolRegistry())
    assert await bridge.sync_all() == 0
    assert bridge.needs_sync() is False
    await manager.add_server(_server_config("added"))
    assert bridge.needs_sync() is True
    assert await bridge.sync_if_needed() == 1
    assert bridge.needs_sync() is False


@pytest.mark.asyncio
async def test_sync_if_needed_skips_when_manager_version_is_unchanged() -> None:
    manager = MCPServerManager(config_path=_make_config_path(), client_factory=FakeMCPClient)
    bridge = MCPToolBridge(manager, ToolRegistry())
    await bridge.sync_all()

    async def fail_refresh(server_id: str) -> list[MCPToolInfo]:
        raise AssertionError(f"refresh_tools should not run: {server_id}")

    manager.refresh_tools = fail_refresh  # type: ignore[method-assign]
    assert await bridge.sync_if_needed() == -1


@pytest.mark.asyncio
async def test_sync_if_needed_removes_disconnected_server_tools() -> None:
    manager = MCPServerManager(config_path=_make_config_path(), client_factory=FakeMCPClient)
    registry = ToolRegistry()
    bridge = MCPToolBridge(manager, registry)
    await manager.add_server(_server_config("paused"))
    await bridge.sync_all()
    assert registry.has("mcp__paused__echo") is True
    await manager.disconnect_server("paused")
    assert await bridge.sync_if_needed() == 0
    assert registry.has("mcp__paused__echo") is False


@pytest.mark.asyncio
async def test_sync_if_needed_removes_deleted_server_tools() -> None:
    manager = MCPServerManager(config_path=_make_config_path(), client_factory=FakeMCPClient)
    registry = ToolRegistry()
    bridge = MCPToolBridge(manager, registry)
    await manager.add_server(_server_config("gone"))
    await bridge.sync_all()
    assert registry.has("mcp__gone__echo") is True
    await manager.remove_server("gone")
    assert await bridge.sync_if_needed() == 0
    assert registry.has("mcp__gone__echo") is False


@pytest.mark.asyncio
async def test_sync_if_needed_adds_new_server_tools() -> None:
    manager = MCPServerManager(config_path=_make_config_path(), client_factory=FakeMCPClient)
    registry = ToolRegistry()
    bridge = MCPToolBridge(manager, registry)
    await bridge.sync_all()
    await manager.add_server(_server_config("fresh"))
    assert await bridge.sync_if_needed() == 1
    assert registry.has("mcp__fresh__echo") is True


@pytest.mark.asyncio
async def test_cli_run_request_syncs_bridge_before_running_loop() -> None:
    bridge = RecordingBridge()
    loop = FakeLoop()
    session = CliSession.model_construct(
        manager=object(),
        mcp_manager=None,
        mcp_bridge=bridge,
        loop=loop,
        registry=ToolRegistry(),
        state=CliState(
            provider_id="provider",
            provider_name="Provider",
            model="model",
            workspace=".",
            permission_mode="auto",
        ),
        event_handler=None,
    )
    await run_request(session, "hello")
    assert bridge.sync_calls == 1
    assert loop.calls == ["hello"]
