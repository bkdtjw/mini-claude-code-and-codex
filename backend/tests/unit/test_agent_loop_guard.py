from __future__ import annotations

import pytest

from backend.common.types import AgentConfig, LLMResponse, ToolCall, ToolResult
from backend.core.s01_agent_loop.agent_loop import AgentLoop
from backend.core.s02_tools.registry import ToolRegistry
from backend.tests.unit.test_agent_loop import MockAdapter, _tool_def


async def _ok_tool(_: dict[str, object]) -> ToolResult:
    return ToolResult(tool_call_id="tc", output="ok")


@pytest.mark.asyncio
async def test_agent_loop_injects_dead_end_reflection_prompt() -> None:
    registry = ToolRegistry()
    registry.register(_tool_def("echo"), _ok_tool)
    adapter = MockAdapter(
        [
            LLMResponse(content="", tool_calls=[ToolCall(name="echo", arguments={})]),
            LLMResponse(content="", tool_calls=[ToolCall(name="echo", arguments={})]),
            LLMResponse(content="", tool_calls=[ToolCall(name="echo", arguments={})]),
            LLMResponse(content="done"),
        ]
    )
    loop = AgentLoop(
        AgentConfig(
            model="test-model",
            max_iterations=5,
            dead_end_reflection_iteration=3,
        ),
        adapter,
        registry,
    )

    result = await loop.run("keep checking")

    assert result.content == "done"
    guard_content = adapter.requests[2].messages[-1].content
    assert "[死胡同反思]" in guard_content
    assert "原有的输出协议和格式" in guard_content


@pytest.mark.asyncio
async def test_agent_loop_injects_final_convergence_prompt() -> None:
    registry = ToolRegistry()
    registry.register(_tool_def("echo"), _ok_tool)
    adapter = MockAdapter(
        [
            LLMResponse(content="", tool_calls=[ToolCall(name="echo", arguments={})]),
            LLMResponse(content="final"),
        ]
    )
    loop = AgentLoop(
        AgentConfig(
            model="test-model",
            max_iterations=2,
            dead_end_reflection_iteration=10,
        ),
        adapter,
        registry,
    )

    result = await loop.run("finish if possible")

    assert result.content == "final"
    guard_content = adapter.requests[1].messages[-1].content
    assert "[最终收口提示]" in guard_content
    assert "原有的输出协议和格式" in guard_content


def test_agent_config_defaults_guard_thresholds() -> None:
    config = AgentConfig(model="test-model")

    assert config.max_consecutive_tool_failures == 5
    assert config.dead_end_reflection_iteration == 10
