from __future__ import annotations

import os
import socket
from typing import Any

from backend.common.errors import AgentError
from backend.common.logging import get_logger
from backend.config import get_redis

logger = get_logger(component="task_runtime_state")

_MIN_TRIGGER_TTL = 120
_RUNNING_TTL = 600


class SchedulerRuntimeState:
    def __init__(self, check_interval: float) -> None:
        self.trigger_ttl = max(int(check_interval * 4), _MIN_TRIGGER_TTL)
        self._owner = f"{socket.gethostname()}:{os.getpid()}"

    async def is_task_running(self, task_id: str) -> bool:
        try:
            redis = self._require_redis()
            return bool(await redis.exists(self._running_key(task_id)))
        except AgentError:
            raise
        except Exception as exc:
            logger.warning("task_running_read_failed", task_id=task_id)
            raise AgentError("SCHEDULER_RUNNING_READ_ERROR", str(exc)) from exc

    async def acquire_trigger(self, task_id: str, minute_key: str) -> bool:
        try:
            redis = self._require_redis()
            acquired = await redis.set(
                self._trigger_key(task_id, minute_key),
                "1",
                nx=True,
                ex=self.trigger_ttl,
            )
            return bool(acquired)
        except AgentError:
            raise
        except Exception as exc:
            logger.warning("task_trigger_write_failed", task_id=task_id, minute_key=minute_key)
            raise AgentError("SCHEDULER_TRIGGER_WRITE_ERROR", str(exc)) from exc

    async def acquire_running(self, task_id: str) -> bool:
        try:
            redis = self._require_redis()
            acquired = await redis.set(
                self._running_key(task_id),
                self._owner,
                nx=True,
                ex=_RUNNING_TTL,
            )
            return bool(acquired)
        except AgentError:
            raise
        except Exception as exc:
            logger.warning("task_running_write_failed", task_id=task_id)
            raise AgentError("SCHEDULER_RUNNING_WRITE_ERROR", str(exc)) from exc

    async def release_running(self, task_id: str) -> None:
        try:
            redis = self._require_redis()
            await redis.delete(self._running_key(task_id))
        except AgentError:
            raise
        except Exception as exc:
            logger.warning("task_running_delete_failed", task_id=task_id)
            raise AgentError("SCHEDULER_RUNNING_DELETE_ERROR", str(exc)) from exc

    @staticmethod
    def _require_redis() -> Any:
        redis = get_redis()
        if redis is None:
            raise AgentError(
                "SCHEDULER_REDIS_UNAVAILABLE",
                "Redis client is required for scheduler runtime state.",
            )
        return redis

    @staticmethod
    def _trigger_key(task_id: str, minute_key: str) -> str:
        return f"task:trigger:{task_id}:{minute_key}"

    @staticmethod
    def _running_key(task_id: str) -> str:
        return f"task:running:{task_id}"


__all__ = ["SchedulerRuntimeState"]
