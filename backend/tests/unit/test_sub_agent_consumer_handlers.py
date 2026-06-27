from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.core.task_queue import TaskPayload
from backend.core.task_queue_consumer import SubAgentConsumerContext, consume_next_sub_agent_task


def _payload(**input_data: object) -> TaskPayload:
    return TaskPayload(
        task_id="task-handler",
        namespace="sub_agent",
        input_data=dict(input_data),
        created_at=0.0,
    )


@pytest.mark.asyncio
async def test_consumer_dispatches_registered_kind_handler() -> None:
    queue = AsyncMock()
    queue.claim.return_value = _payload(kind="custom_task")
    handler = AsyncMock()
    runtime = AsyncMock()

    consumed = await consume_next_sub_agent_task(
        SubAgentConsumerContext(
            queue=queue,
            runtime=runtime,
            task_handlers={"custom_task": handler},
        )
    )

    assert consumed is True
    handler.assert_awaited_once()
    runtime.create_loop_from_id.assert_not_called()
    runtime.create_loop_inline.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_fails_unknown_kind_without_running_agent_loop() -> None:
    queue = AsyncMock()
    queue.claim.return_value = _payload(kind="missing_task")
    queue.fail = AsyncMock()
    runtime = AsyncMock()

    consumed = await consume_next_sub_agent_task(
        SubAgentConsumerContext(queue=queue, runtime=runtime, task_handlers={})
    )

    assert consumed is True
    queue.fail.assert_called_once()
    assert "missing_task" in queue.fail.call_args.args[1]
    runtime.create_loop_from_id.assert_not_called()
    runtime.create_loop_inline.assert_not_called()
