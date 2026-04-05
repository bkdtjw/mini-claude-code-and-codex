from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult
from backend.config.settings import settings as app_settings

from .proxy_lifecycle import ProxyLifecycle, ProxyLifecycleError
from .proxy_models import ProxyLifecycleConfig

DEFAULT_API_URL = "http://127.0.0.1:9090"
_proxy_lifecycle: ProxyLifecycle | None = None


class ProxyOnArgs(BaseModel):
    force: bool = True


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
            "Start proxy, regenerate config, restore custom nodes, and set the system proxy."
        ),
        category="shell",
        parameters=ToolParameterSchema(
            properties={
                "force": {
                    "type": "boolean",
                    "description": "Force config regeneration. Defaults to true.",
                }
            },
            required=[],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            params = ProxyOnArgs.model_validate(args)
            return ToolResult(output=await _get_lifecycle(config).start(params.force))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def create_proxy_off_tool() -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="proxy_off",
        description="Stop proxy and clear the system proxy.",
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
        custom_nodes_path=str(config_dir / "custom_nodes.yaml"),
        api_url=_read_setting("MIHOMO_API_URL", "mihomo_api_url") or DEFAULT_API_URL,
        api_secret=_read_setting("MIHOMO_SECRET", "mihomo_secret"),
    )


def _read_setting(env_name: str, settings_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    return str(getattr(app_settings, settings_name, "") or "").strip()


__all__ = ["create_proxy_off_tool", "create_proxy_on_tool"]
