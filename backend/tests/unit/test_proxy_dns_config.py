from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.core.s02_tools.builtin.proxy_config import ConfigError, ProxyConfigGenerator


def test_default_dns_config_has_ip_bootstrap_and_doh_resolvers() -> None:
    dns = ProxyConfigGenerator.default_dns_config()
    assert dns["default-nameserver"] == ["223.5.5.5", "119.29.29.29"]
    assert all("://" not in value for value in dns["default-nameserver"])
    assert any(value.startswith("https://") for value in dns["proxy-server-nameserver"])


def test_save_rejects_fake_ip_config_without_default_nameserver() -> None:
    generator = ProxyConfigGenerator(str(_make_temp_path()), backup=False)
    config = ProxyConfigGenerator.default_global_opts()
    config["proxies"] = [{"name": "JP1", "type": "ss", "server": "jp.example.com", "port": 443}]
    config["proxy-groups"] = [{"name": "GLOBAL", "type": "select", "proxies": ["JP1"]}]
    config["rules"] = ["MATCH,GLOBAL"]
    config["dns"] = ProxyConfigGenerator.default_dns_config()
    config["dns"].pop("default-nameserver", None)
    with pytest.raises(ConfigError, match="default-nameserver"):
        generator.save(config)


def _make_temp_path() -> Path:
    path = Path("tests/.tmp_proxy_dns") / uuid4().hex / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
