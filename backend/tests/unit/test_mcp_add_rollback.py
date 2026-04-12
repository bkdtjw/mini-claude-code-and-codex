from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import BaseModel

from backend.common.errors import AgentError
from backend.common.types import MCPServerConfig, MCPToolInfo
from backend.core.s02_tools.mcp import MCPClient, MCPServerManager


class ClientPlan(BaseModel):
    fail_connect: bool = False
    fail_list_tools: bool = False
    tool_name: str = "echo"


class StubClient(MCPClient):
    def __init__(self, server_config: MCPServerConfig, plan: ClientPlan) -> None:
        self._server_config = server_config
        self._plan = plan
        self._connected = False
        self.disconnect_calls = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        if self._plan.fail_connect:
            raise AgentError("MCP_CONNECT_ERROR", "connect failed")
        self._connected = True

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self._connected = False

    async def list_tools(self) -> list[MCPToolInfo]:
        if self._plan.fail_list_tools:
            raise AgentError("MCP_LIST_TOOLS_ERROR", "list tools failed")
        return [
            MCPToolInfo(
                name=self._plan.tool_name,
                description="Echo",
                input_schema={"type": "object"},
                server_id=self._server_config.id,
            )
        ]


class ClientFactory:
    def __init__(self, plans: list[ClientPlan]) -> None:
        self._plans = plans
        self.calls = 0
        self.clients: list[StubClient] = []

    def __call__(self, server_config: MCPServerConfig) -> StubClient:
        if self.calls >= len(self._plans):
            raise AssertionError("Unexpected client creation.")
        client = StubClient(server_config, self._plans[self.calls])
        self.calls += 1
        self.clients.append(client)
        return client


def _config(server_id: str = "rollback-server", enabled: bool = True) -> MCPServerConfig:
    return MCPServerConfig(
        id=server_id,
        name=server_id,
        transport="stdio",
        command="npx",
        args=["demo"],
        enabled=enabled,
    )


def _make_manager(plans: list[ClientPlan]) -> tuple[MCPServerManager, ClientFactory, Path]:
    root = Path(__file__).resolve().parents[1] / ".tmp_mcp_add_rollback"
    root.mkdir(exist_ok=True)
    temp_dir = root / uuid4().hex
    temp_dir.mkdir()
    config_path = temp_dir / "mcp_servers.json"
    config_path.write_text(json.dumps({"servers": []}), encoding="utf-8")
    factory = ClientFactory(plans)
    return MCPServerManager(config_path=str(config_path), client_factory=factory), factory, config_path


def _saved_ids(config_path: Path) -> set[str]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return {item["id"] for item in payload["servers"]}


@pytest.mark.asyncio
async def test_add_server_connect_failure_does_not_persist() -> None:
    config = _config()
    manager, factory, config_path = _make_manager([ClientPlan(fail_connect=True)])
    with pytest.raises(AgentError) as exc_info:
        await manager.add_server(config)
    assert exc_info.value.code == "MCP_CONNECT_ERROR"
    assert config.id not in manager._servers
    assert config.id not in manager._clients
    assert config.id not in _saved_ids(config_path)
    assert factory.clients[0].disconnect_calls == 1


@pytest.mark.asyncio
async def test_add_server_can_retry_after_connect_failure() -> None:
    config = _config()
    manager, _, _ = _make_manager([])
    manager._client_factory = ClientFactory([ClientPlan(fail_connect=True), ClientPlan()])
    with pytest.raises(AgentError):
        await manager.add_server(config)
    assert await manager.add_server(config) == config.id


@pytest.mark.asyncio
async def test_add_server_list_tools_failure_rolls_back_and_disconnects() -> None:
    config = _config()
    manager, factory, config_path = _make_manager([ClientPlan(fail_list_tools=True)])
    with pytest.raises(AgentError) as exc_info:
        await manager.add_server(config)
    assert exc_info.value.code == "MCP_LIST_TOOLS_ERROR"
    assert config.id not in manager._servers
    assert config.id not in manager._clients
    assert config.id not in _saved_ids(config_path)
    assert factory.clients[0].disconnect_calls == 1


@pytest.mark.asyncio
async def test_add_server_disabled_saves_without_connecting() -> None:
    config = _config(enabled=False)
    manager, factory, config_path = _make_manager([])
    assert await manager.add_server(config) == config.id
    assert factory.calls == 0
    assert config.id in _saved_ids(config_path)
    assert config.id not in manager._clients


@pytest.mark.asyncio
async def test_connect_server_failure_keeps_existing_config_clean() -> None:
    config = _config(enabled=False)
    manager, _, config_path = _make_manager([])
    await manager.add_server(config)
    factory = ClientFactory([ClientPlan(fail_connect=True)])
    manager._client_factory = factory
    with pytest.raises(AgentError) as exc_info:
        await manager.connect_server(config.id)
    assert exc_info.value.code == "MCP_CONNECT_ERROR"
    assert config.id in manager._servers
    assert config.id in _saved_ids(config_path)
    assert config.id not in manager._clients
    assert factory.clients[0].disconnect_calls == 1


@pytest.mark.asyncio
async def test_connect_server_success_replaces_existing_client() -> None:
    config = _config(enabled=False)
    manager, _, _ = _make_manager([])
    await manager.add_server(config)
    factory = ClientFactory([ClientPlan(tool_name="first"), ClientPlan(tool_name="second")])
    manager._client_factory = factory
    await manager.connect_server(config.id)
    old_client = factory.clients[0]
    await manager.connect_server(config.id)
    assert old_client.disconnect_calls == 1
    assert manager._clients[config.id] is factory.clients[1]
    assert manager._tool_cache[config.id][0].name == "second"


@pytest.mark.asyncio
async def test_remove_server_disconnects_and_clears_state() -> None:
    config = _config(enabled=False)
    manager, _, config_path = _make_manager([])
    await manager.add_server(config)
    factory = ClientFactory([ClientPlan()])
    manager._client_factory = factory
    await manager.connect_server(config.id)
    client = factory.clients[0]
    assert await manager.remove_server(config.id) is True
    assert client.disconnect_calls == 1
    assert config.id not in manager._servers
    assert config.id not in manager._clients
    assert config.id not in manager._tool_cache
    assert config.id not in _saved_ids(config_path)
