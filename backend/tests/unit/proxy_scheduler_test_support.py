from __future__ import annotations

from pathlib import Path

import yaml

from backend.core.s02_tools.builtin.proxy_api_support import find_fastest
from backend.core.s02_tools.builtin.proxy_chain import CHAIN_GROUP_NAME
from backend.core.s02_tools.builtin.proxy_models import DelayTestResult, ProxyGroup, ProxyStatus


def write_custom_nodes(
    path: Path,
    exit_name: str,
    transit_pattern: str = "",
    transit_nodes: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "exit_nodes": [
                    {"name": exit_name, "type": "trojan", "server": "us.example.com", "port": 443}
                ],
                "chain_config": {
                    "exit_node": exit_name,
                    "transit_pattern": transit_pattern,
                    "transit_nodes": transit_nodes or [],
                },
            },
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


class FakeSchedulerAPI:
    def __init__(self, results_sequence: list[dict[str, int]], switch_success: bool = True) -> None:
        self._results_sequence = results_sequence
        self._index = 0
        self.current_node = ""
        self.switch_success = switch_success
        self.reload_paths: list[str] = []
        self.switches: list[str] = []
        self.last_results: dict[str, int] = results_sequence[0] if results_sequence else {}

    async def test_group_delay(
        self,
        _group: str,
        timeout: int = 5000,
        test_url: str = "",
    ) -> DelayTestResult:
        self._index = min(self._index, max(len(self._results_sequence) - 1, 0))
        self.last_results = (
            dict(self._results_sequence[self._index]) if self._results_sequence else {}
        )
        self._index += 1
        fastest_node, fastest_delay = find_fastest(self.last_results)
        return DelayTestResult(
            results=self.last_results,
            fastest_node=fastest_node,
            fastest_delay=fastest_delay,
            timeout_nodes=[name for name, delay in self.last_results.items() if delay <= 0],
            test_url=test_url,
            timestamp="2026-04-04 16:30:00",
        )

    async def switch_proxy(self, _group: str, node_name: str) -> bool:
        self.switches.append(node_name)
        if self.switch_success:
            self.current_node = node_name
        return self.switch_success

    async def get_proxies(self) -> ProxyStatus:
        return ProxyStatus(
            groups=[
                ProxyGroup(
                    name=CHAIN_GROUP_NAME,
                    type="Selector",
                    now=self.current_node,
                    all=list(self.last_results),
                )
            ]
        )

    async def reload_config(self, config_path: str) -> bool:
        self.reload_paths.append(config_path)
        return True

    async def get_version(self) -> str:
        return "v1.19.22"


__all__ = ["FakeSchedulerAPI", "write_custom_nodes"]
