from __future__ import annotations

from time import time
from typing import Any

from backend.common.logging import get_logger
from backend.core.task_queue_types import TaskPayload, TaskStatus

logger = get_logger(component="task_queue")


async def claim_task(queue: Any, worker_id: str) -> TaskPayload | None:
    while True:
        item = await queue._redis.brpop(queue._queue_key, timeout=queue._claim_block_seconds)
        if item is None:
            return None
        task_id = str(item[1])
        if queue._persistence is not None:
            claimed = await queue._persistence.claim(task_id, worker_id)
            if claimed is None:
                continue
            await queue._cache_payload(claimed)
            logger.info("task_claimed", namespace=queue.namespace, task_id=task_id)
            return claimed
        payload = await queue.get_status(task_id)
        if payload is None or payload.status != TaskStatus.PENDING:
            continue
        now = time()
        claimed = payload.model_copy(
            update={
                "status": TaskStatus.RUNNING,
                "worker_id": worker_id,
                "started_at": now,
                "lease_expires_at": now + payload.timeout_seconds,
            }
        )
        await queue._save_payload(claimed)
        logger.info("task_claimed", namespace=queue.namespace, task_id=task_id)
        return claimed


__all__ = ["claim_task"]
