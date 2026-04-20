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


__all__ = [
    "LogEntryResponse",
    "LogSearchResponse",
    "MetricDetailResponse",
    "MetricsSummaryResponse",
    "MetricSeriesResponse",
    "TraceResponse",
]
