from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest

from backend.common.errors import AgentError
from backend.common.types import MCPServerConfig, MCPToolInfo
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.mcp import MCPClient, MCPServerManager, MCPToolBridge


class ConnectCountingClient(MCPClient):
    def __init__(self, server_config: MCPServerConfig) -> None:
        super().__init__(server_config)
        self.open_calls = 0
        self.initialize_calls = 0

    async def _open_transport(self, stack: object) -> tuple[object, object, object]:
        self.open_calls += 1
        await asyncio.sleep(0.01)
        owner = self

        class Session:
            def __init__(self, read_stream: object, write_stream: object) -> None:
                self._read_stream = read_stream
                self._write_stream = write_stream

            async def __aenter__(self) -> "Session":
                return self

            async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
                return None

            async def initialize(self) -> None:
                owner.initialize_calls += 1
                await asyncio.sleep(0.01)

        return Session, object(), object()


class SlowFakeMCPClient(MCPClient):
    def __init__(self, server_config: MCPServerConfig) -> None:
        self._server_config = server_config
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        await asyncio.sleep(0.01)
        self._connected = True

    async def disconnect(self) -> None:
        await asyncio.sleep(0.01)
        self._connected = False

    async def list_tools(self) -> list[MCPToolInfo]:
        await asyncio.sleep(0.01)
        return [
            MCPToolInfo(
                name="echo",
                description=f"Echo from {self._server_config.id}",
                input_schema={"type": "object"},
                server_id=self._server_config.id,
            )
        ]


def _make_config_path() -> str:
    root = Path(__file__).resolve().parents[1] / ".tmp_mcp_concurrency"
    root.mkdir(exist_ok=True)
    temp_dir = root / uuid4().hex
    temp_dir.mkdir()
    path = temp_dir / "mcp_servers.json"
    path.write_text(json.dumps({"servers": []}), encoding="utf-8")
    return str(path)


def _server_config(server_id: str, enabled: bool = True) -> MCPServerConfig:
    return MCPServerConfig(
        id=server_id,
        name=f"Server {server_id}",
        transport="stdio",
        command="npx",
        args=["demo"],
        enabled=enabled,
    )


@pytest.mark.asyncio
async def test_mcp_client_connect_is_idempotent_under_concurrency() -> None:
    client = ConnectCountingClient(_server_config("client-lock"))
    await asyncio.gather(*(client.connect() for _ in range(10)))
    assert client.open_calls == 1
    assert client.initialize_calls == 1
    assert client.is_connected is True
    await client.disconnect()


@pytest.mark.asyncio
async def test_server_manager_serializes_duplicate_add_server_calls() -> None:
    manager = MCPServerManager(config_path=_make_config_path(), client_factory=SlowFakeMCPClient)
    config = _server_config("shared-server", enabled=False)

    async def attempt_add() -> str:
        try:
            return await manager.add_server(config)
        except AgentError as exc:
            return exc.code

    results = await asyncio.gather(*(attempt_add() for _ in range(5)))
    payload = json.loads(Path(manager._config_path).read_text(encoding="utf-8"))
    assert results.count("shared-server") == 1
    assert results.count("MCP_SERVER_EXISTS") == 4
    assert len(await manager.list_servers()) == 1
    assert len(payload["servers"]) == 1


@pytest.mark.asyncio
async def test_server_manager_keeps_client_state_consistent_during_connect_disconnect() -> None:
    manager = MCPServerManager(config_path=_make_config_path(), client_factory=SlowFakeMCPClient)
    await manager.add_server(_server_config("race-server", enabled=False))
    connect_task = asyncio.create_task(manager.connect_server("race-server"))
    await asyncio.sleep(0)
    disconnect_task = asyncio.create_task(manager.disconnect_server("race-server"))
    await asyncio.gather(connect_task, disconnect_task)
    status = (await manager.list_servers())[0]
    client = await manager.get_client("race-server")
    assert status.connected is False
    assert client is None


@pytest.mark.asyncio
async def test_tool_bridge_sync_all_is_serialized_under_concurrency() -> None:
    manager = MCPServerManager(config_path=_make_config_path(), client_factory=SlowFakeMCPClient)
    await manager.add_server(_server_config("server-a"))
    await manager.add_server(_server_config("server-b"))
    registry = ToolRegistry()
    bridge = MCPToolBridge(manager, registry)
    results = await asyncio.gather(*(bridge.sync_all() for _ in range(3)))
    tool_names = sorted(tool.name for tool in registry.list_definitions())
    assert results == [2, 2, 2]
    assert tool_names == ["mcp__server-a__echo", "mcp__server-b__echo"]


@pytest.mark.asyncio
async def test_list_servers_and_add_server_do_not_raise_concurrent_iteration_errors() -> None:
    manager = MCPServerManager(config_path=_make_config_path(), client_factory=SlowFakeMCPClient)
    await manager.add_server(_server_config("initial-server", enabled=False))
    results = await asyncio.gather(
        manager.list_servers(),
        manager.add_server(_server_config("new-server", enabled=False)),
    )
    statuses, new_id = results
    assert {status.id for status in statuses} <= {"initial-server", "new-server"}
    assert new_id == "new-server"
    assert sorted(status.id for status in await manager.list_servers()) == ["initial-server", "new-server"]
