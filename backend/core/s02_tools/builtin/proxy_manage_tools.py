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
        description="切换代理节点，支持模糊匹配节点名",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "node": {"type": "string", "description": "目标节点名称或关键词"},
                "group": {"type": "string", "description": "代理组名称，默认 GLOBAL"},
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
                raise ProxyToolError(f"未找到代理组: {params.group}")
            matches = fuzzy_match(params.node, group.all)
            if not matches:
                raise ProxyToolError(f"未找到匹配节点: {params.node}")
            target = matches[0]
            if not await api.switch_proxy(params.group, target):
                raise ProxyToolError(f"切换节点失败: {target}")
            delay = await api.get_delay(target)
            lines = [
                f"已切换到: {target}",
                f"代理组: {params.group}",
                f"当前延迟: {format_delay(delay)}",
            ]
            if params.node != target:
                node_map = {node.name: node for node in status.nodes}
                lines[0] = f"已切换到: {target}（匹配关键词: {params.node}）"
                similar = [
                    f"{name}({format_delay(node_map.get(name).delay if node_map.get(name) else 0)})"
                    for name in matches[1:4]
                ]
                if similar:
                    lines.append(f"其他相似节点: {', '.join(similar)}")
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
        description="导入订阅、按需注入 smux，或移除已有 smux 配置",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "action": {"type": "string", "description": "inject | remove | import"},
                "subscription_url": {"type": "string", "description": "订阅链接，仅 import 时必填"},
                "up": {"type": "integer", "description": "上行带宽 Mbps，默认 50"},
                "down": {"type": "integer", "description": "下行带宽 Mbps，默认 100"},
                "protocol": {"type": "string", "description": "smux 协议，默认 h2mux"},
                "smux": {"type": "boolean", "description": "导入时是否注入 smux，默认 false"},
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
                    {
                        "protocol": params.protocol,
                        "brutal_up": params.up,
                        "brutal_down": params.down,
                    }
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
                raise ProxyToolError("当前配置缺少 proxies 列表")
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
                    "配置优化完成",
                    f"注入 smux 节点数: {changed}（已跳过 {existing} 个已有配置）",
                    f"协议: {params.protocol} | brutal: up={params.up} down={params.down}",
                ]
            else:
                current["proxies"] = generator.remove_smux(proxies)
                lines = ["已移除 smux 配置", f"影响节点数: {_count_smux(proxies)}"]
            path = str(Path(generator.save(current)).resolve())
            if generator.last_backup_path:
                lines.append(f"备份文件: {generator.last_backup_path}")
            lines.append(
                "mihomo 已重载配置"
                if await api.reload_config(path)
                else "配置已写入，请手动重载 mihomo"
            )
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
    lines = ["订阅导入成功", f"节点数量: {len(config.get('proxies') or [])}"]
    if params.smux:
        lines.append(f"已注入 smux({params.protocol})，brutal up={params.up} down={params.down}")
    else:
        lines.append("未注入 smux，保留原始节点协议参数")
    lines.append(f"配置文件: {path}")
    if generator.last_backup_path:
        lines.append(f"备份文件: {generator.last_backup_path}")
    lines.append(
        "mihomo 已重载配置"
        if await api.reload_config(path)
        else "配置已写入，请手动重载 mihomo"
    )
    return "\n".join(lines)


def _count_smux(proxies: list[object]) -> int:
    return sum(1 for proxy in proxies if isinstance(proxy, dict) and proxy.get("smux"))


__all__ = ["create_proxy_optimize_tool", "create_proxy_switch_tool"]
