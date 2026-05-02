from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import pytest

import backend.core.s01_agent_loop.checkpoint as checkpoint_module
from backend.adapters.base import LLMAdapter
from backend.common.errors import AgentError
from backend.common.types import AgentConfig, LLMRequest, LLMResponse, Message, StreamChunk, ToolCall, ToolDefinition, ToolParameterSchema, ToolResult
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools import ToolRegistry


class MockAdapter(LLMAdapter):
    def __init__(
        self,
        responses: list[LLMResponse],
        before_complete: Callable[[int, LLMRequest], Awaitable[None]] | None = None,
    ) -> None:
        self._responses = responses
        self._before_complete = before_complete
        self.requests: list[LLMRequest] = []

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        index = len(self.requests)
        if self._before_complete is not None:
            await self._before_complete(index, request)
        self.requests.append(request)
        return self._responses[index] if index < len(self._responses) else LLMResponse(content="")

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


def _tool_def(name: str) -> ToolDefinition:
    return ToolDefinition(name=name, description=name, category="shell", parameters=ToolParameterSchema())


def _registry(executor: Callable[[dict[str, object]], Awaitable[ToolResult]] | None = None) -> ToolRegistry:
    async def echo_tool(_: dict[str, object]) -> ToolResult:
        return ToolResult(output="ok")

    registry = ToolRegistry()
    registry.register(_tool_def("echo"), executor or echo_tool)
    return registry


@pytest.mark.asyncio
async def test_checkpoint_called_and_awaited_before_next_step() -> None:
    checkpoints: list[tuple[str, str]] = []

    async def checkpoint(session_id: str, message: Message) -> None:
        checkpoints.append((session_id, message.role))

    async def before_complete(index: int, _: LLMRequest) -> None:
        if index == 0:
            assert checkpoints == [("session-1", "user")]
        if index == 1:
            assert [role for _, role in checkpoints] == ["user", "assistant", "tool"]

    adapter = MockAdapter(
        [
            LLMResponse(content="", tool_calls=[ToolCall(id="tc_1", name="echo", arguments={})]),
            LLMResponse(content="done"),
        ],
        before_complete=before_complete,
    )
    loop = AgentLoop(AgentConfig(model="test", session_id="session-1"), adapter, _registry(), checkpoint_fn=checkpoint)

    result = await loop.run("go")

    assert result.content == "done"
    assert [role for _, role in checkpoints] == ["user", "assistant", "tool", "assistant"]


@pytest.mark.asyncio
async def test_run_without_checkpoint_fn_keeps_existing_behavior() -> None:
    loop = AgentLoop(
        AgentConfig(model="test"),
        MockAdapter([LLMResponse(content="done")]),
        ToolRegistry(),
    )

    result = await loop.run("hello")

    assert result.content == "done"
    assert [message.role for message in loop.messages] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_checkpoint_error_is_logged_and_does_not_stop_run(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[tuple[str, dict[str, object]]] = []

    class FakeLogger:
        def warning(self, event: str, **kwargs: object) -> None:
            warnings.append((event, kwargs))

    async def failing_checkpoint(_: str, __: Message) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(checkpoint_module, "logger", FakeLogger())
    loop = AgentLoop(
        AgentConfig(model="test", session_id="session-1"),
        MockAdapter([LLMResponse(content="done")]),
        ToolRegistry(),
        checkpoint_fn=failing_checkpoint,
    )

    result = await loop.run("hello")

    assert result.content == "done"
    assert warnings and warnings[0][0] == "agent_checkpoint_failed"
    assert warnings[0][1]["session_id"] == "session-1"


@pytest.mark.asyncio
async def test_abort_keeps_already_checkpointed_messages() -> None:
    checkpoints: list[Message] = []
    loop_holder: dict[str, AgentLoop] = {}

    async def checkpoint(_: str, message: Message) -> None:
        checkpoints.append(message.model_copy(deep=True))

    async def aborting_tool(_: dict[str, object]) -> ToolResult:
        loop_holder["loop"].abort()
        return ToolResult(output="ok")

    adapter = MockAdapter([LLMResponse(content="", tool_calls=[ToolCall(id="tc_1", name="echo", arguments={})])])
    loop = AgentLoop(
        AgentConfig(model="test", session_id="session-1", max_iterations=2),
        adapter,
        _registry(aborting_tool),
        checkpoint_fn=checkpoint,
    )
    loop_holder["loop"] = loop

    with pytest.raises(AgentError, match="LOOP_ABORTED"):
        await loop.run("go")

    assert [message.role for message in checkpoints] == ["user", "assistant", "tool"]
