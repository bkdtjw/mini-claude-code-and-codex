from __future__ import annotations

from pydantic import BaseModel

from backend.core.s02_tools.builtin.x_client import XPost


class XPostOut(BaseModel):
    author_name: str
    author_handle: str
    text: str
    likes: int
    retweets: int
    replies: int
    views: int
    created_at: str
    url: str

    @classmethod
    def from_post(cls, post: XPost) -> XPostOut:
        return cls(**post.model_dump())


class XSearchResponse(BaseModel):
    query: str
    count: int
    rate_limited: bool = False
    retry_after: int | None = None
    cached: bool = False
    results: list[XPostOut]


class XCompareItem(BaseModel):
    query: str
    count: int
    total_engagement: int  # 原始互动总量（声量）
    weighted_score: float  # 热度加权分
    unavailable: bool = False  # 该词本轮未取到（限流/额度/上游故障）
    top_post: XPostOut | None = None  # 该词最火一条


class XCompareResponse(BaseModel):
    days: int
    items: list[XCompareItem]


__all__ = ["XCompareItem", "XCompareResponse", "XPostOut", "XSearchResponse"]
