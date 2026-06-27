from __future__ import annotations

from typing import Any

from backend.common.errors import AgentError
from backend.core.task_queue_types import TaskPayload


async def get_queue_children(queue: Any, parent_task_id: str) -> list[TaskPayload]:
    if not parent_task_id:
        return []
    try:
        if queue._persistence is not None:
            return await queue._persistence.get_children(parent_task_id)
        children: list[TaskPayload] = []
        for task_id in await queue._task_ids():
            payload = await queue.get_status(task_id)
            if payload is not None and payload.parent_task_id == parent_task_id:
                children.append(payload)
        return children
    except Exception as exc:  # noqa: BLE001
        raise AgentError("TASK_QUEUE_CHILDREN_ERROR", str(exc)) from exc


__all__ = ["get_queue_children"]
