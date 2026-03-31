from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .x_models import XPost


def build_query(query: str, days: int) -> str:
    since_date = (utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    return f"{query.strip()} since:{since_date}"


def collect_posts(page: Any, limit: int) -> list[XPost]:
    posts: list[XPost] = []
    for tweet in page:
        try:
            posts.append(tweet_to_post(tweet))
        except Exception:
            continue
        if len(posts) >= limit:
            break
    return posts


def tweet_to_post(tweet: Any) -> XPost:
    user = getattr(tweet, "user", None)
    handle = str(getattr(user, "screen_name", "") or "")
    author_name = str(getattr(user, "name", "") or "")
    return XPost(
        author_name=author_name,
        author_handle=handle,
        text=normalize_text(getattr(tweet, "text", "")),
        likes=safe_int(getattr(tweet, "favorite_count", 0)),
        retweets=safe_int(getattr(tweet, "retweet_count", 0)),
        replies=safe_int(getattr(tweet, "reply_count", 0)),
        views=safe_int(getattr(tweet, "view_count", 0)),
        created_at=str(getattr(tweet, "created_at", "") or ""),
        url=f"https://x.com/{handle}/status/{getattr(tweet, 'id', '')}" if handle else "",
    )


def normalize_text(text: Any) -> str:
    return " ".join(str(text or "").split())


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = ["build_query", "collect_posts", "normalize_text", "safe_int", "tweet_to_post", "utcnow"]
