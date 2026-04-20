from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi import FastAPI
from sqlalchemy import text

from backend.api.task_queue_consumer import SubAgentConsumerContext, consume_next_sub_agent_task
from backend.common.errors import AgentError
from backend.common.logging import get_logger, get_worker_id
from backend.config import get_redis
from backend.core.sub_agent_queue import create_sub_agent_task_queue
from backend.core.task_queue import TaskQueue
from backend.storage.database import engine

logger = get_logger(component="app_runtime")
TASK_QUEUE_RECOVERY_INTERVAL_SECONDS = 30


@dataclass
class TaskQueueRuntime:
    queue: TaskQueue
    consumer_task: asyncio.Task[None]
    recovery_task: asyncio.Task[None]


async def start_task_queue_runtime(app: FastAPI) -> TaskQueueRuntime:
    try:
        redis = get_redis()
        if redis is None:
            raise AgentError("TASK_QUEUE_REDIS_MISSING", "Redis client is not initialized.")
        agent_runtime = getattr(app.state, "agent_runtime", None)
        if agent_runtime is None:
            raise AgentError("TASK_QUEUE_RUNTIME_MISSING", "Agent runtime is not initialized.")
        queue = create_sub_agent_task_queue(redis)
        runtime = TaskQueueRuntime(
            queue=queue,
            consumer_task=asyncio.create_task(
                _consume_queue(SubAgentConsumerContext(queue=queue, runtime=agent_runtime))
            ),
            recovery_task=asyncio.create_task(_recover_queue(queue)),
        )
        app.state.task_queue = queue
        app.state.task_queue_runtime = runtime
        app.state.worker_id = get_worker_id()
        return runtime
    except AgentError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AgentError("TASK_QUEUE_RUNTIME_START_ERROR", str(exc)) from exc


async def stop_task_queue_runtime(runtime: TaskQueueRuntime | None) -> None:
    try:
        if runtime is None:
            return
        for task in (runtime.consumer_task, runtime.recovery_task):
            task.cancel()
        for task in (runtime.consumer_task, runtime.recovery_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
    except Exception as exc:  # noqa: BLE001
        raise AgentError("TASK_QUEUE_RUNTIME_STOP_ERROR", str(exc)) from exc


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


async def _consume_queue(context: SubAgentConsumerContext) -> None:
    logger.info("task_queue_consumer_started", namespace=context.queue.namespace)
    while True:
        try:
            processed = await consume_next_sub_agent_task(context)
            if not processed:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "consumer_loop_error",
                namespace=context.queue.namespace,
                error=str(exc),
            )
            await asyncio.sleep(1)


async def _recover_queue(queue: TaskQueue) -> None:
    logger.info(
        "task_queue_recovery_started",
        namespace=queue.namespace,
        interval_seconds=TASK_QUEUE_RECOVERY_INTERVAL_SECONDS,
    )
    while True:
        try:
            recovered = await queue.recover_stale_tasks()
            if recovered:
                logger.info(
                    "task_queue_recovery_completed",
                    namespace=queue.namespace,
                    recovered=recovered,
                )
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("task_queue_recovery_error", namespace=queue.namespace)
        await asyncio.sleep(TASK_QUEUE_RECOVERY_INTERVAL_SECONDS)


__all__ = [
    "TaskQueueRuntime",
    "check_readiness",
    "start_task_queue_runtime",
    "stop_task_queue_runtime",
]
