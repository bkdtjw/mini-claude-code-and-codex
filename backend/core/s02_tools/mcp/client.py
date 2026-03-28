from __future__ import annotations

import json
import os
from contextlib import AsyncExitStack
from typing import Any

from backend.common.errors import AgentError
from backend.common.types import MCPServerConfig, MCPToolInfo, MCPToolResult


class MCPClient:
    """Connect to one MCP server and expose its tools."""

    def __init__(self, server_config: MCPServerConfig) -> None:
        self._server_config = server_config
        self._session: Any | None = None
        self._stack: AsyncExitStack | None = None

    @property
    def is_connected(self) -> bool:
        return self._session is not None and self._stack is not None

    async def connect(self) -> None:
        stack: AsyncExitStack | None = None
        try:
            if self.is_connected:
                return
            stack = AsyncExitStack()
            session_cls, read_stream, write_stream = await self._open_transport(stack)
            session = await stack.enter_async_context(session_cls(read_stream, write_stream))
            await session.initialize()
            self._stack = stack
            self._session = session
        except AgentError:
            if stack is not None:
                await stack.aclose()
            raise
        except Exception as exc:
            if stack is not None:
                await stack.aclose()
            raise AgentError("MCP_CONNECT_ERROR", str(exc)) from exc

    async def disconnect(self) -> None:
        try:
            if self._stack is not None:
                await self._stack.aclose()
        except Exception as exc:
            raise AgentError("MCP_DISCONNECT_ERROR", str(exc)) from exc
        finally:
            self._session = None
            self._stack = None

    async def list_tools(self) -> list[MCPToolInfo]:
        try:
            session = await self._ensure_session()
            result = await session.list_tools()
            return [
                MCPToolInfo(
                    name=str(getattr(tool, "name", "")),
                    description=str(getattr(tool, "description", "") or ""),
                    input_schema=self._extract_schema(tool),
                    server_id=self._server_config.id,
                )
                for tool in getattr(result, "tools", [])
            ]
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("MCP_LIST_TOOLS_ERROR", str(exc)) from exc

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolResult:
        try:
            session = await self._ensure_session()
            result = await session.call_tool(name, arguments=arguments)
            return MCPToolResult(
                content=self._format_tool_result(result),
                is_error=bool(getattr(result, "isError", getattr(result, "is_error", False))),
            )
        except AgentError:
            raise
        except Exception as exc:
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


__all__ = ["MCPClient"]
