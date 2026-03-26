from __future__ import annotations

import asyncio

from backend.common.types import ToolCall, ToolResult

from .registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    @staticmethod
    def _normalize_result(tool_call: ToolCall, result: ToolResult) -> ToolResult:
        return result.model_copy(update={"tool_call_id": tool_call.id})

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        try:
            tool = self._registry.get(tool_call.name)
            if tool is None:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    output=f"Unknown tool: {tool_call.name}",
                    is_error=True,
                )
            _, executor = tool
            try:
                return self._normalize_result(tool_call, await executor(tool_call.arguments))
            except Exception as exc:  # noqa: BLE001
                return ToolResult(
                    tool_call_id=tool_call.id, output=str(exc), is_error=True
                )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(tool_call_id=tool_call.id, output=str(exc), is_error=True)

    async def execute_batch(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        try:
            return list(await asyncio.gather(*(self.execute(call) for call in tool_calls)))
        except Exception as exc:  # noqa: BLE001
            return [
                ToolResult(tool_call_id=call.id, output=str(exc), is_error=True)
                for call in tool_calls
            ]


__all__ = ["ToolExecutor"]
