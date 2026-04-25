from __future__ import annotations

from backend.common.errors import AgentError


class TaskExecutionError(AgentError):
    def __init__(self, message: str, output: str = "") -> None:
        self.output = output
        super().__init__("TASK_EXECUTION_FAILED", message)


__all__ = ["TaskExecutionError"]
