from __future__ import annotations

import json
from typing import Any

from backend.core.task_queue_types import TaskPayload, TaskStatus
from backend.storage.models import SubAgentTaskRecord


def to_record(payload: TaskPayload) -> SubAgentTaskRecord:
    return SubAgentTaskRecord(
        id=payload.task_id,
        namespace=payload.namespace,
        parent_task_id=payload.parent_task_id,
        input_json=json.dumps(payload.input_data, ensure_ascii=False),
        status=payload.status.value,
        worker_id=payload.worker_id,
        created_at=payload.created_at,
        started_at=payload.started_at,
        timeout_seconds=payload.timeout_seconds,
        lease_expires_at=payload.lease_expires_at,
        result_json=dump_optional(payload.result),
        error=payload.error,
        retry_count=payload.retry_count,
        max_retries=payload.max_retries,
    )


def apply_payload(row: SubAgentTaskRecord, payload: TaskPayload) -> None:
    updated = to_record(payload)
    for key in (
        "namespace",
        "parent_task_id",
        "input_json",
        "status",
        "worker_id",
        "created_at",
        "started_at",
        "timeout_seconds",
        "lease_expires_at",
        "result_json",
        "error",
        "retry_count",
        "max_retries",
    ):
        setattr(row, key, getattr(updated, key))


def to_payload(row: SubAgentTaskRecord) -> TaskPayload:
    return TaskPayload(
        task_id=row.id,
        namespace=row.namespace,
        input_data=json_dict(row.input_json),
        parent_task_id=row.parent_task_id,
        status=TaskStatus(row.status),
        worker_id=row.worker_id,
        created_at=row.created_at,
        started_at=row.started_at,
        timeout_seconds=row.timeout_seconds,
        lease_expires_at=row.lease_expires_at,
        result=json_dict(row.result_json) if row.result_json else None,
        error=row.error,
        retry_count=row.retry_count,
        max_retries=row.max_retries,
    )


def dump_optional(value: dict[str, Any] | None) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


def json_dict(raw: str | None) -> dict[str, Any]:
    value = json.loads(raw or "{}")
    return value if isinstance(value, dict) else {}


__all__ = ["apply_payload", "to_payload", "to_record"]
