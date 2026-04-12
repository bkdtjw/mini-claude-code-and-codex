from __future__ import annotations

from typing import Any

import pytest

from backend.core.s02_tools.builtin import proxy_api, proxy_tools
from backend.core.s02_tools.builtin.proxy_api import MihomoAPI
from backend.core.s02_tools.builtin.proxy_api_support import APIRequest
from backend.core.s02_tools.builtin.proxy_models import DelayTestResult, ProxyGroup, ProxyStatus


class FakeResponse:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data = data or {}
        self.content = b"{}"

    def json(self) -> dict[str, Any]:
        return self._data

    def raise_for_status(self) -> None:
        return None


class FakeAsyncClient:
    init_args: list[tuple[float, bool]] = []
    response: FakeResponse = FakeResponse()

    def __init__(self, timeout: float, trust_env: bool) -> None:
        self.init_args.append((timeout, trust_env))

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> FakeResponse:
        return self.response


class TimeoutGroupAPI:
    async def test_group_delay(
        self,
        group_name: str,
        timeout: int,
        test_url: str,
    ) -> DelayTestResult:
        return DelayTestResult(results={}, test_url=test_url, timestamp="2026-04-04 10:00:00")

    async def get_version(self) -> str:
        return "v1.19.22"

    async def get_proxies(self) -> ProxyStatus:
        return ProxyStatus(groups=[ProxyGroup(name="GLOBAL", type="Selector", now="", all=[])])


class MissingGroupAPI(TimeoutGroupAPI):
    async def get_proxies(self) -> ProxyStatus:
        return ProxyStatus(groups=[ProxyGroup(name="AUTO", type="Selector", now="", all=[])])


@pytest.mark.asyncio
async def test_test_group_delay_uses_longer_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.init_args = []
    FakeAsyncClient.response = FakeResponse({"JP1": 123})
    monkeypatch.setattr(proxy_api.httpx, "AsyncClient", FakeAsyncClient)
    result = await MihomoAPI().test_group_delay("GLOBAL", timeout=5000)
    assert result.results == {"JP1": 123}
    assert FakeAsyncClient.init_args[0] == (20.0, False)


@pytest.mark.asyncio
async def test_test_group_delay_filters_message_key(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.init_args = []
    FakeAsyncClient.response = FakeResponse({"message": "get delay: all proxies timeout"})
    monkeypatch.setattr(proxy_api.httpx, "AsyncClient", FakeAsyncClient)
    result = await MihomoAPI().test_group_delay("GLOBAL", timeout=5000)
    assert result.results == {}
    assert result.timeout_nodes == []


@pytest.mark.asyncio
async def test_proxy_test_tool_all_timeout_message(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ensure_ok(*_args: object) -> str | None:
        return None

    monkeypatch.setattr(proxy_tools, "_ensure_mihomo_running", _ensure_ok)
    monkeypatch.setattr(proxy_tools, "_get_api", lambda *_args: TimeoutGroupAPI())
    _, execute = proxy_tools.create_proxy_test_tool()
    result = await execute({"group": "GLOBAL"})
    assert result.is_error is True
    assert "All nodes timed out" in result.output


@pytest.mark.asyncio
async def test_proxy_test_tool_group_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ensure_ok(*_args: object) -> str | None:
        return None

    monkeypatch.setattr(proxy_tools, "_ensure_mihomo_running", _ensure_ok)
    monkeypatch.setattr(proxy_tools, "_get_api", lambda *_args: MissingGroupAPI())
    _, execute = proxy_tools.create_proxy_test_tool()
    result = await execute({"group": "GLOBAL"})
    assert result.is_error is True
    assert "Proxy group GLOBAL not found" in result.output
    assert "AUTO" in result.output


def test_api_request_timeout_override() -> None:
    assert APIRequest(method="GET", path="/test", timeout=30.0).timeout == 30.0
    assert APIRequest(method="GET", path="/test").timeout is None
