from __future__ import annotations

import asyncio

import pytest

from backend.config import get_redis
from backend.core.task_queue import (
    CapacitySubmitRequest,
    QueueSubmitSpec,
    TaskQueue,
    TaskQueueError,
)
from backend.core.task_queue_types import TaskStatus

from .redis_test_support import use_fake_redis


@pytest.fixture
async def queue(monkeypatch: pytest.MonkeyPatch) -> TaskQueue:
    await use_fake_redis(monkeypatch)
    redis = get_redis()
    assert redis is not None
    return TaskQueue("sub_agent", redis, 86400, 1)


def _request(parent: str, task_ids: list[str], max_active: int) -> CapacitySubmitRequest:
    return CapacitySubmitRequest(
        max_active=max_active,
        specs=[
            QueueSubmitSpec(task_id=task_id, input_data={"parent_task_id": parent})
            for task_id in task_ids
        ],
    )


@pytest.mark.asyncio
async def test_submit_many_with_capacity_rejects_extra_active_child(
    queue: TaskQueue,
) -> None:
    await queue.submit_many_with_capacity(_request("parent-1", ["task-a"], 1))

    with pytest.raises(TaskQueueError) as exc:
        await queue.submit_many_with_capacity(_request("parent-1", ["task-b"], 1))

    children = await queue.get_children("parent-1")
    assert exc.value.code == "TASK_QUEUE_CAPACITY_EXCEEDED"
    assert [child.task_id for child in children] == ["task-a"]
    assert await queue.get_status("task-b") is None


@pytest.mark.asyncio
async def test_submit_many_with_capacity_is_all_or_nothing(queue: TaskQueue) -> None:
    await queue.submit_many_with_capacity(_request("parent-2", ["task-a"], 2))

    with pytest.raises(TaskQueueError):
        await queue.submit_many_with_capacity(_request("parent-2", ["task-b", "task-c"], 2))

    assert await queue.get_status("task-b") is None
    assert await queue.get_status("task-c") is None


@pytest.mark.asyncio
async def test_terminal_child_releases_capacity(queue: TaskQueue) -> None:
    await queue.submit_many_with_capacity(_request("parent-3", ["task-a"], 1))
    assert await queue.fail("task-a", "done")

    saved = await queue.submit_many_with_capacity(_request("parent-3", ["task-b"], 1))

    assert [payload.task_id for payload in saved] == ["task-b"]


@pytest.mark.asyncio
async def test_concurrent_capacity_submits_keep_one_winner(queue: TaskQueue) -> None:
    results = await asyncio.gather(
        queue.submit_many_with_capacity(_request("parent-4", ["task-a"], 1)),
        queue.submit_many_with_capacity(_request("parent-4", ["task-b"], 1)),
        return_exceptions=True,
    )

    successes = [item for item in results if not isinstance(item, Exception)]
    failures = [item for item in results if isinstance(item, TaskQueueError)]
    children = await queue.get_children("parent-4")

    assert len(successes) == 1
    assert len(failures) == 1
    assert len(children) == 1
    assert children[0].status == TaskStatus.PENDING
