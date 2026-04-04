from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from .proxy_api import MihomoAPI
from .proxy_auto_start import _ensure_mihomo_running
from .proxy_chain import EXIT_PREFIX, ChainProxyManager
from .proxy_chain_support import (
    AddExitArgs,
    RemoveChainArgs,
    RemoveExitArgs,
    SetChainArgs,
    format_add_exit_output,
    format_list_output,
    format_remove_exit_output,
    format_remove_output,
    format_set_output,
    parse_chain_args,
)
from .proxy_config import ProxyConfigGenerator

DEFAULT_API_URL = "http://127.0.0.1:9090"
_mihomo_api: MihomoAPI | None = None


def _get_api(api_url: str = DEFAULT_API_URL, secret: str = "") -> MihomoAPI:
    global _mihomo_api
    if _mihomo_api is None or getattr(_mihomo_api, "_base_url", "") != api_url.rstrip("/"):
        _mihomo_api = MihomoAPI(api_url, secret)
    elif getattr(_mihomo_api, "_secret", "") != secret.strip():
        _mihomo_api = MihomoAPI(api_url, secret)
    return _mihomo_api


def create_proxy_chain_tool(
    config_path: str,
    api_url: str = DEFAULT_API_URL,
    secret: str = "",
) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="proxy_chain",
        description="管理链式代理，支持落地节点维护、链式创建、删除和查看",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "action": {
                    "type": "string",
                    "description": "add_exit | remove_exit | set | remove | list",
                },
                "name": {"type": "string", "description": "落地节点名称"},
                "type": {"type": "string", "description": "协议类型，默认 trojan"},
                "server": {"type": "string", "description": "服务器地址"},
                "port": {"type": "integer", "description": "端口"},
                "password": {"type": "string", "description": "节点密码"},
                "sni": {"type": "string", "description": "TLS SNI"},
                "skip_cert_verify": {"type": "boolean", "description": "是否跳过证书校验"},
                "extra": {"type": "object", "description": "协议额外参数"},
                "exit_node": {"type": "string", "description": "落地节点名称"},
                "transit_pattern": {"type": "string", "description": "中转节点模糊匹配关键词"},
                "transit_nodes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "指定中转节点列表",
                },
            },
            required=["action"],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            parsed = parse_chain_args(args)
            generator = ProxyConfigGenerator(config_path)
            config = generator.load()
            api = _get_api(api_url, secret)
            if isinstance(parsed, AddExitArgs):
                updated = ChainProxyManager.add_exit_node(
                    config,
                    parsed.name,
                    parsed.type,
                    parsed.server,
                    parsed.port,
                    parsed.password,
                    parsed.sni,
                    parsed.skip_cert_verify,
                    parsed.extra,
                )
                node = next(
                    item
                    for item in ChainProxyManager.list_exit_nodes(updated)
                    if item["name"] == _with_exit_prefix(parsed.name)
                )
                output = format_add_exit_output(node)
                return ToolResult(
                    output=await _save_and_reload(generator, api, updated, output)
                )
            if isinstance(parsed, RemoveExitArgs):
                updated = ChainProxyManager.remove_exit_node(config, parsed.name)
                return ToolResult(
                    output=await _save_and_reload(
                        generator,
                        api,
                        updated,
                        format_remove_exit_output(_with_exit_prefix(parsed.name)),
                    )
                )
            if isinstance(parsed, SetChainArgs):
                err = await _ensure_mihomo_running(api_url, secret)
                if err:
                    return ToolResult(output=err, is_error=True)
                updated, created = ChainProxyManager.set_chain(
                    config,
                    parsed.exit_node,
                    parsed.transit_nodes or None,
                    parsed.transit_pattern or None,
                )
                chains = [
                    item
                    for item in ChainProxyManager.list_chains(updated)
                    if item["exit"] == _with_exit_prefix(parsed.exit_node)
                ]
                mode = _describe_mode(parsed.transit_nodes, parsed.transit_pattern)
                output = format_set_output(
                    _with_exit_prefix(parsed.exit_node),
                    created,
                    mode,
                    chains,
                )
                return ToolResult(
                    output=await _save_and_reload(generator, api, updated, output)
                )
            if isinstance(parsed, RemoveChainArgs):
                err = await _ensure_mihomo_running(api_url, secret)
                if err:
                    return ToolResult(output=err, is_error=True)
                updated, removed = ChainProxyManager.remove_chain(config, parsed.exit_node or None)
                exit_name = _with_exit_prefix(parsed.exit_node) if parsed.exit_node else None
                output = format_remove_output(removed, exit_name)
                return ToolResult(
                    output=await _save_and_reload(generator, api, updated, output)
                )
            return ToolResult(
                output=format_list_output(
                    ChainProxyManager.list_exit_nodes(config),
                    ChainProxyManager.list_chains(config),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


async def _save_and_reload(
    generator: ProxyConfigGenerator,
    api: MihomoAPI,
    config: dict[str, Any],
    output: str,
) -> str:
    path = str(Path(generator.save(config)).resolve())
    suffix = (
        "mihomo 已重载配置"
        if await api.reload_config(path)
        else "配置已写入，请手动重载 mihomo"
    )
    return f"{output}\n{suffix}"


def _with_exit_prefix(name: str) -> str:
    return name if name.startswith(EXIT_PREFIX) else f"{EXIT_PREFIX}{name}"


def _describe_mode(transit_nodes: list[str], transit_pattern: str) -> str:
    if transit_nodes:
        return f"指定 {len(transit_nodes)} 个中转节点"
    if transit_pattern:
        return f"匹配“{transit_pattern}”的节点"
    return "全部非落地节点"


__all__ = ["create_proxy_chain_tool"]
