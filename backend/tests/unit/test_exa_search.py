from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.core.s02_tools.builtin.exa_search import (
    ExaSearchError,
    ExaSearchRequest,
    exa_search,
)


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    captured: dict = {}

    def __init__(self, **kwargs) -> None:
        _FakeClient.captured["client_kwargs"] = kwargs

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def post(self, url, headers=None, json=None) -> _FakeResponse:
        _FakeClient.captured.update(url=url, headers=headers, body=json)
        return _FakeResponse(
            {
                "results": [
                    {
                        "title": "Nvidia ships new chip",
                        "url": "https://news.example/nv",
                        "publishedDate": "2026-06-27T01:00:00.000Z",
                        "highlights": ["fresh chip news"],
                    },
                    "not-a-dict",
                ]
            }
        )


@pytest.mark.asyncio
async def test_exa_search_windows_and_parses(monkeypatch) -> None:
    import backend.core.s02_tools.builtin.exa_search as mod

    monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeClient)
    results = await exa_search(
        ExaSearchRequest(
            query="Latest news on Nvidia",
            api_key="secret",
            start_published=datetime(2026, 6, 26, 16, 0, 0, tzinfo=UTC),
            end_published=datetime(2026, 6, 27, 15, 59, 59, tzinfo=UTC),
            num_results=5,
            proxy_url="http://127.0.0.1:7890",
        )
    )

    assert len(results) == 1
    assert results[0].title == "Nvidia ships new chip"
    assert results[0].highlights == ["fresh chip news"]
    body = _FakeClient.captured["body"]
    assert body["startPublishedDate"] == "2026-06-26T16:00:00.000Z"
    assert body["endPublishedDate"] == "2026-06-27T15:59:59.000Z"
    assert body["contents"]["highlights"] is True
    assert body["contents"]["maxAgeHours"] == 0
    assert _FakeClient.captured["headers"]["x-api-key"] == "secret"
    assert _FakeClient.captured["client_kwargs"]["proxy"] == "http://127.0.0.1:7890"


@pytest.mark.asyncio
async def test_exa_search_requires_key() -> None:
    with pytest.raises(ExaSearchError):
        await exa_search(ExaSearchRequest(query="x", api_key=""))
