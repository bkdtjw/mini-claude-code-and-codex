from __future__ import annotations

from pydantic import BaseModel, Field


class SubAgentTraceEvent(BaseModel):
    task_id: str
    status: str
    wave: int
    duration_ms: int = 0
    tool_call_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class SubAgentTrace(BaseModel):
    events: list[SubAgentTraceEvent] = Field(default_factory=list)

    def spawned(self, task_id: str, wave: int) -> None:
        self.events.append(SubAgentTraceEvent(task_id=task_id, status="spawned", wave=wave))

    def completed(
        self,
        task_id: str,
        wave: int,
        duration_ms: int,
        tool_call_count: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        self.events.append(
            SubAgentTraceEvent(
                task_id=task_id,
                status="completed",
                wave=wave,
                duration_ms=duration_ms,
                tool_call_count=tool_call_count,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        )

    def failed(self, task_id: str, wave: int, duration_ms: int) -> None:
        self.events.append(
            SubAgentTraceEvent(
                task_id=task_id,
                status="failed",
                wave=wave,
                duration_ms=duration_ms,
            )
        )


__all__ = ["SubAgentTrace", "SubAgentTraceEvent"]
