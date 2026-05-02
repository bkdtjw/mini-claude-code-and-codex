from __future__ import annotations

from collections.abc import Awaitable, Callable

from backend.common.logging import get_logger
from backend.common.types import Message

CheckpointFn = Callable[[str, Message], Awaitable[None]]
logger = get_logger(component="agent_loop")


async def safe_checkpoint(checkpoint_fn: CheckpointFn | None, session_id: str, message: Message) -> bool:
    if checkpoint_fn is None:
        return True
    try:
        await checkpoint_fn(session_id, message)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "agent_checkpoint_failed",
            session_id=session_id,
            message_id=message.id,
            role=message.role,
            error=str(exc),
        )
        return False


__all__ = ["CheckpointFn", "safe_checkpoint"]
