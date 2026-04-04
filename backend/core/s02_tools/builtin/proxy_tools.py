from __future__ import annotations

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from .proxy_api import MihomoAPI
from .proxy_auto_start import _ensure_mihomo_running
from .proxy_chain_tools import create_proxy_chain_tool
from .proxy_manage_tools import create_proxy_optimize_tool, create_proxy_switch_tool
from .proxy_tool_support import (
    DEFAULT_TEST_URL,
    OFFLINE_MESSAGE,
    ProxyToolError,
    format_status_output,
    format_test_output,
    parse_status_args,
    parse_test_args,
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


def create_proxy_status_tool(
    api_url: str = DEFAULT_API_URL,
    secret: str = "",
) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="proxy_status",
        description="查看当前代理状态、节点列表和延迟信息",
        category="shell",
        parameters=ToolParameterSchema(
            properties={"group": {"type": "string", "description": "仅查看指定代理组"}},
            required=[],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            err = await _ensure_mihomo_running(api_url, secret)
            if err:
                return ToolResult(output=err, is_error=True)
            params = parse_status_args(args)
            api = _get_api(api_url, secret)
            status = await api.get_proxies()
            version = await api.get_version()
            if not version and not status.groups and not status.nodes:
                raise ProxyToolError(OFFLINE_MESSAGE)
            return ToolResult(output=format_status_output(status, version, params.group))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def create_proxy_test_tool(
    api_url: str = DEFAULT_API_URL,
    secret: str = "",
) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="proxy_test",
        description="对代理组执行批量延迟测速并返回排序结果",
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "group": {"type": "string", "description": "代理组名称，默认 GLOBAL"},
                "timeout": {"type": "integer", "description": "超时时间（毫秒），默认 5000"},
                "url": {"type": "string", "description": f"测速 URL，默认 {DEFAULT_TEST_URL}"},
            },
            required=[],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            err = await _ensure_mihomo_running(api_url, secret)
            if err:
                return ToolResult(output=err, is_error=True)
            params = parse_test_args(args)
            api = _get_api(api_url, secret)
            result = await api.test_group_delay(params.group, params.timeout, params.url)
            if result.results:
                return ToolResult(output=format_test_output(result, params.group))
            if not await api.get_version():
                raise ProxyToolError(OFFLINE_MESSAGE)
            status = await api.get_proxies()
            available_groups = [group.name for group in status.groups]
            if params.group not in available_groups:
                names = ", ".join(available_groups) if available_groups else "无"
                raise ProxyToolError(f"代理组 {params.group} 不存在。可用代理组: {names}")
            raise ProxyToolError(f"代理组 {params.group} 中所有节点测速超时，请检查网络连通性")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


__all__ = [
    "ProxyToolError",
    "_ensure_mihomo_running",
    "create_proxy_chain_tool",
    "create_proxy_optimize_tool",
    "create_proxy_status_tool",
    "create_proxy_switch_tool",
    "create_proxy_test_tool",
]
