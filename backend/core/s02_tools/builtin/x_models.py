from __future__ import annotations

from pydantic import BaseModel, Field


class XClientConfig(BaseModel):
    username: str = ""
    email: str = ""
    password: str
    proxy_url: str = ""
    cookies_file: str = "twitter_cookies.json"


class XSearchOptions(BaseModel):
    max_results: int = Field(default=20, ge=1, le=50)
    days: int = Field(default=30, ge=1, le=365)
    search_type: str = "Latest"


class XPost(BaseModel):
    author_name: str
    author_handle: str
    text: str
    likes: int
    retweets: int
    replies: int
    views: int
    created_at: str
    url: str


__all__ = ["XClientConfig", "XPost", "XSearchOptions"]
