from __future__ import annotations
from time import time
from typing import Any

from backend.common.errors import AgentError
from backend.common.logging import get_logger
from backend.core.task_queue_support import recover_stale_task_payloads, wait_for_task_payloads
from backend.core.task_queue_types import TaskPayload, TaskStatus

logger = get_logger(component="task_queue")


class TaskQueueError(AgentError):
    pass


class TaskQueue:
    def __init__(
        self,
        namespace: str,
        redis_client: Any,
        task_ttl_seconds: int,
        claim_block_seconds: int,
    ) -> None:
        self._namespace = namespace
        self._redis = redis_client
        self._task_ttl_seconds = task_ttl_seconds
        self._claim_block_seconds = claim_block_seconds

    async def submit(
        self,
        task_id: str,
        input_data: dict[str, Any],
        timeout_seconds: float = 60.0,
        max_retries: int = 1,
    ) -> TaskPayload:
        try:
            payload = TaskPayload(
                task_id=task_id,
                namespace=self._namespace,
                input_data=input_data,
                created_at=time(),
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
            await self._save_payload(payload)
            await self._redis.sadd(self._index_key, task_id)
            await self._redis.expire(self._index_key, self._task_ttl_seconds)
            await self._redis.lpush(self._queue_key, task_id)
            await self._redis.expire(self._queue_key, self._task_ttl_seconds)
            logger.info("task_submitted", namespace=self._namespace, task_id=task_id)
            return payload
        except Exception as exc:  # noqa: BLE001
            raise TaskQueueError("TASK_QUEUE_SUBMIT_ERROR", str(exc)) from exc

    async def claim(self, worker_id: str) -> TaskPayload | None:
        try:
            while True:
                item = await self._redis.brpop(self._queue_key, timeout=self._claim_block_seconds)
                if item is None:
                    return None
                task_id = str(item[1])
                payload = await self.get_status(task_id)
                if payload is None or payload.status != TaskStatus.PENDING:
                    continue
                claimed = payload.model_copy(
                    update={
                        "status": TaskStatus.RUNNING,
                        "worker_id": worker_id,
                        "started_at": time(),
                    }
                )
                await self._save_payload(claimed)
                logger.info("task_claimed", namespace=self._namespace, task_id=task_id)
                return claimed
        except Exception as exc:  # noqa: BLE001
            raise TaskQueueError("TASK_QUEUE_CLAIM_ERROR", str(exc)) from exc

    async def complete(self, task_id: str, result: dict[str, Any]) -> None:
        try:
            await self._update_terminal_state(task_id, TaskStatus.SUCCEEDED, result=result, error="")
        except Exception as exc:  # noqa: BLE001
            raise TaskQueueError("TASK_QUEUE_COMPLETE_ERROR", str(exc)) from exc

    async def fail(self, task_id: str, error: str) -> None:
        try:
            await self._update_terminal_state(task_id, TaskStatus.FAILED, result=None, error=error)
        except Exception as exc:  # noqa: BLE001
            raise TaskQueueError("TASK_QUEUE_FAIL_ERROR", str(exc)) from exc

    async def get_status(self, task_id: str) -> TaskPayload | None:
        try:
            data = await self._redis.get(self._task_key(task_id))
            return None if data is None else TaskPayload.model_validate_json(str(data))
        except Exception as exc:  # noqa: BLE001
            raise TaskQueueError("TASK_QUEUE_STATUS_ERROR", str(exc)) from exc

    async def wait_for_tasks(
        self,
        task_ids: list[str],
        poll_interval: float = 0.5,
        global_timeout: float = 0.0,
    ) -> list[TaskPayload]:
        try:
            return await wait_for_task_payloads(self, task_ids, poll_interval, global_timeout)
        except Exception as exc:  # noqa: BLE001
            raise TaskQueueError("TASK_QUEUE_WAIT_ERROR", str(exc)) from exc

    async def recover_stale_tasks(self) -> int:
        try:
            return await recover_stale_task_payloads(self)
        except Exception as exc:  # noqa: BLE001
            raise TaskQueueError("TASK_QUEUE_RECOVER_ERROR", str(exc)) from exc

    async def _update_terminal_state(
        self,
        task_id: str,
        status: TaskStatus,
        result: dict[str, Any] | None,
        error: str,
    ) -> None:
        payload = await self.get_status(task_id)
        if payload is None:
            raise TaskQueueError("TASK_QUEUE_MISSING", f"Task not found: {task_id}")
        if payload.status != TaskStatus.RUNNING:
            logger.warning(
                "task_terminal_update_skipped",
                namespace=self._namespace,
                task_id=task_id,
                current_status=payload.status.value,
                target_status=status.value,
            )
            return
        await self._save_payload(payload.model_copy(update={"status": status, "result": result, "error": error}))

    async def _save_payload(self, payload: TaskPayload) -> None:
        await self._redis.set(
            self._task_key(payload.task_id),
            payload.model_dump_json(),
            ex=self._task_ttl_seconds,
        )

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def _index_key(self) -> str:
        return f"task:{self._namespace}:index"

    @property
    def _queue_key(self) -> str:
        return f"task:{self._namespace}:queue"

    def _task_key(self, task_id: str) -> str:
        return f"task:{self._namespace}:{task_id}"


__all__ = ["TaskPayload", "TaskQueue", "TaskQueueError", "TaskStatus"]
