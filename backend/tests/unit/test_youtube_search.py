from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.tests.unit.youtube_test_support import (
    FakeHttpResponse,
    FakeIpBlocked,
    FakeSnippet,
    FakeTranscriptApi,
    FakeTranscriptError,
    install_http_client,
    load_modules,
)

FAKE_SEARCH_RESPONSE = {
    "items": [
        {
            "id": {"videoId": "abc123"},
            "snippet": {
                "title": "Test Video About Claude Code",
                "channelTitle": "TechChannel",
                "publishedAt": "2026-03-20T10:00:00Z",
            },
        },
        {
            "id": {"videoId": "def456"},
            "snippet": {
                "title": "AI Coding Tools Comparison",
                "channelTitle": "DevReview",
                "publishedAt": "2026-03-15T08:30:00Z",
            },
        },
    ]
}
FAKE_VIDEOS_RESPONSE = {
    "items": [
        {
            "id": "abc123",
            "snippet": {
                "title": "Test Video About Claude Code",
                "channelTitle": "TechChannel",
                "publishedAt": "2026-03-20T10:00:00Z",
            },
            "statistics": {"viewCount": "12345"},
            "contentDetails": {"duration": "PT15M30S"},
        },
        {
            "id": "def456",
            "snippet": {
                "title": "AI Coding Tools Comparison",
                "channelTitle": "DevReview",
                "publishedAt": "2026-03-15T08:30:00Z",
            },
            "statistics": {"viewCount": "8901"},
            "contentDetails": {"duration": "PT22M15S"},
        },
    ]
}
FAKE_TRANSCRIPT = [
    {"text": "Hello everyone", "start": 0.0, "duration": 2.5},
    {"text": "Today we talk about Claude Code", "start": 2.5, "duration": 3.0},
    {"text": "Let's get started", "start": 5.5, "duration": 2.0},
]
FAKE_TRANSCRIPT_OBJECTS = [
    FakeSnippet("Hello everyone", 0.0, 2.5),
    FakeSnippet("Today we talk about Claude Code", 2.5, 3.0),
    FakeSnippet("Let us get started", 5.5, 2.0),
]


def _responses(search_status: int = 200) -> dict[str, FakeHttpResponse]:
    return {
        "/search": FakeHttpResponse(search_status, FAKE_SEARCH_RESPONSE, "https://example.com/search"),
        "/videos": FakeHttpResponse(200, FAKE_VIDEOS_RESPONSE, "https://example.com/videos"),
    }


@pytest.mark.asyncio
async def test_search_returns_formatted_results(monkeypatch: pytest.MonkeyPatch) -> None:
    youtube_client, youtube_search = load_modules(monkeypatch)
    client = install_http_client(monkeypatch, youtube_client, _responses())
    tool, execute = youtube_search.create_youtube_search_tool(api_key="test-key")
    result = await execute({"query": "Claude Code", "max_results": 2, "with_subtitles": False})
    assert result.is_error is False and tool.name == "youtube_search"
    assert "Test Video About Claude Code" in result.output and "TechChannel" in result.output
    assert "12,345" in result.output and "不限日期" in result.output
    assert "publishedAfter" not in client.calls[0]["params"]


@pytest.mark.asyncio
async def test_search_rejects_empty_query(monkeypatch: pytest.MonkeyPatch) -> None:
    _, youtube_search = load_modules(monkeypatch)
    _, execute = youtube_search.create_youtube_search_tool(api_key="test-key")
    result = await execute({"query": "   "})
    assert result.is_error is True and "搜索关键词不能为空" in result.output


@pytest.mark.asyncio
async def test_search_filters_by_days(monkeypatch: pytest.MonkeyPatch) -> None:
    youtube_client, _ = load_modules(monkeypatch)
    client = install_http_client(monkeypatch, youtube_client, _responses())
    monkeypatch.setattr(youtube_client, "_utcnow", lambda: datetime(2026, 3, 31, 0, 0, tzinfo=UTC))
    await youtube_client.search_videos(
        youtube_client.YouTubeSearchRequest(
            query="Claude Code",
            api_key="test-key",
            max_results=2,
            days=30,
        )
    )
    assert client.calls[0]["params"]["publishedAfter"] == "2026-03-01T00:00:00Z"


@pytest.mark.asyncio
async def test_search_uses_proxy_for_api_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    youtube_client, _ = load_modules(monkeypatch)
    client = install_http_client(monkeypatch, youtube_client, _responses())
    await youtube_client.search_videos(
        youtube_client.YouTubeSearchRequest(
            query="Claude Code",
            api_key="test-key",
            proxy_url="http://127.0.0.1:7892",
        )
    )
    assert client.init_kwargs["proxy"] == "http://127.0.0.1:7892"


@pytest.mark.asyncio
async def test_subtitle_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    youtube_client, youtube_search = load_modules(monkeypatch)
    install_http_client(monkeypatch, youtube_client, _responses())
    FakeTranscriptApi.responses = {("abc123", ("zh-Hans", "zh", "en")): FAKE_TRANSCRIPT}
    _, execute = youtube_search.create_youtube_search_tool(api_key="test-key")
    result = await execute({"query": "Claude Code", "max_results": 2, "with_subtitles": True})
    assert result.is_error is False and "Today we talk about Claude Code" in result.output


@pytest.mark.asyncio
async def test_subtitle_with_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    youtube_client, youtube_search = load_modules(monkeypatch)
    install_http_client(monkeypatch, youtube_client, _responses())
    FakeTranscriptApi.responses = {("abc123", ("zh-Hans", "zh", "en")): FAKE_TRANSCRIPT}
    _, execute = youtube_search.create_youtube_search_tool(api_key="test-key", proxy_url="http://127.0.0.1:7892")
    result = await execute({"query": "Claude Code", "max_results": 1, "with_subtitles": True})
    assert result.is_error is False and FakeTranscriptApi.instances
    assert all(instance.proxy_config is not None for instance in FakeTranscriptApi.instances)
    assert FakeTranscriptApi.instances[0].proxy_config.http_url == "http://127.0.0.1:7892"


@pytest.mark.asyncio
async def test_subtitle_without_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    youtube_client, _ = load_modules(monkeypatch)
    FakeTranscriptApi.responses = {("abc123", ("zh-Hans", "zh", "en")): FAKE_TRANSCRIPT}
    result = await youtube_client.fetch_subtitle("abc123")
    assert "Today we talk about Claude Code" in result and FakeTranscriptApi.instances
    assert FakeTranscriptApi.instances[0].proxy_config is None


@pytest.mark.asyncio
async def test_subtitle_handles_object_format(monkeypatch: pytest.MonkeyPatch) -> None:
    youtube_client, _ = load_modules(monkeypatch)
    FakeTranscriptApi.responses = {("abc123", ("zh-Hans", "zh", "en")): FAKE_TRANSCRIPT_OBJECTS}
    result = await youtube_client.fetch_subtitle("abc123", proxy_url="http://127.0.0.1:7892")
    assert "Hello everyone" in result and "Let us get started" in result


@pytest.mark.asyncio
async def test_subtitle_ipblocked_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    youtube_client, _ = load_modules(monkeypatch)
    FakeTranscriptApi.responses = {
        ("abc123", ("zh-Hans", "zh", "en")): FakeIpBlocked("blocked"),
        ("abc123", None): FakeIpBlocked("blocked"),
    }
    assert await youtube_client.fetch_subtitle("abc123", proxy_url="http://127.0.0.1:7892") == ""


@pytest.mark.asyncio
async def test_subtitle_failure_does_not_break_search(monkeypatch: pytest.MonkeyPatch) -> None:
    youtube_client, youtube_search = load_modules(monkeypatch)
    install_http_client(monkeypatch, youtube_client, _responses())
    FakeTranscriptApi.responses = {
        ("abc123", ("zh-Hans", "zh", "en")): FakeTranscriptError("disabled"),
        ("abc123", None): FakeTranscriptError("disabled"),
        ("def456", ("zh-Hans", "zh", "en")): FakeTranscriptError("disabled"),
        ("def456", None): FakeTranscriptError("disabled"),
    }
    _, execute = youtube_search.create_youtube_search_tool(api_key="test-key")
    result = await execute({"query": "Claude Code", "max_results": 2, "with_subtitles": True})
    assert result.is_error is False and "字幕摘要: 未提取字幕" in result.output


@pytest.mark.asyncio
async def test_invalid_api_key_returns_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    youtube_client, youtube_search = load_modules(monkeypatch)
    install_http_client(monkeypatch, youtube_client, _responses(search_status=403))
    _, execute = youtube_search.create_youtube_search_tool(api_key="bad-key")
    result = await execute({"query": "Claude Code"})
    assert result.is_error is True and "API key" in result.output


def test_parse_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    youtube_client, _ = load_modules(monkeypatch)
    assert youtube_client._parse_duration("PT1H2M30S") == 3750
    assert youtube_client._parse_duration("PT15M") == 900
    assert youtube_client._parse_duration("PT30S") == 30


def test_tool_definition(monkeypatch: pytest.MonkeyPatch) -> None:
    _, youtube_search = load_modules(monkeypatch)
    tool, _ = youtube_search.create_youtube_search_tool(api_key="test-key")
    assert tool.name == "youtube_search" and tool.category == "search"
    assert tool.parameters.required == ["query"]


def test_extract_video_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _, youtube_search = load_modules(monkeypatch)
    assert youtube_search._extract_video_id("https://www.youtube.com/watch?v=abc123") == "abc123"
    assert youtube_search._extract_video_id("https://youtu.be/abc123") == "abc123"
    assert youtube_search._extract_video_id("https://www.youtube.com/watch?v=abc123&t=60") == "abc123"
