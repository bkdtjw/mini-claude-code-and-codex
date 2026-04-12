from __future__ import annotations

import asyncio
import json
import os
from contextlib import AsyncExitStack
from typing import Any

from backend.common.errors import AgentError
from backend.common.types import MCPServerConfig, MCPToolInfo, MCPToolResult

CONNECT_TIMEOUT: float = 30.0
LIST_TOOLS_TIMEOUT: float = 15.0
CALL_TOOL_TIMEOUT: float = 60.0


class MCPClient:
    """Connect to one MCP server and expose its tools."""

    def __init__(self, server_config: MCPServerConfig) -> None:
        self._server_config = server_config
        self._session: Any | None = None
        self._stack: AsyncExitStack | None = None
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._session is not None and self._stack is not None

    async def connect(self) -> None:
        stack: AsyncExitStack | None = None
        try:
            async with self._lock:
                if self.is_connected:
                    return
                stack = AsyncExitStack()
                session = await asyncio.wait_for(self._open_session(stack), timeout=CONNECT_TIMEOUT)
                self._stack = stack
                self._session = session
        except asyncio.TimeoutError as exc:
            await self._close_pending_stack(stack)
            self._session = None
            self._stack = None
            raise AgentError("MCP_CONNECT_TIMEOUT", f"MCP server connection timed out after {CONNECT_TIMEOUT}s") from exc
        except AgentError:
            await self._close_pending_stack(stack)
            self._session = None
            self._stack = None
            raise
        except Exception as exc:
            await self._close_pending_stack(stack)
            self._session = None
            self._stack = None
            raise AgentError("MCP_CONNECT_ERROR", str(exc)) from exc

    async def disconnect(self) -> None:
        stack: AsyncExitStack | None = None
        try:
            async with self._lock:
                stack = self._stack
                self._session = None
                self._stack = None
                if stack is not None:
                    await stack.aclose()
        except Exception as exc:
            raise AgentError("MCP_DISCONNECT_ERROR", str(exc)) from exc

    async def list_tools(self) -> list[MCPToolInfo]:
        try:
            session = await self._ensure_session()
            result = await asyncio.wait_for(session.list_tools(), timeout=LIST_TOOLS_TIMEOUT)
            return [
                MCPToolInfo(
                    name=str(getattr(tool, "name", "")),
                    description=str(getattr(tool, "description", "") or ""),
                    input_schema=self._extract_schema(tool),
                    server_id=self._server_config.id,
                )
                for tool in getattr(result, "tools", [])
            ]
        except asyncio.TimeoutError as exc:
            await self._mark_dead()
            raise AgentError("MCP_LIST_TOOLS_TIMEOUT", f"list_tools timed out after {LIST_TOOLS_TIMEOUT}s") from exc
        except AgentError:
            raise
        except Exception as exc:
            if self._is_connection_error(exc):
                await self._mark_dead()
            raise AgentError("MCP_LIST_TOOLS_ERROR", str(exc)) from exc

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolResult:
        try:
            session = await self._ensure_session()
            result = await asyncio.wait_for(session.call_tool(name, arguments=arguments), timeout=CALL_TOOL_TIMEOUT)
            return MCPToolResult(
                content=self._format_tool_result(result),
                is_error=bool(getattr(result, "isError", getattr(result, "is_error", False))),
            )
        except asyncio.TimeoutError as exc:
            await self._mark_dead()
            raise AgentError("MCP_CALL_TOOL_TIMEOUT", f"call_tool '{name}' timed out after {CALL_TOOL_TIMEOUT}s") from exc
        except AgentError:
            raise
        except Exception as exc:
            if self._is_connection_error(exc):
                await self._mark_dead()
            raise AgentError("MCP_CALL_TOOL_ERROR", str(exc)) from exc

    async def _ensure_session(self) -> Any:
        try:
            if not self.is_connected:
                await self.connect()
            if self._session is None:
                raise AgentError("MCP_SESSION_MISSING", "MCP session is not available.")
            return self._session
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("MCP_SESSION_ERROR", str(exc)) from exc

    async def _open_transport(self, stack: AsyncExitStack) -> tuple[Any, Any, Any]:
        if self._server_config.transport == "stdio":
            try:
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client
            except ImportError as exc:
                raise AgentError("MCP_SDK_MISSING", "The 'mcp' package is not installed.") from exc
            params = StdioServerParameters(
                command=self._server_config.command,
                args=self._server_config.args,
                env={**os.environ, **self._server_config.env},
            )
            read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
            return ClientSession, read_stream, write_stream
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client
        except ImportError as exc:
            raise AgentError("MCP_SDK_MISSING", "The 'mcp' package is not installed.") from exc
        read_stream, write_stream = await stack.enter_async_context(sse_client(url=self._server_config.url))
        return ClientSession, read_stream, write_stream

    def _extract_schema(self, tool: Any) -> dict[str, Any]:
        schema = getattr(tool, "inputSchema", getattr(tool, "input_schema", {}))
        return schema if isinstance(schema, dict) else {}

    def _format_tool_result(self, result: Any) -> str:
        parts = [self._format_content_item(item) for item in getattr(result, "content", [])]
        text_parts = [part for part in parts if part]
        structured = getattr(result, "structuredContent", getattr(result, "structured_content", None))
        if structured and not text_parts:
            text_parts.append(json.dumps(structured, ensure_ascii=False))
        if not text_parts and hasattr(result, "model_dump"):
            text_parts.append(json.dumps(result.model_dump(mode="json", by_alias=True), ensure_ascii=False))
        return "\n".join(text_parts) if text_parts else ""

    def _format_content_item(self, item: Any) -> str:
        if hasattr(item, "text"):
            return str(getattr(item, "text", ""))
        resource = getattr(item, "resource", None)
        if resource is not None and hasattr(resource, "text"):
            return str(getattr(resource, "text", ""))
        if hasattr(item, "model_dump"):
            return json.dumps(item.model_dump(mode="json", by_alias=True), ensure_ascii=False)
        return str(item)

    async def _open_session(self, stack: AsyncExitStack) -> Any:
        session_cls, read_stream, write_stream = await self._open_transport(stack)
        session = await stack.enter_async_context(session_cls(read_stream, write_stream))
        await session.initialize()
        return session

    async def _mark_dead(self) -> None:
        async with self._lock:
            stack = self._stack
            self._session = None
            self._stack = None
            await self._close_pending_stack(stack)

    async def _close_pending_stack(self, stack: AsyncExitStack | None) -> None:
        if stack is None:
            return
        try:
            await stack.aclose()
        except Exception:
            return None

    def _is_connection_error(self, exc: Exception) -> bool:
        if isinstance(exc, (BrokenPipeError, ConnectionError, EOFError, OSError)):
            return True
        error_msg = str(exc).lower()
        return any(keyword in error_msg for keyword in ("broken pipe", "connection", "eof", "closed", "transport"))


__all__ = ["MCPClient"]
