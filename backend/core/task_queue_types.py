from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskPayload(BaseModel):
    task_id: str
    namespace: str
    input_data: dict[str, Any]
    parent_task_id: str = ""
    status: TaskStatus = TaskStatus.PENDING
    worker_id: str = ""
    created_at: float
    started_at: float = 0.0
    timeout_seconds: float = 60.0
    lease_expires_at: float = 0.0
    result: dict[str, Any] | None = None
    error: str = ""
    retry_count: int = 0
    max_retries: int = 1


__all__ = ["TaskPayload", "TaskStatus"]
