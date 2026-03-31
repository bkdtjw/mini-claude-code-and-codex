from __future__ import annotations

from typing import Any

from .x_models import XPost
from .x_post_utils import normalize_text, safe_int


def extract_search_posts(
    response_data: dict[str, Any],
    limit: int,
) -> tuple[list[XPost], str | None]:
    instructions = (
        response_data.get("data", {})
        .get("search_by_raw_query", {})
        .get("search_timeline", {})
        .get("timeline", {})
        .get("instructions", [])
    )
    entries = _collect_entries(instructions)
    posts: list[XPost] = []
    next_cursor: str | None = None
    for entry in entries:
        entry_id = str(entry.get("entryId", ""))
        if entry_id.startswith("cursor-bottom"):
            next_cursor = str(entry.get("content", {}).get("value", "") or "") or None
            continue
        if not entry_id.startswith(("tweet", "search-grid")):
            continue
        post = _entry_to_post(entry)
        if post is None:
            continue
        posts.append(post)
        if len(posts) >= limit:
            break
    return posts, next_cursor


def _collect_entries(instructions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for instruction in instructions:
        instruction_entries = instruction.get("entries")
        if isinstance(instruction_entries, list):
            entries.extend(item for item in instruction_entries if isinstance(item, dict))
    return entries


def _entry_to_post(entry: dict[str, Any]) -> XPost | None:
    result = (
        entry.get("content", {})
        .get("itemContent", {})
        .get("tweet_results", {})
        .get("result", {})
    )
    if result.get("__typename") != "Tweet":
        return None
    user_result = result.get("core", {}).get("user_results", {}).get("result", {})
    user_core = user_result.get("core", {})
    user_legacy = user_result.get("legacy", {})
    tweet_legacy = result.get("legacy", {})
    author_handle = str(user_core.get("screen_name") or user_legacy.get("screen_name") or "")
    author_name = str(user_core.get("name") or user_legacy.get("name") or "")
    views = safe_int(result.get("views", {}).get("count"))
    tweet_id = str(result.get("rest_id") or tweet_legacy.get("id_str") or "")
    return XPost(
        author_name=author_name,
        author_handle=author_handle,
        text=normalize_text(tweet_legacy.get("full_text") or tweet_legacy.get("text") or ""),
        likes=safe_int(tweet_legacy.get("favorite_count")),
        retweets=safe_int(tweet_legacy.get("retweet_count")),
        replies=safe_int(tweet_legacy.get("reply_count")),
        views=views,
        created_at=str(tweet_legacy.get("created_at") or ""),
        url=(
            f"https://x.com/{author_handle}/status/{tweet_id}"
            if author_handle and tweet_id
            else ""
        ),
    )


__all__ = ["extract_search_posts"]
