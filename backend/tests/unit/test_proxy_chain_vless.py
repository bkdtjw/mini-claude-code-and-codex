from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.core.s02_tools.builtin import proxy_chain_tools
from backend.core.s02_tools.builtin.proxy_chain import (
    CHAIN_PREFIX,
    EXIT_PREFIX,
    ChainProxyManager,
)
from backend.core.s02_tools.builtin.proxy_chain_tools import create_proxy_chain_tool

from .proxy_chain_test_support import (
    FakeChainAPI,
    make_chain_config,
    make_config,
    make_temp_config_path,
)


def test_add_exit_node_vless_reality_fields() -> None:
    result = ChainProxyManager.add_exit_node(
        make_config([], [{"name": "GLOBAL", "type": "select", "proxies": []}]),
        "Home-VPS",
        "vless",
        "67.216.207.8",
        443,
        "",
        "www.intel.com",
        False,
        {
            "uuid": "demo-uuid",
            "network": "tcp",
            "tls": True,
            "udp": True,
            "flow": "xtls-rprx-vision",
            "reality-opts": {"public-key": "demo-pk", "short-id": "demo-sid"},
            "client-fingerprint": "chrome",
        },
    )
    node = result["proxies"][0]
    assert node["name"] == f"{EXIT_PREFIX}Home-VPS"
    assert node["server"] == "67.216.207.8"
    assert node["uuid"] == "demo-uuid"
    assert node["servername"] == "www.intel.com"
    assert node["reality-opts"] == {"public-key": "demo-pk", "short-id": "demo-sid"}
    assert node["client-fingerprint"] == "chrome"
    assert "password" not in node


def test_set_chain_with_vless_exit_preserves_vless_fields() -> None:
    source = make_chain_config(["HK-A", "JP-A"], [])
    source = ChainProxyManager.add_exit_node(
        source,
        "Home-VPS",
        "vless",
        "67.216.207.8",
        443,
        "",
        "www.intel.com",
        False,
        {
            "uuid": "demo-uuid",
            "network": "tcp",
            "tls": True,
            "flow": "xtls-rprx-vision",
            "reality-opts": {"public-key": "demo-pk", "short-id": "demo-sid"},
        },
    )
    result, count = ChainProxyManager.set_chain(source, "Home-VPS", transit_nodes=["HK-A"])
    chain = next(proxy for proxy in result["proxies"] if proxy["name"].startswith(CHAIN_PREFIX))
    exit_proxy = next(
        proxy for proxy in result["proxies"] if proxy["name"] == f"{EXIT_PREFIX}Home-VPS"
    )
    assert count == 1
    assert chain["dialer-proxy"] == "HK-A"
    assert chain["uuid"] == "demo-uuid"
    assert chain["reality-opts"]["public-key"] == "demo-pk"
    assert exit_proxy["servername"] == "www.intel.com"
    assert "dialer-proxy" not in exit_proxy


@pytest.mark.asyncio
async def test_chain_tool_add_exit_supports_vless_args(monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = make_temp_config_path()
    config_path.write_text(
        yaml.safe_dump(make_chain_config(["HK-A"], []), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(proxy_chain_tools, "_get_api", lambda *_args: FakeChainAPI())
    _, execute = create_proxy_chain_tool(str(config_path))
    result = await execute(
        {
            "action": "add_exit",
            "name": "Home-VPS",
            "type": "vless",
            "server": "67.216.207.8",
            "port": 443,
            "sni": "www.intel.com",
            "uuid": "demo-uuid",
            "network": "tcp",
            "flow": "xtls-rprx-vision",
            "fingerprint": "chrome",
            "reality_public_key": "demo-pk",
            "reality_short_id": "demo-sid",
        }
    )
    saved = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    node = next(proxy for proxy in saved["proxies"] if proxy["name"] == f"{EXIT_PREFIX}Home-VPS")
    assert result.is_error is False
    assert node["uuid"] == "demo-uuid"
    assert node["servername"] == "www.intel.com"
    assert node["tls"] is True
    assert node["udp"] is True
    assert node["reality-opts"] == {"public-key": "demo-pk", "short-id": "demo-sid"}
    assert "password" not in node
