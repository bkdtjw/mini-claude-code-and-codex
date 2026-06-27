from __future__ import annotations

from pydantic import BaseModel

from backend.core.s07_task_system.event_hooks import HookSummary, TimelineEntry


class HookListResponse(BaseModel):
    hooks: list[HookSummary]


class HookLogResponse(BaseModel):
    entries: list[TimelineEntry]


class HookOkResponse(BaseModel):
    ok: bool


__all__ = ["HookListResponse", "HookLogResponse", "HookOkResponse"]
