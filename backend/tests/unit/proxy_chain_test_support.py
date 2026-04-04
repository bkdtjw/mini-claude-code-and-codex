from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from backend.core.s02_tools.builtin.proxy_chain import EXIT_PREFIX


def make_proxy(
    name: str,
    proxy_type: str = "ss",
    server: str = "example.com",
    port: int = 443,
    **extra: Any,
) -> dict[str, Any]:
    proxy = {"name": name, "type": proxy_type, "server": server, "port": port}
    proxy.update(extra)
    return proxy


def make_config(
    proxies: list[dict[str, Any]],
    groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    default_groups = [
        {
            "name": "GLOBAL",
            "type": "select",
            "proxies": [str(proxy.get("name") or "") for proxy in proxies],
        }
    ]
    return {
        "external-controller": "127.0.0.1:9090",
        "proxies": proxies,
        "proxy-groups": groups or default_groups,
    }


def make_chain_config(transits: list[str], exits: list[str]) -> dict[str, Any]:
    proxies = [make_proxy(name) for name in transits]
    proxies.extend(make_proxy(f"{EXIT_PREFIX}{name}", "trojan") for name in exits)
    return make_config(proxies)


def write_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def make_temp_config_path() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_proxy_chain"
    path = root / uuid4().hex / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class FakeChainAPI:
    def __init__(self, reload_success: bool = True) -> None:
        self.reload_success = reload_success
        self.paths: list[str] = []

    async def reload_config(self, config_path: str) -> bool:
        self.paths.append(config_path)
        return self.reload_success


__all__ = ["FakeChainAPI", "make_config", "make_proxy", "make_temp_config_path", "write_config"]
