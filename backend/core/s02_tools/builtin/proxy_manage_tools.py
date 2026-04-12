from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from .proxy_api import MihomoAPI
from .proxy_auto_start import _ensure_mihomo_running
from .proxy_config import ProxyConfigGenerator
from .proxy_subscription import load_subscription
from .proxy_tool_support import (
    OFFLINE_MESSAGE,
    ProxyOptimizeArgs,
    ProxyToolError,
    format_delay,
    fuzzy_match,
    parse_optimize_args,
    parse_switch_args,
)

DEFAULT_API_URL = "http://127.0.0.1:9090"
_mihomo_api: MihomoAPI | None = None


def _get_api(api_url: str = DEFAULT_API_URL, secret: str = "") -> MihomoAPI:
    global _mihomo_api
    if _mihomo_api is None or getattr(_mihomo_api, "_base_url", "") != api_url.rstrip("/"):
        _mihomo_api = MihomoAPI(api_url, secret)
    elif getattr(_mihomo_api, "_secret", "") != secret.strip():
        _mihomo_api = MihomoAPI(api_url, secret)
    return _mihomo_api


def create_proxy_switch_tool(
    api_url: str = DEFAULT_API_URL,
    secret: str = "",
) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="proxy_switch",
        description="Switch proxy nodes with fuzzy matching.",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "node": {"type": "string", "description": "Target node name or keyword"},
                "group": {"type": "string", "description": "Proxy group name. Defaults to GLOBAL"},
            },
            required=["node"],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            err = await _ensure_mihomo_running(api_url, secret)
            if err:
                return ToolResult(output=err, is_error=True)
            params = parse_switch_args(args)
            api = _get_api(api_url, secret)
            status = await api.get_proxies()
            if not status.groups and not await api.get_version():
                raise ProxyToolError(OFFLINE_MESSAGE)
            group = next((item for item in status.groups if item.name == params.group), None)
            if group is None:
                raise ProxyToolError(f"Proxy group {params.group} not found")
            matches = fuzzy_match(params.node, group.all)
            if not matches:
                raise ProxyToolError(f"No matching nodes found for: {params.node}")
            target = matches[0]
            if not await api.switch_proxy(params.group, target):
                raise ProxyToolError(f"Failed to switch to node: {target}")
            delay = await api.get_delay(target)
            lines = [
                f"Switched to: {target}",
                f"Group: {params.group}",
                f"Current delay: {format_delay(delay)}",
            ]
            if params.node != target:
                lines.append(f"Matched keyword: {params.node}")
                node_map = {node.name: node for node in status.nodes}
                similar = [
                    f"{name}({format_delay(node_map.get(name).delay if node_map.get(name) else 0)})"
                    for name in matches[1:4]
                ]
                if similar:
                    lines.append(f"Similar nodes: {', '.join(similar)}")
            return ToolResult(output="\n".join(lines))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def create_proxy_optimize_tool(
    config_path: str = "",
    api_url: str = DEFAULT_API_URL,
    secret: str = "",
) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="proxy_optimize",
        description="Import subscriptions, inject smux, or remove existing smux config.",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "action": {"type": "string", "description": "inject | remove | import"},
                "subscription_url": {"type": "string", "description": "Subscription URL. Required for import"},
                "up": {"type": "integer", "description": "Upload bandwidth in Mbps. Defaults to 50"},
                "down": {"type": "integer", "description": "Download bandwidth in Mbps. Defaults to 100"},
                "protocol": {"type": "string", "description": "smux protocol. Defaults to h2mux"},
                "smux": {"type": "boolean", "description": "Inject smux during import. Defaults to false"},
            },
            required=["action"],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            err = await _ensure_mihomo_running(api_url, secret)
            if err:
                return ToolResult(output=err, is_error=True)
            params = parse_optimize_args(args)
            generator = ProxyConfigGenerator(config_path)
            api = _get_api(api_url, secret)
            if params.action == "import":
                data = await load_subscription(params.subscription_url)
                smux_config = (
                    {"protocol": params.protocol, "brutal_up": params.up, "brutal_down": params.down}
                    if params.smux
                    else None
                )
                config = generator.generate_from_subscription(
                    data,
                    smux_config=smux_config,
                    dns_config=ProxyConfigGenerator.default_dns_config(),
                    global_opts=ProxyConfigGenerator.default_global_opts(),
                )
                return ToolResult(output=await _save_and_reload(api, generator, config, params))
            current = generator.load()
            proxies = current.get("proxies")
            if not isinstance(proxies, list):
                raise ProxyToolError("Current config is missing a proxies list")
            if params.action == "inject":
                existing = _count_smux(proxies)
                current["proxies"] = generator.inject_smux(
                    proxies,
                    protocol=params.protocol,
                    brutal_up=params.up,
                    brutal_down=params.down,
                )
                changed = _count_smux(current["proxies"]) - existing
                lines = [
                    "Config optimized",
                    f"Injected smux into {changed} nodes (skipped {existing} already configured)",
                    f"Protocol: {params.protocol} | brutal: up={params.up} down={params.down}",
                ]
            else:
                current["proxies"] = generator.remove_smux(proxies)
                lines = ["smux config removed", f"Affected nodes: {_count_smux(proxies)}"]
            path = str(Path(generator.save(current)).resolve())
            if generator.last_backup_path:
                lines.append(f"Backup file: {generator.last_backup_path}")
            lines.append("mihomo reloaded" if await api.reload_config(path) else "Config saved. Reload mihomo manually.")
            return ToolResult(output="\n".join(lines))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


async def _save_and_reload(
    api: MihomoAPI,
    generator: ProxyConfigGenerator,
    config: dict[str, Any],
    params: ProxyOptimizeArgs,
) -> str:
    path = str(Path(generator.save(config)).resolve())
    lines = ["Subscription imported", f"Node count: {len(config.get('proxies') or [])}"]
    if params.smux:
        lines.append(f"smux injected ({params.protocol}), brutal up={params.up} down={params.down}")
    else:
        lines.append("smux not injected; preserved original proxy settings")
    lines.append(f"Config file: {path}")
    if generator.last_backup_path:
        lines.append(f"Backup file: {generator.last_backup_path}")
    lines.append("mihomo reloaded" if await api.reload_config(path) else "Config saved. Reload mihomo manually.")
    return "\n".join(lines)


def _count_smux(proxies: list[object]) -> int:
    return sum(1 for proxy in proxies if isinstance(proxy, dict) and proxy.get("smux"))


__all__ = ["create_proxy_optimize_tool", "create_proxy_switch_tool"]
