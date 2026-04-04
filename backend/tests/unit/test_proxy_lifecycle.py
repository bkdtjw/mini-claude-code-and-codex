from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from backend.config.settings import settings as app_settings
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import (
    proxy_chain_tools,
    proxy_lifecycle,
    proxy_lifecycle_tools,
    register_builtin_tools,
)
from backend.core.s02_tools.builtin.proxy_chain import CHAIN_GROUP_NAME, CHAIN_PREFIX, EXIT_PREFIX
from backend.core.s02_tools.builtin.proxy_chain_tools import create_proxy_chain_tool
from backend.core.s02_tools.builtin.proxy_custom_nodes import CustomNodesManager
from backend.core.s02_tools.builtin.proxy_lifecycle import ProxyLifecycle
from backend.core.s02_tools.builtin.proxy_lifecycle_tools import (
    create_proxy_off_tool,
    create_proxy_on_tool,
)
from backend.core.s02_tools.builtin.proxy_models import ProxyLifecycleConfig

from .proxy_chain_test_support import FakeChainAPI, write_config
from .proxy_lifecycle_test_support import (
    FakeWininet,
    FakeWinreg,
    make_base_config,
    make_exit_node,
    make_lifecycle_paths,
)


def _make_runtime_config() -> ProxyLifecycleConfig:
    paths = make_lifecycle_paths()
    return ProxyLifecycleConfig(
        mihomo_path=str(paths["mihomo"]),
        config_path=str(paths["config"]),
        work_dir=str(paths["root"]),
        sub_path=str(paths["sub"]),
        custom_nodes_path=str(paths["custom"]),
    )


def test_custom_nodes_add_update_remove_and_chain_config() -> None:
    config = _make_runtime_config()
    manager = CustomNodesManager(config.custom_nodes_path)
    manager.add_exit_node(make_exit_node())
    manager.add_exit_node({**make_exit_node(), "server": "updated.example.com"})
    manager.set_chain_config("落地", transit_pattern="香港", transit_nodes=["香港A"])
    assert manager.get_exit_nodes()[0]["server"] == "updated.example.com"
    assert manager.get_chain_config()["transit_pattern"] == "香港"
    manager.clear_chain_config()
    manager.remove_exit_node("落地")
    assert manager.get_chain_config()["exit_node"] == ""
    assert manager.get_exit_nodes() == []


def test_merge_into_config_adds_exit_nodes_and_chain() -> None:
    config = _make_runtime_config()
    manager = CustomNodesManager(config.custom_nodes_path)
    base = make_base_config()
    base["proxies"].append(
        {"name": "香港B", "type": "ss", "server": "hk2.example.com", "port": 443}
    )
    base["proxy-groups"][0]["proxies"].append("香港B")
    original = copy.deepcopy(base)
    manager.add_exit_node(make_exit_node())
    merged = manager.merge_into_config(base)
    manager.set_chain_config("落地", transit_pattern="香港")
    chained = manager.merge_into_config(base)
    assert any(item["name"] == f"{EXIT_PREFIX}落地" for item in merged["proxies"])
    assert f"{EXIT_PREFIX}落地" in merged["proxy-groups"][0]["proxies"]
    assert any(group["name"] == CHAIN_GROUP_NAME for group in chained["proxy-groups"])
    assert any(proxy["name"].startswith(CHAIN_PREFIX) for proxy in chained["proxies"])
    assert base == original


def test_set_and_clear_system_proxy_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_winreg = FakeWinreg()
    fake_wininet = FakeWininet()
    monkeypatch.setattr(proxy_lifecycle, "winreg", fake_winreg)
    monkeypatch.setattr(
        proxy_lifecycle.ctypes,
        "windll",
        SimpleNamespace(wininet=fake_wininet),
    )
    assert ProxyLifecycle.set_system_proxy("127.0.0.1", 7890) is True
    assert fake_winreg.values["ProxyEnable"] == 1
    assert fake_winreg.values["ProxyServer"] == "127.0.0.1:7890"
    assert ProxyLifecycle.is_system_proxy_set() is True
    assert ProxyLifecycle.clear_system_proxy() is True
    assert fake_winreg.values["ProxyEnable"] == 0
    assert fake_wininet.calls == [39, 37, 39, 37]


@pytest.mark.asyncio
async def test_lifecycle_start_full_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker: list[str] = []
    config = _make_runtime_config()
    CustomNodesManager(config.custom_nodes_path).add_exit_node(make_exit_node())

    def fake_generate(self: object, data: object, **kwargs: object) -> dict[str, object]:
        _ = (self, data, kwargs)
        tracker.append("generate")
        return make_base_config()

    def fake_merge(self: object, current: dict[str, object]) -> dict[str, object]:
        _ = self
        tracker.append("merge")
        return {**current, "proxies": current["proxies"] + [make_exit_node()]}

    def fake_save(self: object, current: dict[str, object]) -> str:
        _ = (self, current)
        tracker.append("save")
        return str(config.config_path)

    class StubProcess:
        def __init__(self, *_args: object) -> None:
            return None

        async def start(self) -> str:
            tracker.append("start")
            return "v1.19.22"

    monkeypatch.setattr(
        ProxyLifecycle,
        "_kill_process",
        staticmethod(lambda _exe: tracker.append("kill")),
    )
    monkeypatch.setattr(
        proxy_lifecycle.ProxyConfigGenerator,
        "generate_from_subscription",
        fake_generate,
    )
    monkeypatch.setattr(proxy_lifecycle.CustomNodesManager, "merge_into_config", fake_merge)
    monkeypatch.setattr(proxy_lifecycle.ProxyConfigGenerator, "save", fake_save)
    monkeypatch.setattr(proxy_lifecycle, "MihomoProcess", StubProcess)
    monkeypatch.setattr(
        ProxyLifecycle,
        "set_system_proxy",
        staticmethod(lambda _host, _port: tracker.append("proxy") or True),
    )
    output = await ProxyLifecycle(config).start()
    assert tracker == ["kill", "generate", "merge", "save", "start", "proxy"]
    assert "mihomo: v1.19.22" in output
    assert "节点数: 2" in output
    assert f"落地节点: {EXIT_PREFIX}落地" in output


@pytest.mark.asyncio
async def test_lifecycle_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker: list[str] = []
    config = _make_runtime_config()
    monkeypatch.setattr(
        ProxyLifecycle,
        "clear_system_proxy",
        staticmethod(lambda: tracker.append("clear") or True),
    )
    monkeypatch.setattr(
        ProxyLifecycle,
        "_kill_process",
        staticmethod(lambda _exe: tracker.append("kill")),
    )
    output = await ProxyLifecycle(config).stop()
    assert tracker == ["clear", "kill"]
    assert "代理已关闭" in output and "已还原" in output


@pytest.mark.asyncio
async def test_proxy_on_and_off_tool_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _make_runtime_config()

    class DummyLifecycle:
        async def start(self, force: bool = True) -> str:
            return f"start:{force}"

        async def stop(self) -> str:
            return "stop"

    monkeypatch.setattr(proxy_lifecycle_tools, "_get_lifecycle", lambda *_args: DummyLifecycle())
    on_def, on_execute = create_proxy_on_tool(
        mihomo_path=config.mihomo_path,
        config_path=config.config_path,
        work_dir=config.work_dir,
        sub_path=config.sub_path,
        custom_nodes_path=config.custom_nodes_path,
        api_url=config.api_url,
        secret=config.api_secret,
    )
    off_def, off_execute = create_proxy_off_tool()
    on_result = await on_execute({"force": False})
    off_result = await off_execute({})
    assert on_def.name == "proxy_on" and on_result.output == "start:False"
    assert off_def.name == "proxy_off" and off_result.output == "stop"


def test_register_builtin_tools_adds_proxy_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _make_runtime_config()
    monkeypatch.setattr(app_settings, "mihomo_path", config.mihomo_path)
    monkeypatch.setattr(app_settings, "mihomo_config_path", config.config_path)
    monkeypatch.setattr(app_settings, "mihomo_work_dir", config.work_dir)
    monkeypatch.setattr(app_settings, "mihomo_sub_path", config.sub_path)
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=None, mode="readonly")
    assert registry.has("proxy_on") and registry.has("proxy_off")


@pytest.mark.asyncio
async def test_proxy_chain_syncs_to_custom_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _make_runtime_config()

    async def _ensure_ok(*_args: object) -> None:
        return None

    write_config(Path(config.config_path), make_base_config())
    api = FakeChainAPI()
    monkeypatch.setattr(proxy_chain_tools, "_get_api", lambda *_args: api)
    monkeypatch.setattr(proxy_chain_tools, "_ensure_mihomo_running", _ensure_ok)
    _, execute = create_proxy_chain_tool(
        config.config_path,
        custom_nodes_path=config.custom_nodes_path,
    )
    add_result = await execute(
        {
            "action": "add_exit",
            "name": "落地",
            "type": "http",
            "server": "na-relay.oneproxy.vip",
            "port": 1337,
            "extra": {"username": "demo"},
        }
    )
    set_result = await execute({"action": "set", "exit_node": "落地", "transit_pattern": "香港"})
    data = yaml.safe_load(Path(config.custom_nodes_path).read_text(encoding="utf-8"))
    assert add_result.is_error is False and set_result.is_error is False
    assert data["exit_nodes"][0]["name"] == f"{EXIT_PREFIX}落地"
    assert data["chain_config"]["exit_node"] == f"{EXIT_PREFIX}落地"
