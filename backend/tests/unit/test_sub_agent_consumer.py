from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.api.task_queue_consumer import SubAgentConsumerContext, consume_next_sub_agent_task
from backend.common.types import Message, ToolCall
from backend.core.task_queue import TaskPayload


def _payload(**input_data: object) -> TaskPayload:
    return TaskPayload(
        task_id="task-1",
        namespace="sub_agent",
        input_data=dict(input_data),
        created_at=0.0,
    )


@pytest.mark.asyncio
async def test_consume_next_sub_agent_task_completes_successfully() -> None:
    queue = AsyncMock()
    queue.claim.return_value = _payload(spec_id="code-reviewer", input="review me", timeout_seconds=30)
    queue.complete = AsyncMock()
    queue.fail = AsyncMock()
    loop = AsyncMock()
    loop.run = AsyncMock(return_value=SimpleNamespace(content="done"))
    loop.messages = [
        Message(role="assistant", content="", tool_calls=[ToolCall(name="Read", arguments={})]),
    ]
    runtime = AsyncMock()
    runtime.create_loop_from_id = AsyncMock(return_value=loop)

    consumed = await consume_next_sub_agent_task(SubAgentConsumerContext(queue=queue, runtime=runtime))

    assert consumed is True
    runtime.create_loop_from_id.assert_called_once_with(
        "code-reviewer",
        workspace="",
        session_id="sub-agent:task-1",
        is_sub_agent=True,
    )
    queue.complete.assert_called_once_with("task-1", {"content": "done", "tool_call_count": 1})
    queue.fail.assert_not_called()


@pytest.mark.asyncio
async def test_consume_next_sub_agent_task_reports_failure() -> None:
    queue = AsyncMock()
    queue.claim.return_value = _payload(spec_id="code-reviewer", input="review me")
    queue.complete = AsyncMock()
    queue.fail = AsyncMock()
    loop = AsyncMock()
    loop.run = AsyncMock(side_effect=RuntimeError("boom"))
    loop.messages = []
    runtime = AsyncMock()
    runtime.create_loop_from_id = AsyncMock(return_value=loop)

    await consume_next_sub_agent_task(SubAgentConsumerContext(queue=queue, runtime=runtime))

    queue.complete.assert_not_called()
    queue.fail.assert_called_once()
    assert "boom" in queue.fail.call_args.args[1]


@pytest.mark.asyncio
async def test_consume_next_sub_agent_task_reports_timeout() -> None:
    queue = AsyncMock()
    queue.claim.return_value = _payload(spec_id="code-reviewer", input="review me", timeout_seconds=0.01)
    queue.complete = AsyncMock()
    queue.fail = AsyncMock()

    async def _slow_run(_message: str) -> None:
        await asyncio.sleep(0.05)

    loop = AsyncMock()
    loop.run = _slow_run
    loop.messages = []
    runtime = AsyncMock()
    runtime.create_loop_from_id = AsyncMock(return_value=loop)

    await consume_next_sub_agent_task(SubAgentConsumerContext(queue=queue, runtime=runtime))

    queue.complete.assert_not_called()
    queue.fail.assert_called_once()
    assert "超时" in queue.fail.call_args.args[1]


@pytest.mark.asyncio
async def test_consume_next_sub_agent_task_swallow_fail_errors() -> None:
    queue = AsyncMock()
    queue.claim.return_value = _payload(spec_id="code-reviewer", input="review me")
    queue.complete = AsyncMock()
    queue.fail = AsyncMock(side_effect=RuntimeError("redis down"))
    loop = AsyncMock()
    loop.run = AsyncMock(side_effect=RuntimeError("boom"))
    loop.messages = []
    runtime = AsyncMock()
    runtime.create_loop_from_id = AsyncMock(return_value=loop)

    consumed = await consume_next_sub_agent_task(SubAgentConsumerContext(queue=queue, runtime=runtime))

    assert consumed is True
    queue.complete.assert_not_called()
    queue.fail.assert_called_once()
