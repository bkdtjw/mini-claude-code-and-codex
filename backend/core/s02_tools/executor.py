from __future__ import annotations

import asyncio
from time import monotonic

from backend.common.logging import get_logger
from backend.common.metrics import incr
from backend.common.types import SignedToolCall, ToolCall, ToolDefinition, ToolResult

from .registry import ToolRegistry
from .security_gate import SecurityGate

MAX_TOOL_OUTPUT_CHARS = 12000
TOOL_OUTPUT_HEAD_CHARS = 6000
TOOL_OUTPUT_TAIL_CHARS = 6000

logger = get_logger(component="tool_executor")


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    @classmethod
    def _truncate_output(cls, tool_name: str, output: str) -> str:
        if len(output) <= MAX_TOOL_OUTPUT_CHARS:
            return output
        truncated = len(output) - MAX_TOOL_OUTPUT_CHARS
        head = output[:TOOL_OUTPUT_HEAD_CHARS]
        tail = output[-TOOL_OUTPUT_TAIL_CHARS:]
        marker = f"\n...[truncated {truncated} characters]...\n"
        logger.debug(
            "tool_output_truncated",
            tool=tool_name,
            original_length=len(output),
            truncated_to=MAX_TOOL_OUTPUT_CHARS,
        )
        return f"{head}{marker}{tail}"

    @classmethod
    def _finalize_result(cls, tool_call: ToolCall, result: ToolResult) -> ToolResult:
        return result.model_copy(
            update={
                "tool_call_id": tool_call.id,
                "output": cls._truncate_output(tool_call.name, result.output),
            }
        )

    def list_definitions(self) -> list[ToolDefinition]:
        return self._registry.list_definitions()

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        started_at = monotonic()
        logger.info("tool_execute_start", tool=tool_call.name, tool_call_id=tool_call.id)
        await incr("tool_calls")
        try:
            tool = self._registry.get(tool_call.name)
            if tool is None:
                result = self._finalize_result(
                    tool_call,
                    ToolResult(
                        tool_call_id=tool_call.id,
                        output=f"Unknown tool: {tool_call.name}",
                        is_error=True,
                    ),
                )
                await self._log_result(tool_call, result, started_at)
                return result
            _, executor = tool
            try:
                result = self._finalize_result(tool_call, await executor(tool_call.arguments))
                await self._log_result(tool_call, result, started_at)
                return result
            except Exception as exc:  # noqa: BLE001
                result = self._finalize_result(
                    tool_call,
                    ToolResult(
                        tool_call_id=tool_call.id,
                        output=str(exc),
                        is_error=True,
                    ),
                )
                await self._log_result(tool_call, result, started_at)
                return result
        except Exception as exc:  # noqa: BLE001
            result = self._finalize_result(
                tool_call,
                ToolResult(tool_call_id=tool_call.id, output=str(exc), is_error=True),
            )
            await self._log_result(tool_call, result, started_at)
            return result

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

    async def _log_result(self, tool_call: ToolCall, result: ToolResult, started_at: float) -> None:
        duration_ms = int((monotonic() - started_at) * 1000)
        if result.is_error:
            logger.warning(
                "tool_execute_error",
                tool=tool_call.name,
                tool_call_id=tool_call.id,
                error=result.output[:200],
                duration_ms=duration_ms,
            )
            await incr("tool_errors")
            return
        logger.info(
            "tool_execute_end",
            tool=tool_call.name,
            tool_call_id=tool_call.id,
            duration_ms=duration_ms,
            output_length=len(result.output),
        )


__all__ = ["ToolExecutor"]
