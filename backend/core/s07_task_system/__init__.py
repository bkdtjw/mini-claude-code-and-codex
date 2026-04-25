from __future__ import annotations

from .models import NotifyConfig, OutputConfig, ScheduledTask, TaskStoreData

__all__ = [
    "NotifyConfig",
    "OutputConfig",
    "ScheduledTask",
    "TaskExecutor",
    "TaskExecutorDeps",
    "TaskExecutionError",
    "TaskScheduler",
    "TaskStore",
    "TaskStoreData",
]


def __getattr__(name: str) -> object:
    if name == "TaskExecutor":
        from .executor import TaskExecutor

        return TaskExecutor
    if name == "TaskExecutorDeps":
        from .executor_models import TaskExecutorDeps

        return TaskExecutorDeps
    if name == "TaskExecutionError":
        from .executor_errors import TaskExecutionError

        return TaskExecutionError
    if name == "TaskScheduler":
        from .scheduler import TaskScheduler

        return TaskScheduler
    if name == "TaskStore":
        from .store import TaskStore

        return TaskStore
    raise AttributeError(name)
