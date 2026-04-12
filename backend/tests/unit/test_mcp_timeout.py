from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import backend.core.s02_tools.mcp.client as client_module
from backend.common.errors import AgentError
from backend.common.types import MCPServerConfig, MCPServerStatus, MCPToolInfo, MCPToolResult
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.mcp import MCPClient, MCPToolBridge


class SessionPlan(BaseModel):
    initialize_delay: float = 0.0
    list_delay: float = 0.0
    call_delay: float = 0.0
    list_error: str = ""
    call_error: str = ""


class SessionClient(MCPClient):
    def __init__(self, server_config: MCPServerConfig, plan: SessionPlan) -> None:
        super().__init__(server_config)
        self._plan = plan
        self.closed_count = 0

    async def _open_transport(self, stack: object) -> tuple[object, object, object]:
        owner = self
        plan = self._plan
        server_id = self._server_config.id

        class Session:
            def __init__(self, read_stream: object, write_stream: object) -> None:
                self._read_stream = read_stream
                self._write_stream = write_stream

            async def __aenter__(self) -> "Session":
                return self

            async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
                owner.closed_count += 1

            async def initialize(self) -> None:
                if plan.initialize_delay:
                    await asyncio.sleep(plan.initialize_delay)

            async def list_tools(self) -> SimpleNamespace:
                if plan.list_delay:
                    await asyncio.sleep(plan.list_delay)
                if plan.list_error == "broken_pipe":
                    raise BrokenPipeError("broken pipe")
                return SimpleNamespace(
                    tools=[SimpleNamespace(name="echo", description="Echo", inputSchema={"type": "object"})]
                )

            async def call_tool(self, name: str, arguments: dict[str, object]) -> SimpleNamespace:
                if plan.call_delay:
                    await asyncio.sleep(plan.call_delay)
                if plan.call_error == "broken_pipe":
                    raise BrokenPipeError("broken pipe")
                return SimpleNamespace(content=[SimpleNamespace(text=f"{name}:{arguments.get('value', 'ok')}")], isError=False)

        return Session, object(), object()


class BridgeClient:
    def __init__(self, mode: str) -> None:
        self._mode = mode
        self.is_connected = True

    async def call_tool(self, name: str, arguments: dict[str, object]) -> MCPToolResult:
        if self._mode == "disconnect":
            self.is_connected = False
            raise AgentError("MCP_CALL_TOOL_ERROR", "broken pipe")
        if self._mode == "business":
            raise AgentError("MCP_CALL_TOOL_ERROR", "Invalid arguments")
        return MCPToolResult(content=f"{name}:{arguments.get('value', 'ok')}")


class BridgeManager:
    def __init__(self, clients: list[BridgeClient]) -> None:
        self._clients = clients
        self._current: BridgeClient | None = None
        self.connect_calls = 0
        self.version = 0

    async def get_client(self, server_id: str) -> BridgeClient | None:
        return self._current

    async def connect_server(self, server_id: str) -> MCPServerStatus:
        self._current = self._clients[self.connect_calls]
        self.connect_calls += 1
        return MCPServerStatus(id=server_id, name=server_id, transport="stdio", connected=True, enabled=True)


def _config() -> MCPServerConfig:
    return MCPServerConfig(id="timeout-server", name="Timeout Server", transport="stdio", command="npx", args=["demo"])


@pytest.mark.asyncio
async def test_connect_timeout_marks_client_disconnected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "CONNECT_TIMEOUT", 0.01)
    client = SessionClient(_config(), SessionPlan(initialize_delay=0.1))
    with pytest.raises(AgentError) as exc_info:
        await client.connect()
    assert exc_info.value.code == "MCP_CONNECT_TIMEOUT"
    assert client.is_connected is False
    assert client.closed_count == 1


@pytest.mark.asyncio
async def test_call_tool_timeout_marks_connection_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "CALL_TOOL_TIMEOUT", 0.01)
    client = SessionClient(_config(), SessionPlan(call_delay=0.1))
    await client.connect()
    with pytest.raises(AgentError) as exc_info:
        await client.call_tool("echo", {})
    assert exc_info.value.code == "MCP_CALL_TOOL_TIMEOUT"
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_list_tools_timeout_marks_connection_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "LIST_TOOLS_TIMEOUT", 0.01)
    client = SessionClient(_config(), SessionPlan(list_delay=0.1))
    await client.connect()
    with pytest.raises(AgentError) as exc_info:
        await client.list_tools()
    assert exc_info.value.code == "MCP_LIST_TOOLS_TIMEOUT"
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_connection_error_marks_client_dead() -> None:
    client = SessionClient(_config(), SessionPlan(call_error="broken_pipe"))
    await client.connect()
    with pytest.raises(AgentError) as exc_info:
        await client.call_tool("echo", {})
    assert exc_info.value.code == "MCP_CALL_TOOL_ERROR"
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_executor_reconnects_once_after_connection_failure() -> None:
    bridge = MCPToolBridge(BridgeManager([BridgeClient("disconnect"), BridgeClient("success")]), ToolRegistry())
    result = await bridge._build_executor("timeout-server", "echo")({"value": "ok"})
    assert result.is_error is False
    assert result.output == "echo:ok"
    assert bridge._server_manager.connect_calls == 2


@pytest.mark.asyncio
async def test_executor_returns_error_after_retry_failure() -> None:
    bridge = MCPToolBridge(BridgeManager([BridgeClient("disconnect"), BridgeClient("disconnect")]), ToolRegistry())
    result = await bridge._build_executor("timeout-server", "echo")({"value": "ok"})
    assert result.is_error is True
    assert "failed after retry" in result.output


@pytest.mark.asyncio
async def test_executor_does_not_retry_business_error() -> None:
    bridge = MCPToolBridge(BridgeManager([BridgeClient("business")]), ToolRegistry())
    result = await bridge._build_executor("timeout-server", "echo")({"value": "ok"})
    assert result.is_error is True
    assert "Invalid arguments" in result.output
    assert bridge._server_manager.connect_calls == 1
