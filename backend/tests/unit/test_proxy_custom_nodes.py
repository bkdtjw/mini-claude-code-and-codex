from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from backend.core.s02_tools.builtin.proxy_custom_nodes import CustomNodesManager


def test_custom_nodes_save_valid_utf8() -> None:
    path = _make_temp_path()
    manager = CustomNodesManager(str(path))
    manager.save(
        {
            "exit_nodes": [
                {
                    "name": "bwg-us-vless",
                    "type": "vless",
                    "server": "67.216.207.8",
                    "port": 443,
                }
            ],
            "chain_config": {"exit_node": "", "transit_pattern": "", "transit_nodes": []},
        }
    )
    loaded = manager.load()
    assert loaded["exit_nodes"][0]["name"] == "bwg-us-vless"
    content = path.read_bytes().decode("utf-8")
    assert "bwg-us-vless" in content


def test_custom_nodes_no_corrupted_chars() -> None:
    path = _make_temp_path()
    manager = CustomNodesManager(str(path))
    manager.save(
        {
            "exit_nodes": [
                {
                    "name": "bwg-us-vless",
                    "type": "vless",
                    "server": "67.216.207.8",
                    "port": 443,
                }
            ],
            "chain_config": {"exit_node": "", "transit_pattern": "", "transit_nodes": []},
        }
    )
    content = path.read_text(encoding="utf-8")
    assert content.isascii()


def _make_temp_path() -> Path:
    path = Path("tests/.tmp_proxy_custom_nodes") / uuid4().hex / "custom_nodes.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
