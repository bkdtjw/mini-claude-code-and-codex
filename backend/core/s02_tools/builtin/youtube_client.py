from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from backend.config.http_client import load_http_client_config

from .youtube_transcript_client import fetch_subtitle_sync

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeClientError(Exception):
    """YouTube client error."""


@dataclass(slots=True)
class YouTubeVideo:
    title: str
    url: str
    channel: str
    view_count: int
    upload_date: str
    duration_seconds: int
    subtitle_text: str


@dataclass(slots=True)
class YouTubeSearchRequest:
    query: str
    api_key: str
    max_results: int = 5
    days: int = 0
    proxy_url: str = ""


async def search_videos(request: YouTubeSearchRequest) -> list[YouTubeVideo]:
    try:
        if not request.api_key.strip():
            raise YouTubeClientError("缺少 YouTube API key，请检查 YOUTUBE_API_KEY 配置")
        async with httpx.AsyncClient(
            timeout=15.0,
            proxy=request.proxy_url or None,
            trust_env=load_http_client_config().trust_env,
        ) as client:
            search_payload = await _request_json(
                client,
                SEARCH_URL,
                _build_search_params(request),
            )
            video_ids = _extract_video_ids(search_payload)
            if not video_ids:
                return []
            videos_payload = await _request_json(
                client,
                VIDEOS_URL,
                {
                    "part": "snippet,statistics,contentDetails",
                    "id": ",".join(video_ids),
                    "key": request.api_key,
                },
            )
        return _build_videos(search_payload, videos_payload)
    except YouTubeClientError:
        raise
    except httpx.HTTPStatusError as exc:
        raise YouTubeClientError(_translate_http_error(exc)) from exc
    except httpx.HTTPError as exc:
        proxy_hint = request.proxy_url or "direct"
        raise YouTubeClientError(
            f"YouTube 搜索失败：网络请求失败，[{exc.__class__.__name__}] {exc}（proxy={proxy_hint}）"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise YouTubeClientError(f"YouTube 搜索失败：{exc}") from exc


async def fetch_subtitle(video_id: str, proxy_url: str = "") -> str:
    try:
        return await asyncio.to_thread(fetch_subtitle_sync, video_id, proxy_url)
    except Exception:
        return ""


async def _request_json(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, str | int],
) -> dict[str, Any]:
    response = await client.get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _published_after(days: int) -> str:
    return (_utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_search_params(request: YouTubeSearchRequest) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "part": "snippet",
        "q": request.query,
        "type": "video",
        "maxResults": request.max_results,
        "order": "relevance",
        "key": request.api_key,
    }
    if request.days > 0:
        params["publishedAfter"] = _published_after(request.days)
    return params


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _extract_video_ids(payload: dict[str, Any]) -> list[str]:
    return [
        str(item.get("id", {}).get("videoId") or "")
        for item in payload.get("items") or []
        if isinstance(item, dict) and item.get("id", {}).get("videoId")
    ]


def _build_videos(
    search_payload: dict[str, Any],
    videos_payload: dict[str, Any],
) -> list[YouTubeVideo]:
    details = {
        str(item.get("id") or ""): item
        for item in videos_payload.get("items") or []
        if isinstance(item, dict)
    }
    videos: list[YouTubeVideo] = []
    for item in search_payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        video_id = str(item.get("id", {}).get("videoId") or "")
        if not video_id:
            continue
        snippet = item.get("snippet") or {}
        detail = details.get(video_id, {})
        detail_snippet = detail.get("snippet") or {}
        videos.append(
            YouTubeVideo(
                title=str(detail_snippet.get("title") or snippet.get("title") or "未命名视频"),
                url=f"https://www.youtube.com/watch?v={video_id}",
                channel=str(detail_snippet.get("channelTitle") or snippet.get("channelTitle") or "未知频道"),
                view_count=int(detail.get("statistics", {}).get("viewCount") or 0),
                upload_date=_format_upload_date(
                    str(detail_snippet.get("publishedAt") or snippet.get("publishedAt") or "")
                ),
                duration_seconds=_parse_duration(
                    str(detail.get("contentDetails", {}).get("duration") or "")
                ),
                subtitle_text="",
            )
        )
    return videos


def _translate_http_error(exc: httpx.HTTPStatusError) -> str:
    status_code = exc.response.status_code if exc.response is not None else 0
    if status_code in {400, 401, 403}:
        return "YouTube API key 无效或配额已用尽，请检查 YOUTUBE_API_KEY 配置"
    return f"YouTube 搜索失败：HTTP {status_code}"


def _format_upload_date(published_at: str) -> str:
    return published_at.split("T", maxsplit=1)[0] if "T" in published_at else published_at


def _parse_duration(iso_duration: str) -> int:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if match is None:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


__all__ = ["YouTubeClientError", "YouTubeSearchRequest", "YouTubeVideo", "fetch_subtitle", "search_videos"]
