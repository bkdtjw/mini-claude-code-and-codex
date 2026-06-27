from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from backend.common.logging import get_logger
from backend.common.metrics import record_latency_sample
from backend.common.prometheus_metrics import observe_sub_agent_task
from backend.core.task_queue import TaskPayload, TaskQueue

from . import task_queue_consumer_helpers as helpers

logger = get_logger(component="sub_agent_consumer")


@dataclass
class AgentFailureReport:
    payload: TaskPayload
    queue: TaskQueue
    error: str
    started_at: float
    exc: Exception | None = None


async def fail_agent_payload(report: AgentFailureReport) -> None:
    try:
        duration_seconds = monotonic() - report.started_at
        observe_sub_agent_task("error", duration_seconds)
        await record_latency_sample("sub_agent_task", int(duration_seconds * 1000))
        await helpers._safe_fail(
            report.queue,
            report.payload.task_id,
            report.error,
            report.payload.worker_id,
        )
        _log_failure(report, duration_seconds)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"record sub-agent failure failed: {exc}") from exc


def _log_failure(report: AgentFailureReport, duration_seconds: float) -> None:
    payload = {
        "task_id": report.payload.task_id,
        "worker_id": report.payload.worker_id,
        "error": report.error,
        "duration_ms": int(duration_seconds * 1000),
    }
    if report.exc is None:
        logger.error("sub_agent_task_failed", **payload)
    else:
        logger.exception("sub_agent_task_failed", **payload)


__all__ = ["AgentFailureReport", "fail_agent_payload"]
