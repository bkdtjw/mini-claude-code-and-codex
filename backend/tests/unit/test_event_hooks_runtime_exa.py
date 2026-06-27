from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from backend.config.settings import settings
from backend.core.s02_tools.builtin.exa_search import (
    ExaResult,
    ExaSearchError,
    ExaSearchRequest,
)
from backend.core.s07_task_system import event_hooks as eh
from backend.core.s07_task_system import event_hooks_runtime as runtime_module
from backend.core.s07_task_system.event_hooks_runtime import (
    HookRuntime,
    build_hook_runtime,
    make_exa_search_fn,
)
import backend.core.s07_task_system.event_hooks_runtime.exa as exa_module


@pytest.fixture(autouse=True)
def bind_test_database() -> None:
    return None


@pytest.mark.asyncio
async def test_exa_search_fn_maps_query_and_returns_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, ExaSearchRequest] = {}
    result = ExaResult(
        title="Launch confirmed",
        url="https://example.com/story",
        published_date="2026-06-27T00:00:00Z",
        author="Example News",
        highlights=["Launch window moved"],
        text="Launch window moved",
    )

    async def fake_exa_search(request: ExaSearchRequest) -> list[ExaResult]:
        captured["request"] = request
        return [result]

    monkeypatch.setattr(exa_module, "exa_search", fake_exa_search)
    before = datetime.now(UTC)
    search = make_exa_search_fn("exa-key", "http://proxy")

    assert await search(eh.ExaQuery(query="launch", num_results=3, days=4)) == [result]

    request = captured["request"]
    assert (request.query, request.num_results) == ("launch", 3)
    assert (request.api_key, request.proxy_url) == ("exa-key", "http://proxy")
    assert request.start_published is not None and request.end_published is not None
    assert before <= request.end_published <= datetime.now(UTC)
    assert request.end_published - request.start_published == timedelta(days=4)


@pytest.mark.asyncio
async def test_exa_search_fn_degrades_exa_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_exa_search(request: ExaSearchRequest) -> list[ExaResult]:
        raise ExaSearchError("rate limited")

    monkeypatch.setattr(exa_module, "exa_search", failing_exa_search)

    assert await make_exa_search_fn("exa-key")(eh.ExaQuery(query="launch")) == []


def test_build_hook_runtime_wires_exa_when_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    _patch_runtime_factories(monkeypatch, captured)
    _patch_settings(monkeypatch, exa_api_key="exa-key", exa_proxy_url="http://proxy")

    runtime = build_hook_runtime(object(), "model-a")

    assert isinstance(runtime, HookRuntime)
    assert runtime.exa_search_fn == "exa"
    assert captured["exa"] == ("exa-key", "http://proxy")


def test_build_hook_runtime_leaves_exa_none_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    _patch_runtime_factories(monkeypatch, captured)
    _patch_settings(monkeypatch, exa_api_key="", exa_proxy_url="http://proxy")

    runtime = build_hook_runtime(object(), "model-a")

    assert runtime.exa_search_fn is None
    assert "exa" not in captured


def _patch_runtime_factories(
    monkeypatch: pytest.MonkeyPatch,
    captured: dict[str, Any],
) -> None:
    def fake_twitter(config: Any) -> str:
        return "twitter"

    def fake_assess(adapter: Any, model: str) -> str:
        return "assess"

    def fake_push(**kwargs: Any) -> str:
        return "push"

    def fake_exa(api_key: str, proxy_url: str = "") -> str:
        captured["exa"] = (api_key, proxy_url)
        return "exa"

    monkeypatch.setattr(runtime_module, "make_twitter_search_fn", fake_twitter)
    monkeypatch.setattr(runtime_module, "make_assess_fn", fake_assess)
    monkeypatch.setattr(runtime_module, "make_push_fn", fake_push)
    monkeypatch.setattr(runtime_module, "make_exa_search_fn", fake_exa)


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    values = {
        "twitter_username": "",
        "twitter_email": "",
        "twitter_password": "",
        "twitter_proxy_url": "",
        "twitter_cookies_file": "",
        "feishu_app_id": "",
        "feishu_app_secret": "",
        "feishu_chat_id": "",
        "feishu_webhook_url": "",
        "feishu_webhook_secret": "",
        **overrides,
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
