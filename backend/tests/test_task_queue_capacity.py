from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.config import get_redis
from backend.core.task_queue import (
    CapacitySubmitRequest,
    QueueSubmitSpec,
    TaskQueue,
    TaskQueueError,
)
from backend.core.task_queue_types import TaskStatus
from backend.storage import SubAgentTaskStore
from backend.storage.database import SessionFactory


class FailingRedis:
    async def sadd(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def lpush(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("redis enqueue failed")

    async def expire(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def set(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def get(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def smembers(self, *_args: Any, **_kwargs: Any) -> list[str]:
        return []

    async def brpop(self, *_args: Any, **_kwargs: Any) -> None:
        return None


@pytest.fixture
def queue(db_session_factory: SessionFactory) -> TaskQueue:
    redis = get_redis()
    assert redis is not None
    return TaskQueue(
        "sub_agent",
        redis,
        86400,
        1,
        persistence=SubAgentTaskStore(db_session_factory),
    )


def _request(parent: str, task_ids: list[str], max_active: int) -> CapacitySubmitRequest:
    return CapacitySubmitRequest(
        max_active=max_active,
        specs=[
            QueueSubmitSpec(task_id=task_id, input_data={"parent_task_id": parent})
            for task_id in task_ids
        ],
    )


@pytest.mark.asyncio
async def test_persistent_concurrent_capacity_submits_keep_one_winner(
    queue: TaskQueue,
) -> None:
    results = await asyncio.gather(
        queue.submit_many_with_capacity(_request("db-parent-1", ["db-task-a"], 1)),
        queue.submit_many_with_capacity(_request("db-parent-1", ["db-task-b"], 1)),
        return_exceptions=True,
    )

    successes = [item for item in results if not isinstance(item, Exception)]
    failures = [item for item in results if isinstance(item, TaskQueueError)]
    children = await queue.get_children("db-parent-1")

    assert len(successes) == 1
    assert len(failures) == 1
    assert len(children) == 1
    assert children[0].status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_persistent_capacity_batch_is_all_or_nothing(queue: TaskQueue) -> None:
    await queue.submit_many_with_capacity(_request("db-parent-2", ["db-task-a"], 2))

    with pytest.raises(TaskQueueError):
        await queue.submit_many_with_capacity(
            _request("db-parent-2", ["db-task-b", "db-task-c"], 2)
        )

    assert await queue.get_status("db-task-b") is None
    assert await queue.get_status("db-task-c") is None


@pytest.mark.asyncio
async def test_persistent_terminal_child_releases_capacity(queue: TaskQueue) -> None:
    await queue.submit_many_with_capacity(_request("db-parent-3", ["db-task-a"], 1))
    claimed = await queue.claim("worker-a")
    assert claimed is not None
    assert await queue.complete(claimed.task_id, {"content": "done"}, claimed.worker_id)

    saved = await queue.submit_many_with_capacity(_request("db-parent-3", ["db-task-b"], 1))

    assert [payload.task_id for payload in saved] == ["db-task-b"]


@pytest.mark.asyncio
async def test_persistent_capacity_compensates_when_redis_enqueue_fails(
    db_session_factory: SessionFactory,
) -> None:
    queue = TaskQueue(
        "sub_agent",
        FailingRedis(),
        86400,
        1,
        persistence=SubAgentTaskStore(db_session_factory),
    )

    with pytest.raises(TaskQueueError):
        await queue.submit_many_with_capacity(_request("db-parent-4", ["db-task-a"], 1))

    status = await queue.get_status("db-task-a")
    assert status is not None
    assert status.status == TaskStatus.FAILED
    assert "redis enqueue failed" in status.error
