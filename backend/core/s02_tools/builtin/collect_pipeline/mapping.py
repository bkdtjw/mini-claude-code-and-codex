from __future__ import annotations

from typing import Any

from .models import CollectAndProcessPipelineError, RawTweet, RawVideo


def map_x_post(post: Any) -> RawTweet:
    try:
        handle = _clean_text(_read_value(post, "author_handle", "screen_name", "username"))
        name = _clean_text(_read_value(post, "author_name", "name"))
        author = _clean_text(_read_value(post, "author")) or _format_author(handle, name)
        return RawTweet(
            author=author,
            text=_clean_text(_read_value(post, "text")),
            likes=_to_int(_read_value(post, "likes", "favorite_count")),
            retweets=_to_int(_read_value(post, "retweets", "retweet_count")),
            replies=_to_int(_read_value(post, "replies", "reply_count")),
            views=_to_int(_read_value(post, "views", "view_count")),
            created_at=_clean_text(_read_value(post, "created_at")),
            url=_clean_text(_read_value(post, "url")),
        )
    except Exception as exc:  # noqa: BLE001
        raise CollectAndProcessPipelineError(f"X post mapping failed: {exc}") from exc


def map_video(video: Any) -> RawVideo:
    try:
        return RawVideo(
            title=_clean_text(_read_value(video, "title")),
            url=_clean_text(_read_value(video, "url")),
            channel=_clean_text(_read_value(video, "channel")),
            view_count=_to_int(_read_value(video, "view_count", "views")),
            upload_date=_clean_text(_read_value(video, "upload_date", "published_at")),
            subtitle_text=_clean_text(_read_value(video, "subtitle_text", "subtitle")),
        )
    except Exception as exc:  # noqa: BLE001
        raise CollectAndProcessPipelineError(f"YouTube video mapping failed: {exc}") from exc


def _read_value(source: Any, *names: str) -> Any:
    if isinstance(source, dict):
        for name in names:
            if name in source:
                return source[name]
        return None
    for name in names:
        value = getattr(source, name, None)
        if value is not None:
            return value
    return None


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _to_int(value: Any) -> int:
    try:
        return int(str(value or 0).replace(",", ""))
    except (TypeError, ValueError):
        return 0


def _format_author(handle: str, name: str) -> str:
    if handle and name:
        return f"@{handle.lstrip('@')} ({name})"
    if handle:
        return f"@{handle.lstrip('@')}"
    return name


__all__ = ["map_video", "map_x_post"]
