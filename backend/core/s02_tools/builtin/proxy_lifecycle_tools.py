from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult
from backend.config.settings import settings as app_settings

from .proxy_api import MihomoAPI
from .proxy_lifecycle import ProxyLifecycle, ProxyLifecycleError
from .proxy_models import ProxyLifecycleConfig
from .proxy_tool_support import DEFAULT_TEST_URL, format_test_output

DEFAULT_API_URL = "http://127.0.0.1:9090"
_proxy_lifecycle: ProxyLifecycle | None = None


class ProxyOnArgs(BaseModel):
    force: bool = False
    test: bool = True
    group: str = "GLOBAL"
    timeout: int = 5000


def create_proxy_on_tool(
    mihomo_path: str,
    config_path: str,
    work_dir: str,
    sub_path: str,
    custom_nodes_path: str,
    api_url: str = DEFAULT_API_URL,
    secret: str = "",
) -> tuple[ToolDefinition, ToolExecuteFn]:
    config = ProxyLifecycleConfig(
        mihomo_path=mihomo_path,
        config_path=config_path,
        work_dir=work_dir,
        sub_path=sub_path,
        custom_nodes_path=custom_nodes_path,
        api_url=api_url,
        api_secret=secret,
    )
    definition = ToolDefinition(
        name="proxy_on",
        description=(
            "Start the mihomo proxy service: detects and uses systemd service if available, "
            "otherwise falls back to process management. Defaults to existing config without "
            "rewriting files or changing Linux global proxy environment. When force=true, "
            "regenerates config from subscription and restarts the service. For systemd "
            "TUN mode, no environment variables are set as TUN provides transparent proxying. "
            "Runs a delay test by default after startup. Use this tool whenever the user asks "
            "to enable, start, or turn on proxy, TUN mode, or mihomo. "
            "Do NOT start mihomo via the Bash tool because it will time out."
        ),
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "force": {
                    "type": "boolean",
                    "description": "Force service restart and config regeneration. Defaults to false.",
                },
                "test": {"type": "boolean", "description": "Run delay test after startup. Defaults to true."},
                "group": {"type": "string", "description": "Proxy group to test. Defaults to GLOBAL."},
                "timeout": {"type": "integer", "description": "Delay test timeout in milliseconds."},
            },
            required=[],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            params = ProxyOnArgs.model_validate(args)
            output = await _get_lifecycle(config).start(params.force)
            # 启动后自动切换到 Chain 组（如果存在）
            switch_result = await _auto_select_chain(config)
            if switch_result:
                output = f"{output}\n{switch_result}"
            if params.test:
                output = await _append_delay_test(output, config, params.group, params.timeout)
            return ToolResult(output=output)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def create_proxy_off_tool() -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="proxy_off",
        description=(
            "Stop the mihomo proxy service: uses systemctl stop if systemd service exists, "
            "otherwise kills the mihomo process. For systemd mode (TUN), this simply stops "
            "the service as TUN mode does not use environment variables. Use this tool "
            "whenever the user asks to disable, stop, or turn off proxy, TUN mode, or mihomo."
        ),
        category="shell",
        parameters=ToolParameterSchema(properties={}, required=[]),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            _ = args
            return ToolResult(output=await _get_lifecycle().stop())
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def _get_lifecycle(config: ProxyLifecycleConfig | None = None) -> ProxyLifecycle:
    global _proxy_lifecycle
    resolved = config or _build_lifecycle_config()
    if resolved is None:
        raise ProxyLifecycleError("Missing mihomo lifecycle config")
    if _proxy_lifecycle is None or _proxy_lifecycle._config != resolved:
        _proxy_lifecycle = ProxyLifecycle(resolved)
    return _proxy_lifecycle


def _build_lifecycle_config() -> ProxyLifecycleConfig | None:
    mihomo_path = _read_setting("MIHOMO_PATH", "mihomo_path")
    config_path = _read_setting("MIHOMO_CONFIG_PATH", "mihomo_config_path")
    if not mihomo_path or not config_path:
        return None
    config_dir = Path(config_path).resolve().parent
    return ProxyLifecycleConfig(
        mihomo_path=mihomo_path,
        config_path=config_path,
        work_dir=_read_setting("MIHOMO_WORK_DIR", "mihomo_work_dir") or str(config_dir),
        sub_path=_read_setting("MIHOMO_SUB_PATH", "mihomo_sub_path")
        or str(config_dir / "sub_raw.yaml"),
        custom_nodes_path=_read_setting("MIHOMO_CUSTOM_NODES_PATH", "mihomo_custom_nodes_path")
        or str(config_dir / "custom_nodes.yaml"),
        api_url=_read_setting("MIHOMO_API_URL", "mihomo_api_url") or DEFAULT_API_URL,
        api_secret=_read_setting("MIHOMO_SECRET", "mihomo_secret"),
    )


def _read_setting(env_name: str, settings_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    return str(getattr(app_settings, settings_name, "") or "").strip()


async def _append_delay_test(
    output: str,
    config: ProxyLifecycleConfig,
    group: str,
    timeout: int,
) -> str:
    api = MihomoAPI(config.api_url, config.api_secret)
    result = await api.test_group_delay(group or "GLOBAL", timeout, DEFAULT_TEST_URL)
    if result.results:
        return f"{output}\n\n{format_test_output(result, group or 'GLOBAL')}"
    return f"{output}\n\nDelay test complete\nGroup: {group or 'GLOBAL'}\nResult: no reachable nodes"


async def _auto_select_chain(config: ProxyLifecycleConfig) -> str:
    """启动后自动将 GLOBAL 组切换到 Chain（如果 Chain 组存在且有节点）。"""
    try:
        api = MihomoAPI(config.api_url, config.api_secret)
        status = await api.get_proxies()
        chain_group = next((g for g in status.groups if g.name == "Chain"), None)
        if not chain_group or not chain_group.all:
            return ""
        # 检查 GLOBAL 组当前选择
        global_group = next((g for g in status.groups if g.name == "GLOBAL"), None)
        if global_group and global_group.now == "Chain":
            return ""
        # 切换到 Chain
        success = await api.switch_proxy("GLOBAL", "Chain")
        if success:
            return "Auto-switched GLOBAL to Chain"
        return ""
    except Exception:  # noqa: BLE001
        return ""


__all__ = ["create_proxy_off_tool", "create_proxy_on_tool"]
