from __future__ import annotations

import asyncio

import pytest

from backend.config.settings import settings as app_settings
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import (
    proxy_scheduler,
    proxy_scheduler_tools,
    register_builtin_tools,
)
from backend.core.s02_tools.builtin.proxy_chain import ChainProxyManager
from backend.core.s02_tools.builtin.proxy_scheduler import ChainScheduler
from backend.core.s02_tools.builtin.proxy_scheduler_tools import create_proxy_scheduler_tool

from .proxy_chain_test_support import make_chain_config, make_temp_config_path, write_config
from .proxy_scheduler_test_support import FakeSchedulerAPI, write_custom_nodes


def _make_chain_name() -> tuple[dict[str, object], str]:
    config = make_chain_config(["香港A", "日本A"], ["落地"])
    chained, _ = ChainProxyManager.set_chain(config, "落地", transit_pattern="香港")
    return config, ChainProxyManager.list_chains(chained)[0]["name"]


@pytest.mark.asyncio
async def test_scheduler_start(monkeypatch: pytest.MonkeyPatch) -> None:
    source, chain_name = _make_chain_name()
    config_path = make_temp_config_path()
    custom_nodes_path = config_path.parent / "custom_nodes.yaml"
    write_config(config_path, source)
    write_custom_nodes(custom_nodes_path, "落地", transit_pattern="香港")
    api = FakeSchedulerAPI([{chain_name: 80}])
    monkeypatch.setattr(proxy_scheduler, "MihomoAPI", lambda *_args: api)
    async def _idle_loop(self: ChainScheduler) -> None:
        await asyncio.sleep(3600)
    monkeypatch.setattr(proxy_scheduler.ChainScheduler, "_loop", _idle_loop)
    scheduler = ChainScheduler(
        "http://127.0.0.1:9090",
        "",
        str(config_path),
        str(custom_nodes_path),
    )
    output = await scheduler.start()
    assert "调度引擎已启动" in output and chain_name in output
    assert api.reload_paths and api.switches == [chain_name]
    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_stop_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    source, chain_name = _make_chain_name()
    config_path = make_temp_config_path()
    custom_nodes_path = config_path.parent / "custom_nodes.yaml"
    write_config(config_path, source)
    write_custom_nodes(custom_nodes_path, "落地", transit_pattern="香港")
    api = FakeSchedulerAPI([{chain_name: 80}])
    monkeypatch.setattr(proxy_scheduler, "MihomoAPI", lambda *_args: api)
    async def _idle_loop(self: ChainScheduler) -> None:
        await asyncio.sleep(3600)
    monkeypatch.setattr(proxy_scheduler.ChainScheduler, "_loop", _idle_loop)
    scheduler = ChainScheduler(
        "http://127.0.0.1:9090",
        "",
        str(config_path),
        str(custom_nodes_path),
        llm_callback=lambda _p: asyncio.sleep(0, result="{}"),
    )
    await scheduler.start()
    status = await scheduler.status()
    stopped = await scheduler.stop()
    assert "LLM 智能层: 已启用" in status
    assert "调度引擎已停止" in stopped and scheduler.is_running is False


def test_record_max_50(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proxy_scheduler, "MihomoAPI", lambda *_args: FakeSchedulerAPI([{}]))
    scheduler = ChainScheduler("http://127.0.0.1:9090", "", "config.yaml", "custom_nodes.yaml")
    for index in range(55):
        scheduler._record(f"from-{index}", f"to-{index}", "切换", index, "rule")
    assert len(scheduler._history) == 50
    assert scheduler._history[0]["from"] == "from-5"


@pytest.mark.asyncio
async def test_scheduler_tool_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubScheduler:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.is_running = False
        async def start(self) -> str:
            self.is_running = True
            return "started"
        async def stop(self) -> str:
            self.is_running = False
            return "stopped"
        async def status(self) -> str:
            return "status"

    async def _ensure_ok(*_args: object) -> str | None:
        return None

    monkeypatch.setattr(proxy_scheduler_tools, "_ensure_mihomo_running", _ensure_ok)
    monkeypatch.setattr(proxy_scheduler_tools, "ChainScheduler", StubScheduler)
    _, execute = create_proxy_scheduler_tool(
        "http://127.0.0.1:9090",
        "",
        "config.yaml",
        "custom_nodes.yaml",
    )
    started = await execute({"action": "start"})
    status = await execute({"action": "status"})
    stopped = await execute({"action": "stop"})
    assert started.output == "started" and status.output == "status" and stopped.output == "stopped"


def test_register_builtin_tools_adds_proxy_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "mihomo_config_path", str(make_temp_config_path()))
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=None, mode="readonly")
    assert registry.has("proxy_scheduler")
