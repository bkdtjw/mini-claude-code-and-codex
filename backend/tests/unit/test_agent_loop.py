from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from backend.adapters.base import LLMAdapter
from backend.common.errors import AgentError
from backend.common.types import AgentConfig, LLMRequest, LLMResponse, Message, StreamChunk, ToolCall, ToolDefinition, ToolParameterSchema, ToolResult
from backend.core.s01_agent_loop.agent_loop import AgentLoop
from backend.core.s02_tools.registry import ToolRegistry


class MockAdapter(LLMAdapter):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = responses
        self.requests: list[LLMRequest] = []
        self._index = 0

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self._index >= len(self.responses):
            return LLMResponse(content="")
        response = self.responses[self._index]
        self._index += 1
        return response

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


def _tool_def(name: str) -> ToolDefinition:
    return ToolDefinition(name=name, description=name, category="shell", parameters=ToolParameterSchema())


@pytest.mark.asyncio
async def test_run_without_tool_calls_returns_assistant_message() -> None:
    loop = AgentLoop(AgentConfig(model="test-model"), MockAdapter([LLMResponse(content="hello")]), ToolRegistry())
    result = await loop.run("hi")
    assert result.role == "assistant"
    assert result.content == "hello"
    assert loop.status == "done"


@pytest.mark.asyncio
async def test_run_with_tool_calls_then_final_answer() -> None:
    async def echo_tool(_: dict[str, object]) -> ToolResult:
        return ToolResult(tool_call_id="tc_1", output="tool-ok")

    registry = ToolRegistry()
    registry.register(_tool_def("echo"), echo_tool)
    responses = [
        LLMResponse(content="", tool_calls=[ToolCall(id="tc_1", name="echo", arguments={"x": 1})]),
        LLMResponse(content="final answer"),
    ]
    adapter = MockAdapter(responses)
    loop = AgentLoop(AgentConfig(model="test-model"), adapter, registry)
    result = await loop.run("use tool")
    assert result.content == "final answer"
    assert len(adapter.requests) == 2
    assert any(msg.role == "tool" for msg in loop.messages)


@pytest.mark.asyncio
async def test_run_raises_on_max_iterations() -> None:
    async def no_op(_: dict[str, object]) -> ToolResult:
        return ToolResult(tool_call_id="tc_1", output="ok")

    registry = ToolRegistry()
    registry.register(_tool_def("echo"), no_op)
    loop = AgentLoop(
        AgentConfig(model="test-model", max_iterations=1),
        MockAdapter([LLMResponse(content="", tool_calls=[ToolCall(id="tc_1", name="echo", arguments={})])]),
        registry,
    )
    with pytest.raises(AgentError, match="LOOP_MAX_ITERATIONS"):
        await loop.run("loop")


@pytest.mark.asyncio
async def test_abort_interrupts_loop() -> None:
    async def no_op(_: dict[str, object]) -> ToolResult:
        return ToolResult(tool_call_id="tc_1", output="ok")

    registry = ToolRegistry()
    registry.register(_tool_def("echo"), no_op)
    loop = AgentLoop(
        AgentConfig(model="test-model", max_iterations=2),
        MockAdapter([LLMResponse(content="", tool_calls=[ToolCall(id="tc_1", name="echo", arguments={})])]),
        registry,
    )
    loop.abort()
    with pytest.raises(AgentError, match="LOOP_ABORTED"):
        await loop.run("stop")


@pytest.mark.asyncio
async def test_events_emitted_for_status_and_tools() -> None:
    async def no_op(_: dict[str, object]) -> ToolResult:
        return ToolResult(tool_call_id="tc_1", output="ok")

    registry = ToolRegistry()
    registry.register(_tool_def("echo"), no_op)
    adapter = MockAdapter(
        [
            LLMResponse(content="", tool_calls=[ToolCall(id="tc_1", name="echo", arguments={})]),
            LLMResponse(content="done"),
        ]
    )
    loop = AgentLoop(AgentConfig(model="test-model"), adapter, registry)
    events: list[tuple[str, str]] = []
    loop.on(lambda event: events.append((event.type, str(event.data))))
    await loop.run("go")
    event_types = [item[0] for item in events]
    assert "status_change" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types


@pytest.mark.asyncio
async def test_run_stops_after_three_consecutive_tool_failures() -> None:
    async def failing_tool(_: dict[str, object]) -> ToolResult:
        return ToolResult(output="PermissionError [WinError 5] 拒绝访问。", is_error=True)

    registry = ToolRegistry()
    registry.register(_tool_def("bash"), failing_tool)
    adapter = MockAdapter(
        [
            LLMResponse(content="", tool_calls=[ToolCall(id="tc_1", name="bash", arguments={"command": "dir"})]),
            LLMResponse(content="", tool_calls=[ToolCall(id="tc_2", name="bash", arguments={"command": "dir /a"})]),
            LLMResponse(content="", tool_calls=[ToolCall(id="tc_3", name="bash", arguments={"command": "cd && dir"})]),
            LLMResponse(content="should not be reached"),
        ]
    )
    loop = AgentLoop(AgentConfig(model="test-model", max_consecutive_tool_failures=3), adapter, registry)
    result = await loop.run("查看目录")
    assert "连续失败 3 次" in result.content
    assert "PermissionError" in result.content
    assert result.role == "assistant"
    assert loop.status == "done"
    assert len(adapter.requests) == 3
