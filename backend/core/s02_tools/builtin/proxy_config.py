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
            text = self._config_path.read_text(encoding="utf-8")
            return parse_subscription_yaml(text)
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"读取配置失败: {exc}") from exc

    def save(self, config: dict[str, Any]) -> str:
        try:
            self._last_backup_path = ""
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            if self._backup and self._config_path.exists():
                backup_path = Path(f"{self._config_path}.bak")
                shutil.copy2(self._config_path, backup_path)
                self._last_backup_path = str(backup_path)
            self._config_path.write_text(_dump_yaml(config), encoding="utf-8")
            self._verify_saved_config()
            return str(self._config_path)
        except ConfigError:
            if self._last_backup_path:
                shutil.copy2(self._last_backup_path, self._config_path)
            raise
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"写入配置失败: {exc}") from exc

    def generate_from_subscription(
        self,
        subscription_data: dict[str, Any],
        smux_config: dict[str, Any] | None = None,
        dns_config: dict[str, Any] | None = None,
        global_opts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        proxies = copy.deepcopy(subscription_data.get("proxies") or [])
        if not isinstance(proxies, list) or not proxies:
            raise ConfigError("订阅配置缺少可用节点")
        if smux_config is not None:
            proxies = self.inject_smux(proxies, **smux_config)
        config = copy.deepcopy(global_opts or self.default_global_opts())
        config["proxies"] = proxies
        config["proxy-groups"] = [
            {"name": "GLOBAL", "type": "select", "proxies": _proxy_names(proxies)}
        ]
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
            "proxy-server-nameserver": ["223.5.5.5", "119.29.29.29"],
            "nameserver": ["https://doh.pub/dns-query", "https://dns.alidns.com/dns-query"],
            "fallback": ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"],
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
            data = yaml.safe_load(self._config_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ConfigError("配置文件格式无效：不是有效的 YAML 对象")
            proxies = data.get("proxies")
            if not isinstance(proxies, list) or not proxies:
                raise ConfigError("配置文件 proxies 列表为空")
            dns = data.get("dns", {})
            if isinstance(dns, dict) and dns.get("enhanced-mode") == "fake-ip":
                nameservers = dns.get("proxy-server-nameserver")
                if not isinstance(nameservers, list) or not nameservers:
                    raise ConfigError("fake-ip 模式下缺少 proxy-server-nameserver")
            if not str(data.get("external-controller") or "").strip():
                raise ConfigError("配置文件缺少 external-controller")
        except ConfigError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"配置文件验证失败: {exc}") from exc


def _dump_yaml(config: dict[str, Any]) -> str:
    return yaml.safe_dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _proxy_names(proxies: list[dict[str, Any]]) -> list[str]:
    return [
        str(proxy.get("name") or "")
        for proxy in proxies
        if str(proxy.get("name") or "").strip()
    ]


__all__ = ["ConfigError", "ProxyConfigGenerator"]
