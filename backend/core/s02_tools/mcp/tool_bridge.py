from __future__ import annotations

from typing import Any

from backend.common.errors import AgentError
from backend.common.types import (
    MCPToolInfo,
    ToolDefinition,
    ToolParameterSchema,
    ToolPermission,
    ToolResult,
)
from backend.core.s02_tools.registry import ToolRegistry

from .server_manager import MCPServerManager


class MCPToolBridge:
    """Bridge MCP tools into the project's ToolRegistry."""

    def __init__(self, server_manager: MCPServerManager, registry: ToolRegistry) -> None:
        self._server_manager = server_manager
        self._registry = registry
        self._server_tools: dict[str, set[str]] = {}

    async def sync_server_tools(self, server_id: str) -> int:
        try:
            await self.remove_server_tools(server_id)
            tool_names: set[str] = set()
            for tool in await self._server_manager.refresh_tools(server_id):
                definition = self._build_definition(server_id, tool)
                self._registry.register(definition, self._build_executor(server_id, tool.name))
                tool_names.add(definition.name)
            self._server_tools[server_id] = tool_names
            return len(tool_names)
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("MCP_SYNC_SERVER_TOOLS_ERROR", str(exc)) from exc

    async def sync_all(self) -> int:
        try:
            total = 0
            for status in await self._server_manager.list_servers():
                if status.enabled:
                    total += await self.sync_server_tools(status.id)
            return total
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("MCP_SYNC_ALL_TOOLS_ERROR", str(exc)) from exc

    async def remove_server_tools(self, server_id: str) -> int:
        try:
            names = self._server_tools.pop(server_id, self._discover_names(server_id))
            removed = 0
            for name in names:
                if self._registry.remove(name):
                    removed += 1
            return removed
        except Exception as exc:
            raise AgentError("MCP_REMOVE_SERVER_TOOLS_ERROR", str(exc)) from exc

    def _discover_names(self, server_id: str) -> set[str]:
        prefix = self._tool_prefix(server_id)
        return {tool.name for tool in self._registry.list_definitions() if tool.name.startswith(prefix)}

    def _build_definition(self, server_id: str, tool: MCPToolInfo) -> ToolDefinition:
        return ToolDefinition(
            name=f"{self._tool_prefix(server_id)}{tool.name}",
            description=tool.description or f"MCP tool {tool.name} from {server_id}",
            category="mcp",
            parameters=self._to_parameter_schema(tool.input_schema),
            permission=ToolPermission(requires_approval=True, sandboxed=False),
        )

    def _to_parameter_schema(self, input_schema: dict[str, Any]) -> ToolParameterSchema:
        return ToolParameterSchema(
            type=str(input_schema.get("type", "object")),
            description=str(input_schema.get("description", "")),
            required=list(input_schema.get("required", [])),
            properties=dict(input_schema.get("properties", {})),
        )

    def _build_executor(self, server_id: str, tool_name: str):
        async def execute(args: dict[str, Any]) -> ToolResult:
            try:
                client = await self._server_manager.get_client(server_id)
                if client is None or not client.is_connected:
                    await self._server_manager.connect_server(server_id)
                    client = await self._server_manager.get_client(server_id)
                if client is None:
                    return ToolResult(output=f"MCP server not connected: {server_id}", is_error=True)
                result = await client.call_tool(tool_name, args)
                return ToolResult(output=result.content, is_error=result.is_error)
            except Exception as exc:
                return ToolResult(output=str(exc), is_error=True)

        return execute

    def _tool_prefix(self, server_id: str) -> str:
        return f"mcp__{server_id}__"


__all__ = ["MCPToolBridge"]
