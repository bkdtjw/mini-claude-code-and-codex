from __future__ import annotations

from typing import Any

import httpx
import pytest

from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.s02_tools.builtin import web_search as web_search_module
from backend.core.s02_tools.builtin.web_search import create_web_search_tool


class FakeResponse:
    def __init__(self, status_code: int, data: dict[str, Any]) -> None:
        self.status_code = status_code
        self._data = data
        self.request = httpx.Request("POST", web_search_module.ZHIPU_SEARCH_URL)

    @property
    def text(self) -> str:
        return str(self._data)

    def json(self) -> dict[str, Any]:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=self.request, response=self)


class FakeAsyncClient:
    calls: list[dict[str, Any]] = []
    init_args: list[dict[str, Any]] = []
    response = FakeResponse(200, {"search_result": []})
    error: Exception | None = None

    def __init__(self, timeout: float, trust_env: bool) -> None:
        self.init_args.append({"timeout": timeout, "trust_env": trust_env})

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def post(
        self,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self.error is not None:
            raise self.error
        return self.response


def _install_fake_client(monkeypatch: pytest.MonkeyPatch, response: FakeResponse) -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.init_args = []
    FakeAsyncClient.response = response
    FakeAsyncClient.error = None
    monkeypatch.setattr(web_search_module.httpx, "AsyncClient", FakeAsyncClient)


@pytest.mark.asyncio
async def test_web_search_returns_formatted_results(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_client(
        monkeypatch,
        FakeResponse(
            200,
            {
                "search_result": [
                    {
                        "title": "Python 3.12 新特性",
                        "link": "https://docs.python.org/3/whatsnew/3.12.html",
                        "content": "Python 3.12 includes better error messages.",
                        "media": "Python Docs",
                        "publish_date": "2026-05-01",
                    }
                ]
            },
        ),
    )
    tool, execute = create_web_search_tool("test-key")
    result = await execute({"query": "Python 3.12 新特性", "count": 1, "time_filter": "week"})
    assert result.is_error is False and tool.name == "WebSearch"
    assert "Python 3.12 新特性" in result.output
    assert "https://docs.python.org/3/whatsnew/3.12.html" in result.output
    assert "Python 3.12 includes better error messages." in result.output
    call = FakeAsyncClient.calls[0]
    assert call["url"] == web_search_module.ZHIPU_SEARCH_URL
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["json"]["search_engine"] == "search_pro"
    assert call["json"]["search_query"] == "Python 3.12 新特性"
    assert call["json"]["count"] == 1
    assert call["json"]["search_recency_filter"] == "week"
    assert FakeAsyncClient.init_args[0] == {"timeout": 30.0, "trust_env": False}


@pytest.mark.asyncio
async def test_web_search_rejects_empty_query() -> None:
    _, execute = create_web_search_tool("test-key")
    result = await execute({"query": "   "})
    assert result.is_error is True
    assert "搜索关键词不能为空" in result.output


@pytest.mark.asyncio
async def test_web_search_empty_results_are_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_client(monkeypatch, FakeResponse(200, {"search_result": []}))
    _, execute = create_web_search_tool("test-key")
    result = await execute({"query": "不存在的测试查询"})
    assert result.is_error is True
    assert "未找到搜索结果" in result.output


@pytest.mark.asyncio
async def test_web_search_timeout_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_client(monkeypatch, FakeResponse(200, {"search_result": []}))
    FakeAsyncClient.error = httpx.ReadTimeout(
        "timeout",
        request=httpx.Request("POST", web_search_module.ZHIPU_SEARCH_URL),
    )
    _, execute = create_web_search_tool("test-key")
    result = await execute({"query": "Python"})
    assert result.is_error is True
    assert "请求超时" in result.output


@pytest.mark.asyncio
async def test_web_search_api_error_returns_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_client(monkeypatch, FakeResponse(401, {"error": {"message": "bad api key"}}))
    _, execute = create_web_search_tool("bad-key")
    result = await execute({"query": "Python"})
    assert result.is_error is True
    assert "HTTP 401" in result.output
    assert "bad api key" in result.output


def test_register_builtin_tools_adds_web_search_only_with_key() -> None:
    empty_registry = ToolRegistry()
    register_builtin_tools(empty_registry, workspace=None, mode="readonly")
    assert empty_registry.has("WebSearch") is False

    registry = ToolRegistry()
    register_builtin_tools(
        registry,
        workspace=None,
        mode="readonly",
        zhipu_web_search_api_key="test-key",
    )
    names = [definition.name for definition in registry.list_definitions()]
    assert "WebSearch" in names
