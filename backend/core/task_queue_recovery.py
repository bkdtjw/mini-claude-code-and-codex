from __future__ import annotations

from time import time

from backend.common.logging import get_logger
from backend.core.task_queue_support import TaskQueueStore, _lease_expired
from backend.core.task_queue_types import TaskStatus

logger = get_logger(component="task_queue")


async def recover_stale_task_payloads(queue: TaskQueueStore) -> int:
    checked = 0
    recovered = 0
    failed = 0
    now = time()
    for task_id in await queue._task_ids():
        payload = await queue.get_status(task_id)
        checked += 1
        if payload is None:
            await queue._redis.srem(queue._index_key, task_id)
            continue
        if payload.status != TaskStatus.RUNNING or not _lease_expired(payload, now):
            continue
        if payload.retry_count < payload.max_retries:
            has_checkpoint = await queue.has_checkpoint(payload.task_id)
            pending = payload.model_copy(
                update={
                    "status": TaskStatus.PENDING,
                    "worker_id": "",
                    "started_at": 0.0,
                    "lease_expires_at": 0.0,
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
                has_checkpoint=has_checkpoint,
            )
            continue
        await _safe_fail(queue, payload.task_id, f"超时重试 {payload.max_retries} 次后仍未完成")
        refreshed = await queue.get_status(payload.task_id)
        if refreshed is not None and refreshed.status == TaskStatus.FAILED:
            failed += 1
            logger.warning(
                "stale_task_expired",
                namespace=queue.namespace,
                task_id=payload.task_id,
                max_retries=payload.max_retries,
            )
    _log_scan(queue.namespace, checked, recovered, failed)
    return recovered


def _log_scan(namespace: str, checked: int, recovered: int, failed: int) -> None:
    payload = {
        "namespace": namespace,
        "checked": checked,
        "recovered": recovered,
        "failed": failed,
    }
    if failed:
        logger.warning("stale_task_scan", **payload)
    elif recovered:
        logger.info("stale_task_scan", **payload)
    else:
        logger.debug("stale_task_scan", **payload)


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


__all__ = ["recover_stale_task_payloads"]
