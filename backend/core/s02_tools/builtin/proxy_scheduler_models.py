from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

LLMCallback = Callable[[str], Awaitable[str]]


class SchedulerError(Exception):
    """Proxy scheduler error."""


class SchedulerDecision(BaseModel):
    """调度决策结果。"""

    should_switch: bool = False
    target: str = ""
    reason: str = ""
    target_delay: int = 0
    current_delay: int = 0
    source: str = "rule"


__all__ = ["LLMCallback", "SchedulerDecision", "SchedulerError"]
