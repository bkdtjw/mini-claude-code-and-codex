from __future__ import annotations

import asyncio
from time import time
from typing import Any, Protocol

from backend.common.logging import get_logger
from backend.core.task_queue_types import TaskPayload, TaskStatus

logger = get_logger(component="task_queue")
TERMINAL_TASK_STATUSES = {TaskStatus.SUCCEEDED, TaskStatus.FAILED}
WAIT_TIMEOUT_ERROR = "等待超时，主 agent 放弃等待"


class TaskQueueStore(Protocol):
    namespace: str
    _redis: Any
    _index_key: str
    _queue_key: str
    _task_ttl_seconds: int

    async def get_status(self, task_id: str) -> TaskPayload | None: ...
    async def fail(self, task_id: str, error: str) -> None: ...
    async def _save_payload(self, payload: TaskPayload) -> None: ...


async def wait_for_task_payloads(
    queue: TaskQueueStore,
    task_ids: list[str],
    poll_interval: float,
    global_timeout: float,
) -> list[TaskPayload]:
    if not task_ids:
        return []
    deadline = time() + global_timeout if global_timeout > 0 else float("inf")
    while True:
        statuses = [await queue.get_status(task_id) for task_id in task_ids]
        if all(status is not None and status.status in TERMINAL_TASK_STATUSES for status in statuses):
            return [status for status in statuses if status is not None]
        if time() > deadline:
            return await _fail_stuck_tasks(queue, task_ids, statuses)
        await asyncio.sleep(poll_interval)


async def recover_stale_task_payloads(queue: TaskQueueStore) -> int:
    checked = 0
    recovered = 0
    failed = 0
    now = time()
    for raw_task_id in await queue._redis.smembers(queue._index_key):
        task_id = str(raw_task_id)
        payload = await queue.get_status(task_id)
        checked += 1
        if payload is None:
            await queue._redis.srem(queue._index_key, task_id)
            continue
        if payload.status != TaskStatus.RUNNING or (now - payload.started_at) <= payload.timeout_seconds:
            continue
        if payload.retry_count < payload.max_retries:
            pending = payload.model_copy(
                update={
                    "status": TaskStatus.PENDING,
                    "worker_id": "",
                    "started_at": 0.0,
                    "result": None,
                    "error": "",
                    "retry_count": payload.retry_count + 1,
                }
            )
            await queue._save_payload(pending)
            await queue._redis.lpush(queue._queue_key, payload.task_id)
            await queue._redis.expire(queue._queue_key, queue._task_ttl_seconds)
            recovered += 1
            logger.warning(
                "stale_task_recovered",
                namespace=queue.namespace,
                task_id=payload.task_id,
                retry_count=pending.retry_count,
                worker_id=payload.worker_id,
            )
            continue
        await _expire_stale_task(queue, payload)
        refreshed = await queue.get_status(payload.task_id)
        if refreshed is not None and refreshed.status == TaskStatus.FAILED:
            failed += 1
            logger.warning(
                "stale_task_expired",
                namespace=queue.namespace,
                task_id=payload.task_id,
                max_retries=payload.max_retries,
            )
    logger.info(
        "stale_task_scan",
        namespace=queue.namespace,
        checked=checked,
        recovered=recovered,
        failed=failed,
    )
    return recovered


async def _fail_stuck_tasks(
    queue: TaskQueueStore,
    task_ids: list[str],
    statuses: list[TaskPayload | None],
) -> list[TaskPayload]:
    final_statuses: list[TaskPayload] = []
    for task_id, status in zip(task_ids, statuses, strict=False):
        if status is None:
            continue
        if status.status in TERMINAL_TASK_STATUSES:
            final_statuses.append(status)
            continue
        await _safe_fail(queue, task_id, WAIT_TIMEOUT_ERROR)
        refreshed = await queue.get_status(task_id)
        final_statuses.append(
            refreshed
            if refreshed is not None
            else status.model_copy(update={"status": TaskStatus.FAILED, "error": WAIT_TIMEOUT_ERROR})
        )
    return final_statuses


async def _expire_stale_task(queue: TaskQueueStore, payload: TaskPayload) -> None:
    await _safe_fail(
        queue,
        payload.task_id,
        f"超时重试 {payload.max_retries} 次后仍未完成",
    )


async def _safe_fail(queue: TaskQueueStore, task_id: str, error: str) -> None:
    try:
        await queue.fail(task_id, error)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "stale_task_fail_error",
            namespace=queue.namespace,
            task_id=task_id,
            error=error,
            fail_error=str(exc),
        )
