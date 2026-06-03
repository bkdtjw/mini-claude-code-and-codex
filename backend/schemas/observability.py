from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetricSeriesResponse(BaseModel):
    total: int = 0
    daily: dict[str, int] = Field(default_factory=dict)


class MetricsSummaryResponse(BaseModel):
    period_days: int
    metrics: dict[str, MetricSeriesResponse] = Field(default_factory=dict)


class MetricDetailResponse(BaseModel):
    name: str
    total: int = 0
    daily: dict[str, int] = Field(default_factory=dict)


class LatencyStatResponse(BaseModel):
    name: str
    count: int = 0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    max_ms: float = 0.0


class LatencySummaryResponse(BaseModel):
    latencies: dict[str, LatencyStatResponse] = Field(default_factory=dict)


class LogEntryResponse(BaseModel):
    timestamp: str
    level: str
    event: str
    trace_id: str = ""
    session_id: str = ""
    worker_id: str = ""
    component: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class LogSearchResponse(BaseModel):
    count: int = 0
    logs: list[LogEntryResponse] = Field(default_factory=list)


class TraceResponse(BaseModel):
    trace_id: str
    events: list[LogEntryResponse] = Field(default_factory=list)


class TraceSpanResponse(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str = ""
    name: str
    status: str = "success"
    start_time: str = ""
    end_time: str = ""
    duration_ms: int = 0
    component: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceSpansResponse(BaseModel):
    trace_id: str
    spans: list[TraceSpanResponse] = Field(default_factory=list)


__all__ = [
    "LatencyStatResponse",
    "LatencySummaryResponse",
    "LogEntryResponse",
    "LogSearchResponse",
    "MetricDetailResponse",
    "MetricsSummaryResponse",
    "MetricSeriesResponse",
    "TraceResponse",
    "TraceSpanResponse",
    "TraceSpansResponse",
]
