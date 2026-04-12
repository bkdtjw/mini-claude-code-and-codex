from __future__ import annotations

from pathlib import Path

import pytest

from backend.config.settings import settings as app_settings
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import proxy_chain_tools, register_builtin_tools
from backend.core.s02_tools.builtin.proxy_chain import (
    CHAIN_GROUP_NAME,
    CHAIN_PREFIX,
    EXIT_PREFIX,
    ChainProxyManager,
)
from backend.core.s02_tools.builtin.proxy_chain_tools import create_proxy_chain_tool

from .proxy_chain_test_support import (
    FakeChainAPI,
    make_chain_config,
    make_config,
    make_proxy,
    make_temp_config_path,
    write_config,
)


async def _fake_ensure_ok(*_args: object) -> str | None:
    return None


def test_add_exit_node_creates_node() -> None:
    source = make_config([], [{"name": "GLOBAL", "type": "select", "proxies": []}])
    result = ChainProxyManager.add_exit_node(
        source,
        "钀藉湴-缇庡浗",
        "trojan",
        "us.example.com",
        443,
        "pass",
    )
    assert source["proxies"] == []
    assert result["proxies"][0]["name"] == f"{EXIT_PREFIX}钀藉湴-缇庡浗"
    assert f"{EXIT_PREFIX}钀藉湴-缇庡浗" in result["proxy-groups"][0]["proxies"]


def test_add_exit_node_updates_existing() -> None:
    source = make_config([make_proxy(f"{EXIT_PREFIX}钀藉湴", "trojan", server="old.example.com")])
    result = ChainProxyManager.add_exit_node(
        source,
        f"{EXIT_PREFIX}钀藉湴",
        "trojan",
        "new.example.com",
        443,
        "pass",
    )
    assert len(result["proxies"]) == 1
    assert result["proxies"][0]["server"] == "new.example.com"


def test_remove_exit_node_removes_references() -> None:
    standby = make_proxy("澶囩敤")
    standby["dialer-proxy"] = f"{EXIT_PREFIX}钀藉湴"
    source = make_config(
        [make_proxy("棣欐腐A"), make_proxy(f"{EXIT_PREFIX}钀藉湴"), standby],
        [{"name": "GLOBAL", "type": "select", "proxies": ["棣欐腐A", f"{EXIT_PREFIX}钀藉湴"]}],
    )
    result = ChainProxyManager.remove_exit_node(source, "钀藉湴")
    assert [proxy["name"] for proxy in result["proxies"]] == ["棣欐腐A", "澶囩敤"]
    assert result["proxy-groups"][0]["proxies"] == ["棣欐腐A"]
    assert "dialer-proxy" not in result["proxies"][1]


def test_set_chain_creates_virtual_nodes() -> None:
    source = make_chain_config(["棣欐腐A", "棣欐腐B", "鏃ユ湰A"], ["钀藉湴"])
    result, count = ChainProxyManager.set_chain(source, "钀藉湴")
    chains = [proxy for proxy in result["proxies"] if proxy["name"].startswith(CHAIN_PREFIX)]
    exit_proxy = next(proxy for proxy in result["proxies"] if proxy["name"] == f"{EXIT_PREFIX}钀藉湴")
    assert count == 3
    assert len(chains) == 3
    assert {proxy["dialer-proxy"] for proxy in chains} == {"棣欐腐A", "棣欐腐B", "鏃ユ湰A"}
    assert "dialer-proxy" not in exit_proxy
    assert next(group for group in result["proxy-groups"] if group["name"] == CHAIN_GROUP_NAME)


def test_set_chain_with_pattern_and_explicit_nodes() -> None:
    source = make_chain_config(["棣欐腐A", "棣欐腐B", "鏃ユ湰A", "鏃ユ湰B"], ["钀藉湴"])
    _, pattern_count = ChainProxyManager.set_chain(source, "钀藉湴", transit_pattern="棣欐腐")
    result, explicit_count = ChainProxyManager.set_chain(
        source,
        "钀藉湴",
        transit_nodes=["棣欐腐A", "鏃ユ湰A"],
    )
    assert pattern_count == 2
    assert explicit_count == 2
    assert {item["transit"] for item in ChainProxyManager.list_chains(result)} == {"棣欐腐A", "鏃ユ湰A"}


def test_remove_chain_all_and_specific_exit() -> None:
    source, _ = ChainProxyManager.set_chain(
        make_chain_config(["棣欐腐A", "鏃ユ湰A"], ["钀藉湴A", "钀藉湴B"]),
        "钀藉湴A",
    )
    source, _ = ChainProxyManager.set_chain(source, "钀藉湴B", transit_pattern="鏃ユ湰")
    removed_all, removed_count = ChainProxyManager.remove_chain(source)
    kept, kept_count = ChainProxyManager.remove_chain(source, "钀藉湴A")
    assert removed_count == 3
    assert not [proxy for proxy in removed_all["proxies"] if proxy["name"].startswith(CHAIN_PREFIX)]
    assert kept_count == 2
    assert any("钀藉湴B" in item["name"] for item in ChainProxyManager.list_chains(kept))


def test_list_chains_and_exit_nodes() -> None:
    source, _ = ChainProxyManager.set_chain(make_chain_config(["棣欐腐A"], ["钀藉湴", "钀藉湴2"]), "钀藉湴")
    chains = ChainProxyManager.list_chains(source)
    exits = ChainProxyManager.list_exit_nodes(source)
    assert chains[0]["transit"] == "棣欐腐A"
    assert chains[0]["exit"] == f"{EXIT_PREFIX}钀藉湴"
    assert [item["name"] for item in exits] == [f"{EXIT_PREFIX}钀藉湴", f"{EXIT_PREFIX}钀藉湴2"]


@pytest.mark.asyncio
async def test_chain_tool_add_exit_and_set_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = make_temp_config_path()
    write_config(config_path, make_chain_config(["棣欐腐A", "鏃ユ湰A"], []))
    api = FakeChainAPI()
    monkeypatch.setattr(proxy_chain_tools, "_ensure_mihomo_running", _fake_ensure_ok)
    monkeypatch.setattr(proxy_chain_tools, "_get_api", lambda *_args: api)
    _, execute = create_proxy_chain_tool(str(config_path))
    add_result = await execute(
        {
            "action": "add_exit",
            "name": "钀藉湴",
            "type": "trojan",
            "server": "us.example.com",
            "port": 443,
            "password": "pass",
            "sni": "us.example.com",
        }
    )
    set_result = await execute({"action": "set", "exit_node": "钀藉湴", "transit_pattern": "棣欐腐"})
    assert add_result.is_error is False and "Exit node added" in add_result.output
    assert set_result.is_error is False and "Chain nodes created: 1" in set_result.output
    assert api.paths and Path(api.paths[-1]).is_absolute()


@pytest.mark.asyncio
async def test_chain_tool_list_and_virtual_node_correctness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = make_temp_config_path()
    source, _ = ChainProxyManager.set_chain(
        make_chain_config(["棣欐腐A", "鏃ユ湰A"], ["钀藉湴"]),
        "钀藉湴",
        transit_nodes=["棣欐腐A"],
    )
    write_config(config_path, source)
    monkeypatch.setattr(proxy_chain_tools, "_get_api", lambda *_args: FakeChainAPI())
    _, execute = create_proxy_chain_tool(str(config_path))
    result = await execute({"action": "list"})
    chain = ChainProxyManager.list_chains(source)[0]
    virtual = next(proxy for proxy in source["proxies"] if proxy["name"] == chain["name"])
    exit_proxy = next(proxy for proxy in source["proxies"] if proxy["name"] == f"{EXIT_PREFIX}钀藉湴")
    assert result.is_error is False and chain["name"] in result.output
    assert virtual["dialer-proxy"] == "棣欐腐A"
    assert "dialer-proxy" not in exit_proxy


def test_register_builtin_tools_adds_proxy_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "mihomo_config_path", str(make_temp_config_path()))
    registry = ToolRegistry()
    register_builtin_tools(registry, workspace=None, mode="readonly")
    assert registry.has("proxy_chain")
