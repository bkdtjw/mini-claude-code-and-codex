from __future__ import annotations

import asyncio

from backend.common.types import SignedToolCall, ToolCall, ToolDefinition, ToolResult

from .registry import ToolRegistry
from .security_gate import SecurityGate

MAX_TOOL_OUTPUT_CHARS = 12000
TOOL_OUTPUT_HEAD_CHARS = 6000
TOOL_OUTPUT_TAIL_CHARS = 6000


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    @classmethod
    def _truncate_output(cls, output: str) -> str:
        if len(output) <= MAX_TOOL_OUTPUT_CHARS:
            return output
        truncated = len(output) - MAX_TOOL_OUTPUT_CHARS
        head = output[:TOOL_OUTPUT_HEAD_CHARS]
        tail = output[-TOOL_OUTPUT_TAIL_CHARS:]
        marker = f"\n...[truncated {truncated} characters]...\n"
        return f"{head}{marker}{tail}"

    @classmethod
    def _finalize_result(cls, tool_call: ToolCall, result: ToolResult) -> ToolResult:
        return result.model_copy(
            update={
                "tool_call_id": tool_call.id,
                "output": cls._truncate_output(result.output),
            }
        )

    def list_definitions(self) -> list[ToolDefinition]:
        return self._registry.list_definitions()

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        try:
            tool = self._registry.get(tool_call.name)
            if tool is None:
                return self._finalize_result(
                    tool_call,
                    ToolResult(
                        tool_call_id=tool_call.id,
                        output=f"Unknown tool: {tool_call.name}",
                        is_error=True,
                    ),
                )
            _, executor = tool
            try:
                return self._finalize_result(tool_call, await executor(tool_call.arguments))
            except Exception as exc:  # noqa: BLE001
                return self._finalize_result(
                    tool_call,
                    ToolResult(
                        tool_call_id=tool_call.id,
                        output=str(exc),
                        is_error=True,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            return self._finalize_result(
                tool_call,
                ToolResult(tool_call_id=tool_call.id, output=str(exc), is_error=True),
            )

    async def execute_batch(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        try:
            return list(await asyncio.gather(*(self.execute(call) for call in tool_calls)))
        except Exception as exc:  # noqa: BLE001
            return [
                self._finalize_result(
                    call,
                    ToolResult(tool_call_id=call.id, output=str(exc), is_error=True),
                )
                for call in tool_calls
            ]

    async def execute_signed(self, signed_call: SignedToolCall, gate: SecurityGate) -> ToolResult:
        try:
            if not gate.verify(signed_call):
                return self._finalize_result(
                    signed_call.tool_call,
                    ToolResult(
                        tool_call_id=signed_call.tool_call.id,
                        output="HMAC verification failed",
                        is_error=True,
                    ),
                )
            return await self.execute(signed_call.tool_call)
        except Exception as exc:  # noqa: BLE001
            return self._finalize_result(
                signed_call.tool_call,
                ToolResult(
                    tool_call_id=signed_call.tool_call.id,
                    output=str(exc),
                    is_error=True,
                ),
            )

    async def execute_signed_batch(
        self,
        signed_calls: list[SignedToolCall],
        gate: SecurityGate,
    ) -> list[ToolResult]:
        try:
            results: list[ToolResult] = []
            for signed_call in signed_calls:
                results.append(await self.execute_signed(signed_call, gate))
            return results
        except Exception as exc:  # noqa: BLE001
            return [
                self._finalize_result(
                    signed_call.tool_call,
                    ToolResult(
                        tool_call_id=signed_call.tool_call.id,
                        output=str(exc),
                        is_error=True,
                    ),
                )
                for signed_call in signed_calls
            ]


__all__ = ["ToolExecutor"]
