from __future__ import annotations

import asyncio
from time import monotonic

import pytest

from backend.common.types import (
    SecurityPolicy,
    SignedToolCall,
    ToolCall,
    ToolDefinition,
    ToolParameterSchema,
    ToolResult,
)
from backend.core.s02_tools.executor import ToolExecutor
from backend.core.s02_tools.registry import ToolRegistry
from backend.core.s02_tools.security_gate import SecurityGate


def _tool_def(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=name,
        category="shell",
        parameters=ToolParameterSchema(),
    )


def _gate(registry: ToolRegistry) -> SecurityGate:
    return SecurityGate(SecurityPolicy(allowed_tools=[], dangerous_tools=[]), registry)


def _signed(gate: SecurityGate, calls: list[ToolCall]) -> list[SignedToolCall]:
    return gate.authorize(calls).signed_calls


@pytest.mark.asyncio
async def test_signed_batch_executes_verified_tools_in_parallel() -> None:
    async def slow(args: dict[str, object]) -> ToolResult:
        await asyncio.sleep(0.2)
        return ToolResult(output=str(args["value"]))

    registry = ToolRegistry()
    registry.register(_tool_def("slow"), slow)
    gate = _gate(registry)
    executor = ToolExecutor(registry)
    calls = [
        ToolCall(id="call-a", name="slow", arguments={"value": "a"}),
        ToolCall(id="call-b", name="slow", arguments={"value": "b"}),
        ToolCall(id="call-c", name="slow", arguments={"value": "c"}),
    ]
    started = monotonic()
    results = await executor.execute_signed_batch(_signed(gate, calls), gate)
    elapsed = monotonic() - started
    assert [item.output for item in results] == ["a", "b", "c"]
    assert elapsed < 0.45


@pytest.mark.asyncio
async def test_signed_batch_keeps_input_order_with_verify_failure() -> None:
    async def echo(args: dict[str, object]) -> ToolResult:
        return ToolResult(output=str(args["value"]))

    registry = ToolRegistry()
    registry.register(_tool_def("echo"), echo)
    gate = _gate(registry)
    executor = ToolExecutor(registry)
    signed_calls = _signed(
        gate,
        [
            ToolCall(id="call-a", name="echo", arguments={"value": "a"}),
            ToolCall(id="call-b", name="echo", arguments={"value": "b"}),
            ToolCall(id="call-c", name="echo", arguments={"value": "c"}),
        ],
    )
    signed_calls[1] = signed_calls[1].model_copy(update={"signature": "bad"})
    reordered = [signed_calls[2], signed_calls[1], signed_calls[0]]
    results = await executor.execute_signed_batch(reordered, gate)
    assert [item.tool_call_id for item in results] == ["call-c", "call-b", "call-a"]
    assert [item.output for item in results] == ["c", "HMAC verification failed", "a"]
    assert [item.is_error for item in results] == [False, True, False]


@pytest.mark.asyncio
async def test_signed_batch_isolates_parallel_execute_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def noop(_: dict[str, object]) -> ToolResult:
        return ToolResult(output="unused")

    async def fake_execute(tool_call: ToolCall) -> ToolResult:
        if tool_call.id == "call-b":
            raise RuntimeError("boom")
        return ToolResult(tool_call_id=tool_call.id, output=f"ok-{tool_call.id}")

    registry = ToolRegistry()
    registry.register(_tool_def("noop"), noop)
    gate = _gate(registry)
    executor = ToolExecutor(registry)
    monkeypatch.setattr(executor, "execute", fake_execute)
    signed_calls = _signed(
        gate,
        [
            ToolCall(id="call-a", name="noop", arguments={}),
            ToolCall(id="call-b", name="noop", arguments={}),
            ToolCall(id="call-c", name="noop", arguments={}),
        ],
    )
    results = await executor.execute_signed_batch(signed_calls, gate)
    assert [item.output for item in results] == ["ok-call-a", "boom", "ok-call-c"]
    assert [item.is_error for item in results] == [False, True, False]
