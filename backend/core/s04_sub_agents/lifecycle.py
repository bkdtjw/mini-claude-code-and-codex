from __future__ import annotations

import asyncio

from backend.common.types import ToolResult

from .spawner import SpawnParams, SubAgentSpawner


class SubAgentLifecycle:
    """Track sub-agent execution lifecycle and timeouts."""

    def __init__(self, timeout: float = 120.0) -> None:
        self._timeout = timeout
        self._active_tasks: set[asyncio.Task[ToolResult]] = set()

    async def run_with_timeout(self, spawner: SubAgentSpawner, params: SpawnParams) -> ToolResult:
        try:
            task = asyncio.create_task(spawner.spawn_and_run(params))
            self._active_tasks.add(task)
            try:
                return await asyncio.wait_for(task, timeout=self._timeout)
            except asyncio.TimeoutError:
                task.cancel()
                return ToolResult(output=f"Sub-agent timed out after {self._timeout:.0f}s", is_error=True)
            finally:
                self._active_tasks.discard(task)
        except Exception as exc:
            return ToolResult(output=str(exc), is_error=True)

    @property
    def active_count(self) -> int:
        return len({task for task in self._active_tasks if not task.done()})


__all__ = ["SubAgentLifecycle"]
