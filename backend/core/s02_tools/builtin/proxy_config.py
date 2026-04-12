from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

import yaml

from .proxy_subscription import parse_subscription_yaml


class ConfigError(Exception):
    """Config generation or validation error."""


class ProxyConfigGenerator:
    """Generate and update mihomo config files."""

    def __init__(self, config_path: str, backup: bool = True) -> None:
        self._config_path = Path(config_path)
        self._backup = backup
        self._last_backup_path = ""

    @property
    def last_backup_path(self) -> str:
        return self._last_backup_path

    def load(self) -> dict[str, Any]:
        try:
            if not self._config_path.exists():
                return {}
            with open(self._config_path, "r", encoding="utf-8") as handle:
                text = handle.read()
            return parse_subscription_yaml(text)
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"Failed to read config: {exc}") from exc

    def save(self, config: dict[str, Any]) -> str:
        try:
            self._last_backup_path = ""
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            if self._backup and self._config_path.exists():
                backup_path = Path(f"{self._config_path}.bak")
                shutil.copy2(self._config_path, backup_path)
                self._last_backup_path = str(backup_path)
            with open(self._config_path, "w", encoding="utf-8") as handle:
                handle.write(_dump_yaml(config))
            self._verify_saved_config()
            return str(self._config_path)
        except ConfigError:
            if self._last_backup_path:
                shutil.copy2(self._last_backup_path, self._config_path)
            raise
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"Failed to write config: {exc}") from exc

    def generate_from_subscription(
        self,
        subscription_data: dict[str, Any],
        smux_config: dict[str, Any] | None = None,
        dns_config: dict[str, Any] | None = None,
        global_opts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        proxies = copy.deepcopy(subscription_data.get("proxies") or [])
        if not isinstance(proxies, list) or not proxies:
            raise ConfigError("Subscription config must contain at least one proxy.")
        if smux_config is not None:
            proxies = self.inject_smux(proxies, **smux_config)
        config = copy.deepcopy(global_opts or self.default_global_opts())
        config["proxies"] = proxies
        config["proxy-groups"] = [{"name": "GLOBAL", "type": "select", "proxies": _proxy_names(proxies)}]
        config["rules"] = ["MATCH,GLOBAL"]
        if dns_config:
            config["dns"] = copy.deepcopy(dns_config)
        return config

    @staticmethod
    def inject_smux(
        proxies: list[dict[str, Any]],
        protocol: str = "h2mux",
        max_connections: int = 4,
        min_streams: int = 4,
        padding: bool = True,
        brutal_up: int = 50,
        brutal_down: int = 100,
    ) -> list[dict[str, Any]]:
        result = copy.deepcopy(proxies)
        for proxy in result:
            proxy_type = str(proxy.get("type") or "").lower()
            if proxy.get("smux") or proxy_type in {"direct", "reject"}:
                continue
            proxy["smux"] = {
                "enabled": True,
                "protocol": protocol,
                "max-connections": max_connections,
                "min-streams": min_streams,
                "padding": padding,
                "brutal-opts": {"enabled": True, "up": brutal_up, "down": brutal_down},
            }
        return result

    @staticmethod
    def remove_smux(proxies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = copy.deepcopy(proxies)
        for proxy in result:
            proxy.pop("smux", None)
        return result

    @staticmethod
    def default_dns_config() -> dict[str, Any]:
        return {
            "enable": True,
            "enhanced-mode": "fake-ip",
            "fake-ip-range": "198.18.0.1/16",
            "default-nameserver": ["223.5.5.5", "119.29.29.29"],
            "proxy-server-nameserver": [
                "https://1.0.0.1/dns-query",
                "https://doh.pub/dns-query",
                "1.1.1.1",
            ],
            "nameserver": ["https://doh.pub/dns-query", "https://dns.alidns.com/dns-query"],
            "fallback": ["https://1.0.0.1/dns-query", "https://8.8.4.4/dns-query"],
            "fallback-filter": {"geoip": True, "geoip-code": "CN"},
        }

    @staticmethod
    def default_global_opts() -> dict[str, Any]:
        return {
            "mixed-port": 7890,
            "allow-lan": False,
            "mode": "rule",
            "log-level": "info",
            "external-controller": "127.0.0.1:9090",
            "tcp-concurrent": True,
            "unified-delay": True,
            "keep-alive-interval": 30,
            "find-process-mode": "strict",
        }

    def _verify_saved_config(self) -> None:
        try:
            with open(self._config_path, "r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle)
            if not isinstance(data, dict):
                raise ConfigError("Config file is not a valid YAML object.")
            proxies = data.get("proxies")
            if not isinstance(proxies, list) or not proxies:
                raise ConfigError("Config file proxies list is empty.")
            dns = data.get("dns", {})
            if isinstance(dns, dict) and dns.get("enhanced-mode") == "fake-ip":
                if not isinstance(dns.get("proxy-server-nameserver"), list) or not dns.get(
                    "proxy-server-nameserver"
                ):
                    raise ConfigError("fake-ip mode requires proxy-server-nameserver")
                if not isinstance(dns.get("default-nameserver"), list) or not dns.get("default-nameserver"):
                    raise ConfigError("fake-ip mode requires default-nameserver")
            if not str(data.get("external-controller") or "").strip():
                raise ConfigError("Config file is missing external-controller")
        except ConfigError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"Failed to validate config file: {exc}") from exc


def _dump_yaml(config: dict[str, Any]) -> str:
    return yaml.dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _proxy_names(proxies: list[dict[str, Any]]) -> list[str]:
    return [str(proxy.get("name") or "") for proxy in proxies if str(proxy.get("name") or "").strip()]


__all__ = ["ConfigError", "ProxyConfigGenerator"]
