from __future__ import annotations

from typing import Any

import pytest

from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.s02_tools.builtin import feishu_notify as feishu_module
from backend.core.s02_tools.builtin.feishu_notify import create_feishu_notify_tool


class FakeResponse:
    def __init__(self, status_code: int, data: dict[str, Any]) -> None:
        self.status_code = status_code
        self._data = data

    def json(self) -> dict[str, Any]:
        return self._data


class InvalidJsonResponse(FakeResponse):
    def json(self) -> dict[str, Any]:
        raise ValueError("invalid json")


class FakeAsyncClient:
    calls: list[tuple[str, dict[str, Any]]] = []
    response = FakeResponse(200, {"StatusCode": 0, "StatusMessage": "success"})

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
        self.calls.append((url, json))
        return self.response


@pytest.mark.asyncio
async def test_feishu_notify_sends_text_message(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.response = FakeResponse(200, {"StatusCode": 0, "StatusMessage": "success"})
    monkeypatch.setattr(feishu_module.httpx, "AsyncClient", FakeAsyncClient)
    _, execute = create_feishu_notify_tool("https://open.feishu.cn/open-apis/bot/v2/hook/test-token")
    result = await execute({"content": "hello feishu"})
    assert result.is_error is False
    assert FakeAsyncClient.calls[0][1]["msg_type"] == "text"
    assert FakeAsyncClient.calls[0][1]["content"]["text"] == "hello feishu"


@pytest.mark.asyncio
async def test_feishu_notify_sends_post_message_with_sign(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.response = FakeResponse(200, {"StatusCode": 0, "StatusMessage": "success"})
    monkeypatch.setattr(feishu_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(feishu_module.time, "time", lambda: 1700000000)
    _, execute = create_feishu_notify_tool(
        "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
        "secret-123",
    )
    result = await execute({"title": "日报", "content": "第一行\n第二行"})
    body = FakeAsyncClient.calls[0][1]
    assert result.is_error is False
    assert body["msg_type"] == "post"
    assert body["content"]["post"]["zh_cn"]["title"] == "日报"
    assert body["timestamp"] == "1700000000"
    assert "sign" in body


def test_register_builtin_tools_adds_feishu_tool() -> None:
    registry = ToolRegistry()
    register_builtin_tools(
        registry,
        workspace=".",
        mode="readonly",
        feishu_webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
    )
    assert registry.has("feishu_notify")


def test_register_builtin_tools_adds_feishu_without_workspace() -> None:
    registry = ToolRegistry()
    register_builtin_tools(
        registry,
        workspace=None,
        mode="readonly",
        feishu_webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
    )
    assert registry.has("feishu_notify")


@pytest.mark.asyncio
async def test_feishu_notify_handles_invalid_json_response(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.response = InvalidJsonResponse(200, {})
    monkeypatch.setattr(feishu_module.httpx, "AsyncClient", FakeAsyncClient)
    _, execute = create_feishu_notify_tool("https://open.feishu.cn/open-apis/bot/v2/hook/test-token")
    result = await execute({"content": "hello feishu"})
    assert result.is_error is True
    assert "有效 JSON" in result.output


@pytest.mark.asyncio
async def test_register_builtin_tools_reads_feishu_secret_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.response = FakeResponse(200, {"StatusCode": 0, "StatusMessage": "success"})
    monkeypatch.setattr(feishu_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(feishu_module.time, "time", lambda: 1700000000)
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/open-apis/bot/v2/hook/test-token")
    monkeypatch.setenv("FEISHU_WEBHOOK_SECRET", "secret-123")
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=None, mode="readonly")
    tool = registry.get("feishu_notify")
    assert tool is not None
    _, execute = tool
    result = await execute({"content": "hello feishu"})
    assert result.is_error is False
    assert FakeAsyncClient.calls[0][1]["timestamp"] == "1700000000"
    assert "sign" in FakeAsyncClient.calls[0][1]
