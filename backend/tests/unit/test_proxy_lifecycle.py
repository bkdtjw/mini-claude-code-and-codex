from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from backend.core.s02_tools.builtin import proxy_lifecycle
from backend.core.s02_tools.builtin.proxy_chain import CHAIN_GROUP_NAME, CHAIN_PREFIX, EXIT_PREFIX
from backend.core.s02_tools.builtin.proxy_custom_nodes import CustomNodesManager
from backend.core.s02_tools.builtin.proxy_lifecycle import ProxyLifecycle

from .proxy_lifecycle_test_support import (
    FakeWininet,
    FakeWinreg,
    make_base_config,
    make_exit_node,
    make_runtime_config,
)


def test_custom_nodes_add_update_remove_and_chain_config() -> None:
    config = make_runtime_config()
    manager = CustomNodesManager(config.custom_nodes_path)
    manager.add_exit_node(make_exit_node())
    manager.add_exit_node({**make_exit_node(), "server": "updated.example.com"})
    manager.set_chain_config("relay", transit_pattern="HK", transit_nodes=["HK-A"])
    assert manager.get_exit_nodes()[0]["server"] == "updated.example.com"
    assert manager.get_chain_config()["exit_node"] == f"{EXIT_PREFIX}relay"
    assert manager.get_chain_config()["transit_pattern"] == "HK"
    assert manager.get_chain_config()["transit_nodes"] == ["HK-A"]
    manager.clear_chain_config()
    manager.remove_exit_node("relay")
    assert manager.get_chain_config()["exit_node"] == ""
    assert manager.get_exit_nodes() == []


def test_merge_into_config_adds_exit_nodes_and_chain() -> None:
    config = make_runtime_config()
    manager = CustomNodesManager(config.custom_nodes_path)
    base = make_base_config()
    base["proxies"].append({"name": "HK-B", "type": "ss", "server": "hk2.example.com", "port": 443})
    base["proxy-groups"][0]["proxies"].append("HK-B")
    original = copy.deepcopy(base)
    manager.add_exit_node(make_exit_node())
    merged = manager.merge_into_config(base)
    manager.set_chain_config("relay", transit_pattern="HK")
    chained = manager.merge_into_config(base)
    assert any(item["name"] == f"{EXIT_PREFIX}relay" for item in merged["proxies"])
    assert f"{EXIT_PREFIX}relay" in merged["proxy-groups"][0]["proxies"]
    assert any(group["name"] == CHAIN_GROUP_NAME for group in chained["proxy-groups"])
    assert any(proxy["name"].startswith(CHAIN_PREFIX) for proxy in chained["proxies"])
    assert base == original


def test_set_and_clear_system_proxy_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_winreg = FakeWinreg()
    fake_wininet = FakeWininet()
    monkeypatch.setattr(proxy_lifecycle, "IS_WINDOWS", True)
    monkeypatch.setattr(proxy_lifecycle, "winreg", fake_winreg)
    monkeypatch.setattr(
        proxy_lifecycle.ctypes,
        "windll",
        SimpleNamespace(wininet=fake_wininet),
        raising=False,
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
    config = make_runtime_config()
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

    async def no_running_api(_self: object) -> str:
        return ""

    monkeypatch.setattr(
        ProxyLifecycle, "_kill_process", staticmethod(lambda _exe: tracker.append("kill"))
    )
    monkeypatch.setattr(ProxyLifecycle, "_check_systemd_service", lambda _self: False)
    monkeypatch.setattr(proxy_lifecycle.MihomoAPI, "get_version", no_running_api)
    monkeypatch.setattr(
        proxy_lifecycle.ProxyConfigGenerator, "generate_from_subscription", fake_generate
    )
    monkeypatch.setattr(proxy_lifecycle.CustomNodesManager, "merge_into_config", fake_merge)
    monkeypatch.setattr(proxy_lifecycle.ProxyConfigGenerator, "save", fake_save)
    monkeypatch.setattr(proxy_lifecycle, "MihomoProcess", StubProcess)
    output = await ProxyLifecycle(config).start()
    assert tracker == ["kill", "generate", "merge", "save", "start"]
    assert "mihomo: v1.19.22" in output
    assert "System proxy: unchanged" in output
    assert "Node count: 2" in output
    assert f"Exit node: {EXIT_PREFIX}relay" in output


@pytest.mark.asyncio
async def test_lifecycle_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker: list[str] = []
    config = make_runtime_config()
    monkeypatch.setattr(ProxyLifecycle, "_check_systemd_service", lambda _self: False)
    monkeypatch.setattr(
        ProxyLifecycle, "_kill_process", staticmethod(lambda _exe: tracker.append("kill"))
    )
    output = await ProxyLifecycle(config).stop()
    assert tracker == ["kill"]
    assert "Proxy stopped" in output
    assert "System proxy: unchanged" in output
