from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import text

from backend.common.errors import AgentError
from backend.common.logging import get_worker_id
from backend.config import get_redis
from backend.core import create_sub_agent_task_queue
from backend.core.task_queue import TaskQueue
from backend.storage import SubAgentTaskStore
from backend.storage.database import engine


def init_task_queue(app: FastAPI) -> TaskQueue:
    try:
        redis = get_redis()
        if redis is None:
            raise AgentError("TASK_QUEUE_REDIS_MISSING", "Redis client is not initialized.")
        queue = create_sub_agent_task_queue(redis, persistence=SubAgentTaskStore())
        app.state.task_queue = queue
        app.state.worker_id = get_worker_id()
        return queue
    except AgentError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AgentError("TASK_QUEUE_INIT_ERROR", str(exc)) from exc


async def check_readiness() -> dict[str, bool]:
    postgres_ready = False
    redis_ready = False
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        postgres_ready = True
    except Exception:
        postgres_ready = False
    try:
        redis = get_redis()
        if redis is not None:
            await redis.ping()
            redis_ready = True
    except Exception:
        redis_ready = False
    return {"postgres": postgres_ready, "redis": redis_ready}


__all__ = ["check_readiness", "init_task_queue"]
