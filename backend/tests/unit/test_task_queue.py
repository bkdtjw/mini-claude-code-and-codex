from __future__ import annotations

import asyncio

import pytest

from backend.config import get_redis
from backend.core.task_queue import TaskQueue
from backend.core.task_queue_types import TaskStatus

from .redis_test_support import use_fake_redis


@pytest.fixture
async def queue(monkeypatch: pytest.MonkeyPatch) -> TaskQueue:
    await use_fake_redis(monkeypatch)
    redis = get_redis()
    assert redis is not None
    return TaskQueue(
        namespace="sub_agent",
        redis_client=redis,
        task_ttl_seconds=86400,
        claim_block_seconds=1,
    )


@pytest.mark.asyncio
async def test_submit_claim_complete_flow(queue: TaskQueue) -> None:
    submitted = await queue.submit("task-1", {"prompt": "hello"})
    claimed = await queue.claim("worker-1")
    assert claimed is not None
    await queue.complete("task-1", {"output": "done"})
    status = await queue.get_status("task-1")
    assert submitted.status == TaskStatus.PENDING
    assert claimed.status == TaskStatus.RUNNING
    assert status is not None
    assert status.status == TaskStatus.SUCCEEDED
    assert status.result == {"output": "done"}


@pytest.mark.asyncio
async def test_recover_stale_running_task_returns_to_queue(queue: TaskQueue) -> None:
    await queue.submit("task-2", {"prompt": "recover"}, timeout_seconds=0.01, max_retries=1)
    first_claim = await queue.claim("worker-1")
    assert first_claim is not None
    await asyncio.sleep(0.02)
    recovered = await queue.recover_stale_tasks()
    second_claim = await queue.claim("worker-2")
    assert recovered == 1
    assert second_claim is not None
    assert second_claim.task_id == "task-2"
    assert second_claim.retry_count == 1
    assert second_claim.worker_id == "worker-2"


@pytest.mark.asyncio
async def test_fail_updates_task_status(queue: TaskQueue) -> None:
    await queue.submit("task-3", {"prompt": "fail"})
    claimed = await queue.claim("worker-1")
    assert claimed is not None
    await queue.fail("task-3", "boom")
    status = await queue.get_status("task-3")
    assert status is not None
    assert status.status == TaskStatus.FAILED
    assert status.error == "boom"


@pytest.mark.asyncio
async def test_wait_for_tasks_returns_terminal_states(queue: TaskQueue) -> None:
    await queue.submit("task-4", {"prompt": "a"})
    await queue.submit("task-5", {"prompt": "b"})
    await queue.claim("worker-1")
    await queue.claim("worker-2")

    async def _finish_tasks() -> None:
        await asyncio.sleep(0.01)
        await queue.complete("task-4", {"output": "ok"})
        await asyncio.sleep(0.01)
        await queue.fail("task-5", "bad")

    waiter = asyncio.create_task(queue.wait_for_tasks(["task-4", "task-5"], poll_interval=0.01))
    finisher = asyncio.create_task(_finish_tasks())
    statuses = await waiter
    await finisher
    by_id = {status.task_id: status for status in statuses}
    assert by_id["task-4"].status == TaskStatus.SUCCEEDED
    assert by_id["task-5"].status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_wait_for_tasks_global_timeout_marks_running_tasks_failed(queue: TaskQueue) -> None:
    await queue.submit("task-6", {"prompt": "hang"})
    claimed = await queue.claim("worker-1")
    assert claimed is not None

    statuses = await queue.wait_for_tasks(["task-6"], poll_interval=0.01, global_timeout=0.02)

    assert len(statuses) == 1
    assert statuses[0].status == TaskStatus.FAILED
    assert "等待超时" in statuses[0].error


@pytest.mark.asyncio
async def test_recover_stale_running_task_fails_after_max_retries(queue: TaskQueue) -> None:
    await queue.submit("task-7", {"prompt": "expire"}, timeout_seconds=0.01, max_retries=0)
    claimed = await queue.claim("worker-1")
    assert claimed is not None
    await asyncio.sleep(0.02)

    recovered = await queue.recover_stale_tasks()
    status = await queue.get_status("task-7")

    assert recovered == 0
    assert status is not None
    assert status.status == TaskStatus.FAILED
    assert "重试" in status.error
