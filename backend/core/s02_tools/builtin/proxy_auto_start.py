from __future__ import annotations

import os
from pathlib import Path

from backend.config.settings import settings as app_settings

from .proxy_api import MihomoAPI
from .proxy_models import ProxyConfig
from .proxy_process import MihomoProcess

DEFAULT_API_URL = "http://127.0.0.1:9090"
AUTO_START_HINT = (
    "mihomo API unavailable. To enable auto-start, set MIHOMO_PATH and MIHOMO_CONFIG_PATH"
)
_mihomo_api: MihomoAPI | None = None
_mihomo_process: MihomoProcess | None = None


def _get_api(api_url: str = DEFAULT_API_URL, secret: str = "") -> MihomoAPI:
    global _mihomo_api
    if _mihomo_api is None or getattr(_mihomo_api, "_base_url", "") != api_url.rstrip("/"):
        _mihomo_api = MihomoAPI(api_url, secret)
    elif getattr(_mihomo_api, "_secret", "") != secret.strip():
        _mihomo_api = MihomoAPI(api_url, secret)
    return _mihomo_api


async def _ensure_mihomo_running(api_url: str = DEFAULT_API_URL, secret: str = "") -> str | None:
    global _mihomo_process
    api = _get_api(api_url, secret)
    if await api.get_version():
        return None
    config = _build_process_config(api_url, secret)
    if config is None:
        return AUTO_START_HINT
    if _mihomo_process is None or getattr(_mihomo_process, "_config", None) != config:
        _mihomo_process = MihomoProcess(config)
    result = await _mihomo_process.start()
    if result[:1].lower() == "v":
        return None
    return f"mihomo auto-start failed: {result}"


def _build_process_config(api_url: str, secret: str) -> ProxyConfig | None:
    mihomo_path = _read_setting("MIHOMO_PATH", "mihomo_path")
    config_path = _read_setting("MIHOMO_CONFIG_PATH", "mihomo_config_path")
    if not mihomo_path or not config_path:
        return None
    work_dir = _read_setting("MIHOMO_WORK_DIR", "mihomo_work_dir") or str(Path(mihomo_path).parent)
    return ProxyConfig(
        mihomo_path=mihomo_path,
        config_path=config_path,
        work_dir=work_dir,
        api_url=api_url,
        api_secret=secret,
    )


def _read_setting(env_name: str, settings_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    return str(getattr(app_settings, settings_name, "") or "").strip()


__all__ = ["AUTO_START_HINT", "DEFAULT_API_URL", "_ensure_mihomo_running", "_get_api"]
