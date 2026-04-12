from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .proxy_api import MihomoAPI
from .proxy_chain import CHAIN_GROUP_NAME, ChainProxyManager
from .proxy_config import ProxyConfigGenerator
from .proxy_custom_nodes import CustomNodesManager
from .proxy_scheduler_models import SchedulerError


async def ensure_chain_group(
    api: MihomoAPI,
    config_path: str,
    custom_nodes_path: str,
) -> int:
    generator = ProxyConfigGenerator(config_path)
    manager = CustomNodesManager(custom_nodes_path)
    config = generator.load()
    merged = manager.merge_into_config(config)
    if not ChainProxyManager.list_chains(merged):
        updated = merged
        chain_config = manager.get_chain_config()
        for exit_name in _resolve_exit_targets(manager.get_exit_nodes(), chain_config):
            updated, _created = ChainProxyManager.set_chain(
                updated,
                exit_name,
                chain_config.get("transit_nodes") or None,
                chain_config.get("transit_pattern") or None,
            )
        merged = updated
    if merged != config:
        path = str(Path(generator.save(merged)).resolve())
        await api.reload_config(path)
    return len(ChainProxyManager.list_chains(merged))


async def load_current_node(api: MihomoAPI) -> str:
    status = await api.get_proxies()
    group = next((item for item in status.groups if item.name == CHAIN_GROUP_NAME), None)
    return group.now if group and group.now else ""


def format_current(node: str, delay: int) -> str:
    return f"{node} ({delay}ms)" if node and delay > 0 else (node or "None")


def format_runtime(start_time: datetime | None) -> str:
    if start_time is None:
        return "0 seconds"
    seconds = max(int((datetime.now() - start_time).total_seconds()), 0)
    return f"{seconds // 60} minutes" if seconds >= 60 else f"{seconds} seconds"


def _resolve_exit_targets(
    exit_nodes: list[dict[str, Any]],
    chain_config: dict[str, Any],
) -> list[str]:
    targets = [str(chain_config.get("exit_node") or "").strip()]
    if not targets[0]:
        targets = [str(item.get("name") or "").strip() for item in exit_nodes]
    cleaned = [name for name in targets if name]
    if not cleaned:
        raise SchedulerError("No exit nodes are available. Configure custom_nodes.yaml first.")
    return list(dict.fromkeys(cleaned))


__all__ = ["ensure_chain_group", "format_current", "format_runtime", "load_current_node"]
