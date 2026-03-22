from __future__ import annotations

from typing import Any

from backend.common.errors import ToolError
from backend.common.types import ToolDefinition, ToolExecuteFn


class ToolRegistry:
    """Tool registry for managing available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._executors: dict[str, ToolExecuteFn] = {}

    def register(self, definition: ToolDefinition, executor: ToolExecuteFn) -> None:
        if definition.name in self._tools:
            raise ToolError(
                code="TOOL_ALREADY_REGISTERED",
                message=f"Tool already registered: {definition.name}",
                tool_name=definition.name,
                tool_call_id="",
            )
        self._tools[definition.name] = definition
        self._executors[definition.name] = executor

    def get(self, name: str) -> tuple[ToolDefinition, ToolExecuteFn] | None:
        definition = self._tools.get(name)
        if definition is None:
            return None
        return definition, self._executors[name]

    def list_definitions(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def get_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": definition.name,
                "description": definition.description,
                "parameters": definition.parameters.model_dump(),
            }
            for definition in self._tools.values()
        ]

    def remove(self, name: str) -> bool:
        if name not in self._tools:
            return False
        self._tools.pop(name, None)
        self._executors.pop(name, None)
        return True

    def has(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


__all__ = ["ToolRegistry"]
