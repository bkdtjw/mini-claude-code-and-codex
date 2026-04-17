from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.common.types import MCPServerConfig, MCPToolInfo, MCPToolResult
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.mcp import MCPClient, MCPServerManager, MCPToolBridge
from backend.storage import MCPServerStore

from .storage_test_support import make_test_session_factory


class FakeMCPClient(MCPClient):
    def __init__(self, server_config: MCPServerConfig) -> None:
        self._server_config = server_config
        self._connected = False
        self.calls: list[tuple[str, dict[str, object]]] = []

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
                description="Echo input text",
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
                server_id=self._server_config.id,
            )
        ]

    async def call_tool(self, name: str, arguments: dict[str, object]) -> MCPToolResult:
        self.calls.append((name, arguments))
        return MCPToolResult(content=f"echo:{arguments.get('text', '')}")


async def _make_manager(tmp_path: Path) -> MCPServerManager:
    _engine, session_factory = await make_test_session_factory(tmp_path, f"mcp_integration_{uuid4().hex}")
    return MCPServerManager(
        config_path=str(tmp_path / "empty_mcp.json"),
        client_factory=FakeMCPClient,
        store=MCPServerStore(session_factory),
    )


def _server_config() -> MCPServerConfig:
    return MCPServerConfig(
        id="filesystem",
        name="File System",
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem"],
        enabled=True,
    )


@pytest.mark.asyncio
async def test_mcp_server_manager_persists_and_lists_status(tmp_path: Path) -> None:
    manager = await _make_manager(tmp_path)
    server_id = await manager.add_server(_server_config())
    statuses = await manager.list_servers()
    assert server_id == "filesystem"
    assert len(statuses) == 1
    assert statuses[0].connected is True
    assert statuses[0].tool_count == 1


@pytest.mark.asyncio
async def test_mcp_tool_bridge_registers_prefixed_tools(tmp_path: Path) -> None:
    manager = await _make_manager(tmp_path)
    await manager.add_server(_server_config())
    registry = ToolRegistry()
    bridge = MCPToolBridge(manager, registry)
    count = await bridge.sync_all()
    tool = registry.get("mcp__filesystem__echo")
    assert count == 1
    assert tool is not None
    definition, executor = tool
    result = await executor({"text": "hello"})
    assert definition.category == "mcp"
    assert result.output == "echo:hello"
    assert result.is_error is False
