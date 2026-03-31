from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest

from backend.adapters.base import LLMAdapter
from backend.common.types import (
    LLMRequest,
    LLMResponse,
    Message,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    ToolParameterSchema,
    ToolResult,
)
from backend.core.s06_context_compression import (
    ContextCompressor,
    ThresholdPolicy,
    TokenCounter,
)


class MockAdapter(LLMAdapter):
    def __init__(
        self,
        response: LLMResponse | None = None,
        should_raise: bool = False,
    ) -> None:
        self._response = response or LLMResponse(content="summary")
        self._should_raise = should_raise
        self.requests: list[LLMRequest] = []

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self._should_raise:
            raise RuntimeError("summary failed")
        return self._response

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


def _tool_definition(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"{name} description",
        category="file-ops",
        parameters=ToolParameterSchema(
            properties={"path": {"type": "string"}},
            required=["path"],
        ),
    )


def _build_messages() -> list[Message]:
    return [
        Message(role="system", content="system prompt"),
        Message(role="user", content="Need to inspect backend/core/s01_agent_loop/agent_loop.py"),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="call_read", name="Read", arguments={"path": "agent_loop.py"})],
        ),
        Message(
            role="tool",
            content="",
            tool_results=[ToolResult(tool_call_id="call_read", output="A" * 260)],
        ),
        Message(role="assistant", content="Patched backend/core/s01_agent_loop/agent_loop.py"),
        Message(role="user", content="Continue with tests"),
    ]


def test_token_counter_estimates_messages_and_tools() -> None:
    counter = TokenCounter()
    message = Message(
        role="assistant",
        content="a" * 20,
        tool_calls=[ToolCall(name="Read", arguments={"path": "demo.py"})],
        tool_results=[ToolResult(output="b" * 16)],
    )
    definitions = [_tool_definition("Read")]
    expected_messages = len(message.content) // 4
    expected_messages += len(
        json.dumps(
            message.tool_calls[0].arguments,
            default=str,
            ensure_ascii=False,
            sort_keys=True,
        )
    ) // 4
    expected_messages += len(message.tool_results[0].output) // 4
    expected_tools = len(
        json.dumps(
            definitions[0].model_dump(),
            default=str,
            ensure_ascii=False,
            sort_keys=True,
        )
    ) // 4
    assert counter.estimate_messages_tokens([message]) == expected_messages
    assert counter.estimate_tools_tokens(definitions) == expected_tools


def test_threshold_policy_respects_threshold_and_reserve_count() -> None:
    policy = ThresholdPolicy(
        max_context_tokens=100,
        compact_threshold_ratio=0.90,
        reserve_recent_count=3,
    )
    assert policy.should_compact(89) is False
    assert policy.should_compact(90) is True
    assert policy.get_reserve_count() == 3


@pytest.mark.asyncio
async def test_context_compressor_compact_returns_summary_and_recent_messages() -> None:
    adapter = MockAdapter(response=LLMResponse(content="summary body"))
    compressor = ContextCompressor(
        adapter=adapter,
        model="test-model",
        policy=ThresholdPolicy(reserve_recent_count=2),
    )
    compacted = await compressor.compact(_build_messages())
    assert [message.role for message in compacted] == ["system", "user", "assistant", "user"]
    assert compacted[1].content == "[对话历史摘要]\nsummary body"
    assert compacted[2].content == "Patched backend/core/s01_agent_loop/agent_loop.py"
    assert compacted[3].content == "Continue with tests"
    summary_prompt = adapter.requests[0].messages[1].content
    assert "Read[ok]=" in summary_prompt
    assert "A" * 201 not in summary_prompt


@pytest.mark.asyncio
async def test_context_compressor_falls_back_when_summary_call_fails() -> None:
    adapter = MockAdapter(should_raise=True)
    compressor = ContextCompressor(
        adapter=adapter,
        model="test-model",
        policy=ThresholdPolicy(reserve_recent_count=2),
    )
    compacted = await compressor.compact(_build_messages())
    assert [message.role for message in compacted] == ["system", "user", "assistant", "user"]
    assert compacted[1].content.startswith("[对话历史摘要]\n以下为降级摘要")
    assert "Need to inspect backend/core/s01_agent_loop/agent_loop.py" in compacted[1].content
    assert compacted[3].content == "Continue with tests"
