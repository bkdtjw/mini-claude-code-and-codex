from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from backend.adapters.base import LLMAdapter
from backend.common.types import (
    AgentConfig,
    LLMRequest,
    LLMResponse,
    SecurityPolicy,
    SignedToolCall,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    ToolParameterSchema,
    ToolResult,
)
from backend.core.s01_agent_loop.agent_loop import AgentLoop
from backend.core.s02_tools import ToolExecutor, ToolRegistry
from backend.core.s02_tools.security_gate import SecurityGate


class MockAdapter(LLMAdapter):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = responses
        self._index = 0

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if self._index >= len(self._responses):
            return LLMResponse(content="")
        response = self._responses[self._index]
        self._index += 1
        return response

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


def _tool_def(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=name,
        category="shell",
        parameters=ToolParameterSchema(),
    )


def _registry_with_echo() -> ToolRegistry:
    async def _echo(_: dict[str, object]) -> ToolResult:
        return ToolResult(output="ok")

    registry = ToolRegistry()
    registry.register(_tool_def("echo"), _echo)
    return registry


def _policy(**kwargs: object) -> SecurityPolicy:
    return SecurityPolicy(**{"allowed_tools": [], "dangerous_tools": [], **kwargs})


def test_authorize_and_verify_success() -> None:
    gate = SecurityGate(_policy(), _registry_with_echo())
    result = gate.authorize([ToolCall(id="call-1", name="echo", arguments={"x": 1})])
    assert len(result.signed_calls) == 1 and result.rejected_results == []
    assert gate.verify(result.signed_calls[0]) is True


def test_verify_detects_tampered_signature() -> None:
    gate = SecurityGate(_policy(), _registry_with_echo())
    signed_call = gate.authorize(
        [ToolCall(id="call-1", name="echo", arguments={"x": 1})]
    ).signed_calls[0]
    tampered = signed_call.model_copy(
        deep=True,
        update={"tool_call": signed_call.tool_call.model_copy(update={"arguments": {"x": 2}})},
    )
    assert gate.verify(tampered) is False


def test_verify_blocks_replay() -> None:
    gate = SecurityGate(_policy(), _registry_with_echo())
    signed_call = gate.authorize(
        [ToolCall(id="call-1", name="echo", arguments={"x": 1})]
    ).signed_calls[0]
    assert gate.verify(signed_call) is True
    assert gate.verify(signed_call) is False


def test_authorize_rejects_non_whitelisted_tool() -> None:
    gate = SecurityGate(_policy(allowed_tools=["Read"]), _registry_with_echo())
    result = gate.authorize([ToolCall(id="call-1", name="echo", arguments={})])
    assert result.signed_calls == []
    assert result.rejected_results[0].tool_call_id == "call-1"
    assert "tool not allowed" in result.rejected_results[0].output


def test_authorize_rejects_unknown_tool() -> None:
    gate = SecurityGate(_policy(), ToolRegistry())
    result = gate.authorize([ToolCall(id="call-1", name="missing", arguments={})])
    assert result.signed_calls == []
    assert "unknown tool" in result.rejected_results[0].output


def test_authorize_respects_max_calls_per_turn() -> None:
    gate = SecurityGate(_policy(max_calls_per_turn=2), _registry_with_echo())
    result = gate.authorize(
        [
            ToolCall(id="call-1", name="echo", arguments={"x": 1}),
            ToolCall(id="call-2", name="echo", arguments={"x": 2}),
            ToolCall(id="call-3", name="echo", arguments={"x": 3}),
        ]
    )
    assert [item.sequence for item in result.signed_calls] == [1, 2]
    assert result.rejected_results[0].tool_call_id == "call-3"
    assert "max calls per turn exceeded" in result.rejected_results[0].output


@pytest.mark.asyncio
async def test_execute_signed_rejects_invalid_signature() -> None:
    registry = _registry_with_echo()
    gate = SecurityGate(_policy(), registry)
    executor = ToolExecutor(registry)
    signed_call = gate.authorize([ToolCall(id="call-1", name="echo", arguments={})]).signed_calls[0]
    forged = SignedToolCall(
        tool_call=signed_call.tool_call,
        sequence=signed_call.sequence,
        timestamp=signed_call.timestamp,
        signature="deadbeef",
    )
    result = await executor.execute_signed(forged, gate)
    assert result.is_error is True and result.output == "HMAC verification failed"


def test_reset_resets_sequence_counter() -> None:
    gate = SecurityGate(_policy(), _registry_with_echo())
    first = gate.authorize([ToolCall(id="call-1", name="echo", arguments={})]).signed_calls[0]
    gate.reset()
    second = gate.authorize([ToolCall(id="call-2", name="echo", arguments={})]).signed_calls[0]
    assert first.sequence == 1 and second.sequence == 1


@pytest.mark.asyncio
async def test_agent_loop_emits_security_reject_event() -> None:
    registry = _registry_with_echo()
    loop = AgentLoop(
        AgentConfig(model="test-model"),
        MockAdapter(
            [
                LLMResponse(
                    content="",
                    tool_calls=[ToolCall(id="call-1", name="echo", arguments={"x": 1})],
                ),
                LLMResponse(content="done"),
            ]
        ),
        registry,
        security_policy=SecurityPolicy(allowed_tools=["Read"], dangerous_tools=[]),
    )
    events: list[tuple[str, object]] = []
    loop.on(lambda event: events.append((event.type, event.data)))
    result = await loop.run("run tool")
    security_event = next(item for item in events if item[0] == "security_reject")
    assert result.content == "done"
    assert isinstance(security_event[1], ToolResult)
    assert "SecurityGate rejected" in security_event[1].output
