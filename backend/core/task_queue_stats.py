from __future__ import annotations

from dataclasses import dataclass

from backend.core.task_queue import TaskQueue, TaskStatus


@dataclass(frozen=True)
class TaskQueueSnapshot:
    pending: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0

    @property
    def unfinished(self) -> int:
        return self.pending + self.running


async def get_task_queue_snapshot(queue: TaskQueue) -> TaskQueueSnapshot:
    counts = {status: 0 for status in TaskStatus}
    for task_id in await queue._task_ids():  # noqa: SLF001 - queue has no public snapshot API.
        payload = await queue.get_status(task_id)
        if payload is not None:
            counts[payload.status] += 1
    return TaskQueueSnapshot(
        pending=counts[TaskStatus.PENDING],
        running=counts[TaskStatus.RUNNING],
        succeeded=counts[TaskStatus.SUCCEEDED],
        failed=counts[TaskStatus.FAILED],
    )


__all__ = ["TaskQueueSnapshot", "get_task_queue_snapshot"]
