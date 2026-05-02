from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CollectAndProcessPipelineError(Exception):
    """Collect-and-process pipeline error."""


class RawTweet(BaseModel):
    author: str = ""
    text: str = ""
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    views: int = 0
    created_at: str = ""
    url: str = ""


class RawVideo(BaseModel):
    title: str = ""
    url: str = ""
    channel: str = ""
    view_count: int = 0
    upload_date: str = ""
    subtitle_text: str = ""


class TaskMemory(BaseModel):
    task_id: str
    reported_ids: list[str] = Field(default_factory=list)
    reported_signatures: list[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    evidence_text: str
    stats: dict[str, Any] = Field(default_factory=dict)


class TweetCandidate(BaseModel):
    author: str
    text: str
    likes: int
    retweets: int
    replies: int
    views: int
    created_at: str
    url: str
    keyword_hits: list[str] = Field(default_factory=list)
    tokens: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    created_dt: datetime | None = None
    hours_ago: float = 999.0
    penalties: dict[str, float] = Field(default_factory=dict)
    score_parts: dict[str, float] = Field(default_factory=dict)
    engagement_raw: float = 0
    engagement_percentile: float = 0
    score: float = 0


class TweetCluster(BaseModel):
    cluster_id: str
    signature: str
    items: list[TweetCandidate] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    keyword_hits: list[str] = Field(default_factory=list)
    score: float = 0


__all__ = [
    "CollectAndProcessPipelineError",
    "PipelineResult",
    "RawTweet",
    "RawVideo",
    "TaskMemory",
    "TweetCandidate",
    "TweetCluster",
]
