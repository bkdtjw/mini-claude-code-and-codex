from __future__ import annotations

from typing import Any

import httpx
import pytest

from backend.core.s02_tools.builtin import proxy_api, proxy_tools
from backend.core.s02_tools.builtin.proxy_api import MihomoAPI
from backend.core.s02_tools.builtin.proxy_auto_start import AUTO_START_HINT
from backend.core.s02_tools.builtin.proxy_models import (
    DelayTestResult,
    ProxyGroup,
    ProxyNode,
    ProxyStatus,
)


class FakeResponse:
    def __init__(self, status_code: int = 200, data: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._data = data or {}
        self.content = b"{}" if data is not None else b""

    def json(self) -> dict[str, Any]:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code < 400:
            return
        request = httpx.Request("GET", "http://127.0.0.1:9090")
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError("request failed", request=request, response=response)


class FakeAsyncClient:
    calls: list[dict[str, Any]] = []
    init_args: list[tuple[float, bool]] = []
    response: FakeResponse = FakeResponse()
    error: Exception | None = None

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
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers or {},
                "params": params or {},
                "json": json or {},
            }
        )
        if self.error is not None:
            raise self.error
        return self.response


class StubProxyAPI:
    async def get_proxies(self) -> ProxyStatus:
        return ProxyStatus(
            groups=[
                ProxyGroup(
                    name="GLOBAL",
                    type="Selector",
                    now="Tokyo-JP1",
                    all=["Tokyo-JP1", "HongKong-HK2"],
                )
            ],
            nodes=[
                ProxyNode(name="Tokyo-JP1", type="Shadowsocks", alive=True, delay=65),
                ProxyNode(name="HongKong-HK2", type="Trojan", alive=False, delay=0),
            ],
        )

    async def get_version(self) -> str:
        return "v1.19.22"

    async def test_group_delay(
        self, group_name: str, timeout: int, test_url: str
    ) -> DelayTestResult:
        return DelayTestResult(
            results={"HongKong-HK2": 78, "Tokyo-JP1": 65, "US1": 180, "TW1": 0},
            timeout_nodes=["TW1"],
            fastest_node="Tokyo-JP1",
            fastest_delay=65,
            test_url=test_url,
            timestamp="2026-04-03 15:30:00",
        )


@pytest.mark.asyncio
async def test_proxy_status_tool_returns_formatted_output(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ensure_ok(*_args: object) -> str | None:
        return None

    monkeypatch.setattr(proxy_tools, "_ensure_mihomo_running", _ensure_ok)
    monkeypatch.setattr(proxy_tools, "_get_api", lambda *_args: StubProxyAPI())
    _, execute = proxy_tools.create_proxy_status_tool()
    result = await execute({})
    assert result.is_error is False
    assert "mihomo v1.19.22" in result.output
    assert "Group: GLOBAL" in result.output
    assert "Tokyo-JP1(65ms)" in result.output


@pytest.mark.asyncio
async def test_proxy_test_tool_returns_sorted_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ensure_ok(*_args: object) -> str | None:
        return None

    monkeypatch.setattr(proxy_tools, "_ensure_mihomo_running", _ensure_ok)
    monkeypatch.setattr(proxy_tools, "_get_api", lambda *_args: StubProxyAPI())
    _, execute = proxy_tools.create_proxy_test_tool()
    result = await execute({"group": "GLOBAL"})
    assert result.is_error is False
    assert (
        result.output.index("Tokyo-JP1")
        < result.output.index("HongKong-HK2")
        < result.output.index("US1")
    )
    assert result.output.index("US1") < result.output.index("TW1")
    assert "Fastest node: Tokyo-JP1 (65ms)" in result.output


@pytest.mark.asyncio
async def test_proxy_status_and_test_handle_api_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ensure_failed(*_args: object) -> str | None:
        return AUTO_START_HINT

    monkeypatch.setattr(proxy_tools, "_ensure_mihomo_running", _ensure_failed)
    _, execute_status = proxy_tools.create_proxy_status_tool()
    _, execute_test = proxy_tools.create_proxy_test_tool()
    status_result = await execute_status({})
    test_result = await execute_test({})
    assert status_result.is_error is True and AUTO_START_HINT in status_result.output
    assert test_result.is_error is True and AUTO_START_HINT in test_result.output


@pytest.mark.asyncio
async def test_proxy_api_url_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.init_args = []
    FakeAsyncClient.error = None
    FakeAsyncClient.response = FakeResponse(data={"delay": 123})
    monkeypatch.setattr(proxy_api.httpx, "AsyncClient", FakeAsyncClient)
    delay = await MihomoAPI().get_delay("Node /1?", timeout=3000)
    assert delay == 123
    assert FakeAsyncClient.calls[0]["url"].endswith("/proxies/Node%20%2F1%3F/delay")
    assert FakeAsyncClient.calls[0]["params"] == {
        "timeout": 3000,
        "url": "http://www.gstatic.com/generate_204",
    }
    assert FakeAsyncClient.init_args[0] == (10.0, False)


def test_proxy_api_headers_with_secret() -> None:
    assert MihomoAPI(secret="top-secret")._headers()["Authorization"] == "Bearer top-secret"
    assert "Authorization" not in MihomoAPI()._headers()


def test_register_builtin_tools_adds_proxy_tools() -> None:
    from backend.core.s02_tools import ToolRegistry
    from backend.core.s02_tools.builtin import register_builtin_tools

    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=None, mode="readonly")
    assert registry.has("proxy_status")
    assert registry.has("proxy_test")
