from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from .proxy_chain import CHAIN_GROUP_NAME, ChainProxyManager
from .proxy_chain_utils import append_name_to_groups, ensure_list, find_proxy, normalize_exit_name
from .proxy_models import CustomNodesState


class CustomNodesError(Exception):
    """Raised when custom node persistence fails."""


class CustomNodesManager:
    """Persist custom exit nodes and chain settings."""

    def __init__(self, storage_path: str) -> None:
        self._storage_path = Path(storage_path)

    def load(self) -> dict[str, Any]:
        try:
            if not self._storage_path.exists():
                return _default_state()
            data = yaml.safe_load(self._storage_path.read_text(encoding="utf-8")) or {}
            return CustomNodesState.model_validate(data).model_dump()
        except Exception as exc:  # noqa: BLE001
            raise CustomNodesError(f"读取 custom_nodes 失败: {exc}") from exc

    def save(self, data: dict[str, Any]) -> None:
        try:
            payload = CustomNodesState.model_validate(data).model_dump()
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._storage_path.write_text(
                yaml.safe_dump(
                    payload,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            raise CustomNodesError(f"写入 custom_nodes 失败: {exc}") from exc

    def add_exit_node(self, node: dict[str, Any]) -> None:
        data = self.load()
        exit_nodes = data["exit_nodes"]
        normalized = copy.deepcopy(node)
        normalized["name"] = normalize_exit_name(str(node.get("name") or ""))
        existing = next(
            (
                index
                for index, item in enumerate(exit_nodes)
                if item.get("name") == normalized["name"]
            ),
            -1,
        )
        if existing >= 0:
            exit_nodes[existing] = normalized
        else:
            exit_nodes.append(normalized)
        self.save(data)

    def remove_exit_node(self, name: str) -> None:
        data = self.load()
        exit_name = normalize_exit_name(name)
        data["exit_nodes"] = [item for item in data["exit_nodes"] if item.get("name") != exit_name]
        if data["chain_config"]["exit_node"] == exit_name:
            data["chain_config"] = _default_state()["chain_config"]
        self.save(data)

    def set_chain_config(
        self,
        exit_node: str,
        transit_pattern: str = "",
        transit_nodes: list[str] | None = None,
    ) -> None:
        data = self.load()
        data["chain_config"] = {
            "exit_node": normalize_exit_name(exit_node),
            "transit_pattern": transit_pattern.strip(),
            "transit_nodes": [item.strip() for item in transit_nodes or [] if item.strip()],
        }
        self.save(data)

    def clear_chain_config(self) -> None:
        data = self.load()
        data["chain_config"] = _default_state()["chain_config"]
        self.save(data)

    def get_exit_nodes(self) -> list[dict[str, Any]]:
        return self.load()["exit_nodes"]

    def get_chain_config(self) -> dict[str, Any]:
        return self.load()["chain_config"]

    def merge_into_config(self, config: dict[str, Any]) -> dict[str, Any]:
        try:
            data = self.load()
            result = copy.deepcopy(config)
            proxies = ensure_list(result, "proxies")
            groups = ensure_list(result, "proxy-groups")
            for node in data["exit_nodes"]:
                if find_proxy(proxies, str(node.get("name") or "")) is None:
                    proxies.append(copy.deepcopy(node))
                append_name_to_groups(groups, str(node.get("name") or ""), {CHAIN_GROUP_NAME})
            chain_config = data["chain_config"]
            if chain_config["exit_node"]:
                result, _ = ChainProxyManager.set_chain(
                    result,
                    chain_config["exit_node"],
                    chain_config["transit_nodes"] or None,
                    chain_config["transit_pattern"] or None,
                )
            return result
        except Exception as exc:  # noqa: BLE001
            raise CustomNodesError(f"合并 custom_nodes 失败: {exc}") from exc


def _default_state() -> dict[str, Any]:
    return CustomNodesState().model_dump()


__all__ = ["CustomNodesError", "CustomNodesManager"]
