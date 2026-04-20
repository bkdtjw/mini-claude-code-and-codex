from __future__ import annotations

from typing import Any

from backend.core.task_queue import TaskQueue

SUB_AGENT_TASK_QUEUE_NAMESPACE = "sub_agent"
SUB_AGENT_TASK_QUEUE_TTL_SECONDS = 86400
SUB_AGENT_TASK_QUEUE_CLAIM_BLOCK_SECONDS = 1


def create_sub_agent_task_queue(redis_client: Any) -> TaskQueue:
    return TaskQueue(
        namespace=SUB_AGENT_TASK_QUEUE_NAMESPACE,
        redis_client=redis_client,
        task_ttl_seconds=SUB_AGENT_TASK_QUEUE_TTL_SECONDS,
        claim_block_seconds=SUB_AGENT_TASK_QUEUE_CLAIM_BLOCK_SECONDS,
    )


__all__ = [
    "SUB_AGENT_TASK_QUEUE_CLAIM_BLOCK_SECONDS",
    "SUB_AGENT_TASK_QUEUE_NAMESPACE",
    "SUB_AGENT_TASK_QUEUE_TTL_SECONDS",
    "create_sub_agent_task_queue",
]
