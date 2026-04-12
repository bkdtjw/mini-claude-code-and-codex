from __future__ import annotations

import pytest

from backend.tests.unit.test_youtube_search import FAKE_VIDEOS_RESPONSE
from backend.tests.unit.youtube_test_support import (
    FakeHttpResponse,
    install_http_client,
    load_modules,
)


@pytest.mark.asyncio
async def test_search_skips_channel_result_before_first_video(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    youtube_client, youtube_search = load_modules(monkeypatch)
    install_http_client(
        monkeypatch,
        youtube_client,
        {
            "/search": FakeHttpResponse(
                200,
                {
                    "items": [
                        {
                            "id": {"kind": "youtube#channel", "channelId": "chan-1"},
                            "snippet": {"title": "OpenAI", "channelTitle": "OpenAI"},
                        },
                        {
                            "id": {"kind": "youtube#video", "videoId": "abc123"},
                            "snippet": {
                                "title": "Test Video About Claude Code",
                                "channelTitle": "TechChannel",
                                "publishedAt": "2026-03-20T10:00:00Z",
                            },
                        },
                    ]
                },
                "https://example.com/search",
            ),
            "/videos": FakeHttpResponse(200, FAKE_VIDEOS_RESPONSE, "https://example.com/videos"),
        },
    )
    _, execute = youtube_search.create_youtube_search_tool(api_key="test-key")
    result = await execute({"query": "OpenAI", "max_results": 1, "with_subtitles": False})
    assert result.is_error is False
    assert "共 1 个视频" in result.output
    assert "Test Video About Claude Code" in result.output
