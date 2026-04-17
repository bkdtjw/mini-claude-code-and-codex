from __future__ import annotations

import logging
import os
import socket

from backend.config import get_redis

logger = logging.getLogger(__name__)

_MIN_TRIGGER_TTL = 120
_RUNNING_TTL = 600


class SchedulerRuntimeState:
    def __init__(self, check_interval: float) -> None:
        self.trigger_ttl = max(int(check_interval * 4), _MIN_TRIGGER_TTL)
        self.triggered_minutes: dict[str, str] = {}
        self.running_tasks: set[str] = set()
        self._owner = f"{socket.gethostname()}:{os.getpid()}"

    async def is_task_running(self, task_id: str) -> bool:
        redis = get_redis()
        if redis is not None:
            try:
                if await redis.exists(self._running_key(task_id)):
                    return True
            except Exception:
                logger.warning(
                    "Failed to read Redis running key, using in-memory fallback",
                    exc_info=True,
                )
        return task_id in self.running_tasks

    async def acquire_trigger(self, task_id: str, minute_key: str) -> bool:
        redis = get_redis()
        if redis is not None:
            try:
                acquired = await redis.set(
                    self._trigger_key(task_id, minute_key),
                    "1",
                    nx=True,
                    ex=self.trigger_ttl,
                )
                return bool(acquired)
            except Exception:
                logger.warning(
                    "Failed to write Redis trigger key, using in-memory fallback",
                    exc_info=True,
                )
        if self.triggered_minutes.get(task_id) == minute_key:
            return False
        self.triggered_minutes[task_id] = minute_key
        return True

    async def acquire_running(self, task_id: str) -> bool:
        redis = get_redis()
        if redis is not None:
            try:
                acquired = await redis.set(
                    self._running_key(task_id),
                    self._owner,
                    nx=True,
                    ex=_RUNNING_TTL,
                )
                return bool(acquired)
            except Exception:
                logger.warning(
                    "Failed to write Redis running key, using in-memory fallback",
                    exc_info=True,
                )
        if task_id in self.running_tasks:
            return False
        self.running_tasks.add(task_id)
        return True

    async def release_running(self, task_id: str) -> None:
        redis = get_redis()
        if redis is not None:
            try:
                await redis.delete(self._running_key(task_id))
            except Exception:
                logger.warning("Failed to delete Redis running key", exc_info=True)
        self.running_tasks.discard(task_id)

    @staticmethod
    def _trigger_key(task_id: str, minute_key: str) -> str:
        return f"task:trigger:{task_id}:{minute_key}"

    @staticmethod
    def _running_key(task_id: str) -> str:
        return f"task:running:{task_id}"


__all__ = ["SchedulerRuntimeState"]
