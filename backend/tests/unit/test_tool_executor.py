from __future__ import annotations

import pytest

from backend.common.types import ToolCall, ToolDefinition, ToolParameterSchema, ToolResult
from backend.core.s02_tools.executor import ToolExecutor
from backend.core.s02_tools.registry import ToolRegistry


def _make_definition(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"{name} description",
        category="shell",
        parameters=ToolParameterSchema(),
    )


@pytest.mark.asyncio
async def test_execute_success_returns_result() -> None:
    async def ok_executor(_: dict[str, object]) -> ToolResult:
        return ToolResult(tool_call_id="call_1", output="ok")

    registry = ToolRegistry()
    registry.register(_make_definition("run_shell"), ok_executor)
    executor = ToolExecutor(registry)
    result = await executor.execute(ToolCall(id="call_1", name="run_shell", arguments={}))
    assert result.is_error is False
    assert result.output == "ok"
    assert result.tool_call_id == "call_1"


@pytest.mark.asyncio
async def test_execute_normalizes_tool_call_id_from_builtin_result() -> None:
    async def ok_executor(_: dict[str, object]) -> ToolResult:
        return ToolResult(output="ok")

    registry = ToolRegistry()
    registry.register(_make_definition("run_shell"), ok_executor)
    executor = ToolExecutor(registry)
    result = await executor.execute(ToolCall(id="call_9", name="run_shell", arguments={}))
    assert result.is_error is False
    assert result.output == "ok"
    assert result.tool_call_id == "call_9"


@pytest.mark.asyncio
async def test_execute_unknown_tool_returns_error() -> None:
    executor = ToolExecutor(ToolRegistry())
    result = await executor.execute(ToolCall(id="call_2", name="missing", arguments={}))
    assert result.is_error is True
    assert result.output == "Unknown tool: missing"
    assert result.tool_call_id == "call_2"


@pytest.mark.asyncio
async def test_execute_executor_raises_returns_error() -> None:
    async def bad_executor(_: dict[str, object]) -> ToolResult:
        raise RuntimeError("boom")

    registry = ToolRegistry()
    registry.register(_make_definition("explode"), bad_executor)
    executor = ToolExecutor(registry)
    result = await executor.execute(ToolCall(id="call_3", name="explode", arguments={}))
    assert result.is_error is True
    assert result.output == "boom"
    assert result.tool_call_id == "call_3"


@pytest.mark.asyncio
async def test_execute_batch_multiple_tools() -> None:
    async def echo_executor(args: dict[str, object]) -> ToolResult:
        return ToolResult(tool_call_id=str(args["id"]), output=str(args["id"]))

    registry = ToolRegistry()
    registry.register(_make_definition("echo"), echo_executor)
    executor = ToolExecutor(registry)
    calls = [
        ToolCall(id="call_a", name="echo", arguments={"id": "a"}),
        ToolCall(id="call_b", name="missing", arguments={}),
        ToolCall(id="call_c", name="echo", arguments={"id": "c"}),
    ]
    results = await executor.execute_batch(calls)
    assert [item.output for item in results] == ["a", "Unknown tool: missing", "c"]
    assert [item.is_error for item in results] == [False, True, False]


@pytest.mark.asyncio
async def test_execute_truncates_large_output() -> None:
    async def large_executor(_: dict[str, object]) -> ToolResult:
        return ToolResult(output=("a" * 7000) + ("b" * 7000))

    registry = ToolRegistry()
    registry.register(_make_definition("large"), large_executor)
    executor = ToolExecutor(registry)
    result = await executor.execute(ToolCall(id="call_large", name="large", arguments={}))
    assert result.output.startswith("a" * 6000)
    assert result.output.endswith("b" * 6000)
    assert "[truncated 2000 characters]" in result.output
