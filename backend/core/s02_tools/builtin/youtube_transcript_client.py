from __future__ import annotations

import re
from typing import Any

import youtube_transcript_api as transcript_api  # type: ignore[import-not-found, import-untyped]

try:
    from youtube_transcript_api.proxies import GenericProxyConfig  # type: ignore[import-not-found, import-untyped]
except Exception:  # pragma: no cover - compatibility fallback
    GenericProxyConfig = None


class _FallbackTranscriptError(Exception):
    """鍏煎缂哄け寮傚父绫诲瀷鏃剁殑鍥為€€寮傚父銆?"""


LANGUAGE_PRIORITY: tuple[str, ...] = ("zh-Hans", "zh", "en")
SUBTITLE_CHAR_LIMIT = 3000
YouTubeTranscriptApi = transcript_api.YouTubeTranscriptApi


def _resolve_exception_type(candidate: Any) -> type[BaseException]:
    if isinstance(candidate, type) and issubclass(candidate, BaseException):
        return candidate
    return _FallbackTranscriptError


_TRANSCRIPT_ERRORS = tuple(
    _resolve_exception_type(getattr(transcript_api, name, _FallbackTranscriptError))
    for name in (
        "TranscriptsDisabled",
        "NoTranscriptFound",
        "CouldNotRetrieveTranscript",
        "IpBlocked",
        "RequestBlocked",
    )
)


def fetch_subtitle_sync(video_id: str, proxy_url: str = "") -> str:
    client = _create_transcript_client(proxy_url)
    transcript = _load_transcript(client, video_id, LANGUAGE_PRIORITY)
    if not transcript:
        transcript = _load_transcript(client, video_id, None)
    return _normalize_subtitle_text(transcript)


def _create_transcript_client(proxy_url: str) -> Any:
    normalized_proxy = proxy_url.strip()
    if not normalized_proxy or GenericProxyConfig is None:
        return YouTubeTranscriptApi()
    try:
        return YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(
                http_url=normalized_proxy,
                https_url=normalized_proxy,
            )
        )
    except TypeError:
        return YouTubeTranscriptApi()


def _load_transcript(client: Any, video_id: str, languages: tuple[str, ...] | None) -> list[Any]:
    try:
        return list(_fetch_transcript(client, video_id, languages))
    except _TRANSCRIPT_ERRORS:
        return []
    except Exception:
        return []


def _fetch_transcript(client: Any, video_id: str, languages: tuple[str, ...] | None) -> Any:
    if hasattr(client, "fetch"):
        if languages is None:
            return client.fetch(video_id)
        return client.fetch(video_id, languages=languages)
    if languages is None:
        return YouTubeTranscriptApi.get_transcript(video_id)
    return YouTubeTranscriptApi.get_transcript(video_id, languages=list(languages))


def _extract_text(snippet: Any) -> str:
    if isinstance(snippet, dict):
        return str(snippet.get("text") or "")
    return str(getattr(snippet, "text", "") or "")


def _normalize_subtitle_text(items: list[Any]) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for item in items:
        text = re.sub(r"\s+", " ", _extract_text(item)).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        lines.append(text)
    subtitle = " ".join(lines).strip()
    if len(subtitle) <= SUBTITLE_CHAR_LIMIT:
        return subtitle
    return f"{subtitle[:SUBTITLE_CHAR_LIMIT].rstrip()}..."


__all__ = ["fetch_subtitle_sync"]
