from __future__ import annotations

import asyncio
from typing import Any

from backend.common.logging import get_logger
from backend.common.types import Message
from backend.core.task_queue import TaskQueue

logger = get_logger(component="sub_agent_consumer")


async def _heartbeat_loop(
    queue: TaskQueue,
    task_id: str,
    interval: float,
    extension: float,
) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await queue.renew_lease(task_id, extension)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sub_agent_task_heartbeat_error", task_id=task_id, error=str(exc))


def _timeout_seconds(input_data: dict[str, Any]) -> float:
    raw_timeout = input_data.get("timeout_seconds", 120)
    try:
        timeout_seconds = float(raw_timeout)
    except (TypeError, ValueError):
        return 120.0
    return timeout_seconds if timeout_seconds > 0 else 120.0


def _tool_call_count(messages: list[Any]) -> int:
    return sum(
        len(message.tool_calls)
        for message in messages
        if getattr(message, "role", "") == "assistant" and getattr(message, "tool_calls", None)
    )


def _loop_config_value(loop: Any, name: str) -> str:
    value = getattr(getattr(loop, "_config", None), name, "")
    return value if isinstance(value, str) else ""


def _restored_messages(loop: Any, messages: list[Message]) -> list[Message]:
    prompt = _loop_config_value(loop, "system_prompt")
    if prompt and (not messages or messages[0].role != "system"):
        return [Message(role="system", content=prompt), *messages]
    return messages


async def _safe_fail(queue: TaskQueue, task_id: str, error: str, worker_id: str = "") -> None:
    try:
        failed = await queue.fail(task_id, error, worker_id=worker_id)
        if not failed:
            logger.warning(
                "sub_agent_task_fail_discarded",
                task_id=task_id,
                worker_id=worker_id,
                original_error=error,
            )
    except Exception as fail_exc:  # noqa: BLE001
        logger.error(
            "sub_agent_task_fail_error",
            task_id=task_id,
            original_error=error,
            fail_error=str(fail_exc),
        )


__all__ = [
    "_heartbeat_loop",
    "_loop_config_value",
    "_restored_messages",
    "_safe_fail",
    "_timeout_seconds",
    "_tool_call_count",
]
