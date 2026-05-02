from __future__ import annotations

from typing import Any

from backend.core.task_queue import TaskQueue
from backend.core.task_queue_persistence import TaskPersistence

SUB_AGENT_TASK_QUEUE_NAMESPACE = "sub_agent"
SUB_AGENT_TASK_QUEUE_TTL_SECONDS = 86400
SUB_AGENT_TASK_QUEUE_CLAIM_BLOCK_SECONDS = 1


def create_sub_agent_task_queue(
    redis_client: Any,
    persistence: TaskPersistence | None = None,
) -> TaskQueue:
    return TaskQueue(
        namespace=SUB_AGENT_TASK_QUEUE_NAMESPACE,
        redis_client=redis_client,
        task_ttl_seconds=SUB_AGENT_TASK_QUEUE_TTL_SECONDS,
        claim_block_seconds=SUB_AGENT_TASK_QUEUE_CLAIM_BLOCK_SECONDS,
        persistence=persistence,
    )


__all__ = [
    "SUB_AGENT_TASK_QUEUE_CLAIM_BLOCK_SECONDS",
    "SUB_AGENT_TASK_QUEUE_NAMESPACE",
    "SUB_AGENT_TASK_QUEUE_TTL_SECONDS",
    "create_sub_agent_task_queue",
]
