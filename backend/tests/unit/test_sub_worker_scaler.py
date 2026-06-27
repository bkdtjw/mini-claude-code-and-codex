from __future__ import annotations

import asyncio

import pytest

import backend.sub_worker_scaler as scaler
from backend.api.task_queue_consumer import SubAgentConsumerContext
from backend.core.task_queue import TaskPayload, TaskStatus
from backend.sub_worker_scaler import WorkerPoolConfig, WorkerPoolController


class FakeQueue:
    namespace = "sub_agent"

    def __init__(self) -> None:
        self.statuses: dict[str, TaskPayload] = {}

    async def _task_ids(self) -> list[str]:
        return list(self.statuses)

    async def get_status(self, task_id: str) -> TaskPayload | None:
        return self.statuses.get(task_id)


def _payload(task_id: str, status: TaskStatus) -> TaskPayload:
    return TaskPayload(
        task_id=task_id,
        namespace="sub_agent",
        input_data={},
        status=status,
        created_at=0.0,
    )


@pytest.mark.asyncio
async def test_worker_pool_scales_up_and_only_scales_down_when_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_consume(_context: SubAgentConsumerContext) -> bool:
        await asyncio.sleep(0)
        return False

    monkeypatch.setattr(scaler, "consume_next_sub_agent_task", fake_consume)
    queue = FakeQueue()
    shutdown = asyncio.Event()
    controller = WorkerPoolController(
        SubAgentConsumerContext(queue=queue, runtime=object()),  # type: ignore[arg-type]
        shutdown,
        WorkerPoolConfig(default_concurrency=2, max_concurrency=4, idle_seconds=0.0),
    )

    controller._scale_to(2)  # noqa: SLF001
    queue.statuses = {f"task-{index}": _payload(f"task-{index}", TaskStatus.PENDING) for index in range(4)}
    await controller._adjust_once()  # noqa: SLF001
    assert len(controller._consumers) == 4  # noqa: SLF001

    queue.statuses = {"task-1": _payload("task-1", TaskStatus.RUNNING)}
    await controller._adjust_once()  # noqa: SLF001
    assert len(controller._consumers) == 4  # noqa: SLF001

    queue.statuses = {}
    await controller._adjust_once()  # noqa: SLF001
    await controller._adjust_once()  # noqa: SLF001
    assert len(controller._consumers) == 2  # noqa: SLF001
    await controller._cancel_consumers()  # noqa: SLF001
