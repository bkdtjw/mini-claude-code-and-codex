from __future__ import annotations

import math
import os
from collections import deque
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest, multiprocess

_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
_WINDOW_SIZE = 1000
_LATENCY_NAMES = {
    "http": "HTTP 请求",
    "agent_run": "Agent 执行",
    "llm_request": "LLM 请求",
    "tool_call": "工具调用",
    "sub_agent_task": "子 Agent",
}
_latencies: dict[str, deque[float]] = {key: deque(maxlen=_WINDOW_SIZE) for key in _LATENCY_NAMES}

business_events_total = Counter(
    "agent_studio_business_events_total",
    "Legacy business counters mirrored from the Redis daily metrics collector.",
    ("metric",),
)
http_requests_total = Counter(
    "agent_studio_http_requests_total",
    "HTTP requests handled by the API.",
    ("method", "path", "status"),
)
http_request_duration_seconds = Histogram(
    "agent_studio_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "path", "status"),
    buckets=_BUCKETS,
)
agent_runs_total = Counter(
    "agent_studio_agent_runs_total",
    "Agent loop runs.",
    ("status",),
)
agent_run_duration_seconds = Histogram(
    "agent_studio_agent_run_duration_seconds",
    "Agent loop run duration in seconds.",
    ("status",),
    buckets=_BUCKETS,
)
llm_requests_total = Counter(
    "agent_studio_llm_requests_total",
    "LLM requests by provider, model, request type and status.",
    ("provider", "model", "request_type", "status", "error_code"),
)
llm_request_duration_seconds = Histogram(
    "agent_studio_llm_request_duration_seconds",
    "LLM request duration in seconds.",
    ("provider", "model", "request_type", "status"),
    buckets=_BUCKETS,
)
llm_tokens_total = Counter(
    "agent_studio_llm_tokens_total",
    "LLM token usage.",
    ("provider", "model", "kind"),
)
tool_calls_total = Counter(
    "agent_studio_tool_calls_total",
    "Tool calls by tool and status.",
    ("tool", "status"),
)
tool_call_duration_seconds = Histogram(
    "agent_studio_tool_call_duration_seconds",
    "Tool call duration in seconds.",
    ("tool", "status"),
    buckets=_BUCKETS,
)
sub_agent_tasks_total = Counter(
    "agent_studio_sub_agent_tasks_total",
    "Sub-agent task executions.",
    ("status",),
)
sub_agent_task_duration_seconds = Histogram(
    "agent_studio_sub_agent_task_duration_seconds",
    "Sub-agent task duration in seconds.",
    ("status",),
    buckets=_BUCKETS,
)


def render_prometheus_metrics() -> bytes:
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry)
    return generate_latest()


def record_business_metric(metric: str, value: int = 1) -> None:
    if value > 0:
        business_events_total.labels(metric=metric).inc(value)


def observe_http_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    status = str(status_code)
    http_requests_total.labels(method=method, path=path, status=status).inc()
    http_request_duration_seconds.labels(method=method, path=path, status=status).observe(duration_seconds)
    _record_latency("http", duration_seconds)


def observe_agent_run(status: str, duration_seconds: float) -> None:
    agent_runs_total.labels(status=status).inc()
    agent_run_duration_seconds.labels(status=status).observe(duration_seconds)
    _record_latency("agent_run", duration_seconds)


def observe_llm_request(
    provider: str,
    model: str,
    request_type: str,
    status: str,
    duration_seconds: float,
    *,
    error_code: str = "",
    tokens: dict[str, int] | None = None,
) -> None:
    llm_requests_total.labels(
        provider=provider,
        model=model,
        request_type=request_type,
        status=status,
        error_code=error_code,
    ).inc()
    llm_request_duration_seconds.labels(
        provider=provider,
        model=model,
        request_type=request_type,
        status=status,
    ).observe(duration_seconds)
    for kind, value in (tokens or {}).items():
        if value > 0:
            llm_tokens_total.labels(provider=provider, model=model, kind=kind).inc(value)
    _record_latency("llm_request", duration_seconds)


def observe_tool_call(tool: str, status: str, duration_seconds: float) -> None:
    tool_calls_total.labels(tool=tool, status=status).inc()
    tool_call_duration_seconds.labels(tool=tool, status=status).observe(duration_seconds)
    _record_latency("tool_call", duration_seconds)


def observe_sub_agent_task(status: str, duration_seconds: float) -> None:
    sub_agent_tasks_total.labels(status=status).inc()
    sub_agent_task_duration_seconds.labels(status=status).observe(duration_seconds)
    _record_latency("sub_agent_task", duration_seconds)


def latency_snapshot() -> dict[str, dict[str, Any]]:
    return {key: _stats_for(key, values) for key, values in _latencies.items()}


def _record_latency(key: str, duration_seconds: float) -> None:
    if duration_seconds >= 0 and key in _latencies:
        _latencies[key].append(duration_seconds * 1000)


def _stats_for(key: str, values: deque[float]) -> dict[str, Any]:
    items = sorted(values)
    return {
        "name": _LATENCY_NAMES[key],
        "count": len(items),
        "p50_ms": _percentile(items, 50),
        "p95_ms": _percentile(items, 95),
        "max_ms": round(items[-1], 2) if items else 0.0,
    }


def _percentile(items: list[float], percentile: int) -> float:
    if not items:
        return 0.0
    index = max(math.ceil((percentile / 100) * len(items)) - 1, 0)
    return round(items[index], 2)


def reset_latency_for_tests() -> None:
    for values in _latencies.values():
        values.clear()


__all__ = [
    "CONTENT_TYPE_LATEST",
    "latency_snapshot",
    "observe_agent_run",
    "observe_http_request",
    "observe_llm_request",
    "observe_sub_agent_task",
    "observe_tool_call",
    "record_business_metric",
    "render_prometheus_metrics",
    "reset_latency_for_tests",
]
