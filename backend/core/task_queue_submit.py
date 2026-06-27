from __future__ import annotations

from time import time
from typing import Any

from pydantic import BaseModel, Field

from backend.common.errors import AgentError
from backend.common.logging import get_log_context
from backend.core.task_queue_types import TaskPayload, TaskStatus


class CapacitySubmitError(AgentError):
    pass


class QueueSubmitSpec(BaseModel):
    task_id: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = 60.0
    max_retries: int = 1


class CapacitySubmitRequest(BaseModel):
    specs: list[QueueSubmitSpec] = Field(default_factory=list)
    max_active: int = Field(ge=1)


def build_payload(namespace: str, spec: QueueSubmitSpec) -> TaskPayload:
    payload_input = _with_log_context(spec.input_data)
    return TaskPayload(
        task_id=spec.task_id,
        namespace=namespace,
        input_data=payload_input,
        parent_task_id=str(payload_input.get("parent_task_id", "")),
        created_at=time(),
        timeout_seconds=spec.timeout_seconds,
        max_retries=spec.max_retries,
    )


def parent_id(payloads: list[TaskPayload]) -> str:
    if not payloads:
        return ""
    ids = {payload.parent_task_id for payload in payloads}
    if len(ids) != 1:
        raise CapacitySubmitError(
            "TASK_QUEUE_CAPACITY_PARENT_MISMATCH",
            "capacity batch must share one parent_task_id",
        )
    return payloads[0].parent_task_id


def enforce_capacity(
    payloads: list[TaskPayload],
    existing: list[TaskPayload],
    max_active: int,
) -> None:
    active = sum(
        1 for item in existing if item.status in {TaskStatus.PENDING, TaskStatus.RUNNING}
    )
    if active + len(payloads) > max_active:
        raise CapacitySubmitError(
            "TASK_QUEUE_CAPACITY_EXCEEDED",
            f"active={active}, requested={len(payloads)}, max_active={max_active}",
        )


async def fail_saved_payloads(
    persistence: Any,
    payloads: list[TaskPayload],
    error: str,
) -> None:
    try:
        for payload in payloads:
            await persistence.fail(payload.task_id, error)
    except Exception as exc:  # noqa: BLE001
        raise CapacitySubmitError("TASK_QUEUE_CAPACITY_COMPENSATE_ERROR", str(exc)) from exc


def _with_log_context(input_data: dict[str, Any]) -> dict[str, Any]:
    payload_input = dict(input_data)
    context = get_log_context()
    trace_id = str(payload_input.get("trace_id") or context.get("trace_id") or "")
    if trace_id:
        payload_input["trace_id"] = trace_id
    return payload_input


__all__ = [
    "CapacitySubmitError",
    "CapacitySubmitRequest",
    "QueueSubmitSpec",
    "build_payload",
    "enforce_capacity",
    "fail_saved_payloads",
    "parent_id",
]
