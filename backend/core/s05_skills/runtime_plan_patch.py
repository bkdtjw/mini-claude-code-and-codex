from __future__ import annotations

from backend.common.types import AgentEventHandler
from backend.core.s01_agent_loop import AgentLoop, PlanExecuteRunner

from .models import AgentSpec


def patch_plan_runner(
    runner: PlanExecuteRunner,
    spec: AgentSpec | None,
    event_handler: AgentEventHandler | None,
) -> None:
    original_loop = runner._build_step_loop  # noqa: SLF001

    def build_step_loop(todo_step: object, context: object) -> AgentLoop:
        loop = original_loop(todo_step, context)
        if spec is not None:
            loop._config.max_iterations = spec.max_iterations  # noqa: SLF001
            loop._config.timeout_seconds = spec.timeout_seconds  # noqa: SLF001
        if event_handler is not None:
            loop.on(event_handler)
        return loop

    runner._build_step_loop = build_step_loop  # noqa: SLF001


__all__ = ["patch_plan_runner"]
