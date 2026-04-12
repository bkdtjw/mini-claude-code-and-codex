from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

VPS_NODE = {
    "name": "bwg-us-vless",
    "type": "vless",
    "server": "67.216.207.8",
    "port": 443,
    "uuid": "db387da6-20c5-4f89-94c7-53e56398ba3b",
    "network": "tcp",
    "tls": True,
    "udp": True,
    "flow": "xtls-rprx-vision",
    "servername": "www.intel.com",
    "reality-opts": {
        "public-key": "EqJ53uDx53Ip26PZ9VmQpJj_W4-ZdQdzqxi6T_o7QA0",
        "short-id": "7b5d25da",
    },
    "client-fingerprint": "chrome",
}


def main() -> None:
    from backend.core.s02_tools.builtin.proxy_custom_nodes import CustomNodesManager

    work_dir = Path(os.environ.get("MIHOMO_WORK_DIR", REPO_ROOT))
    custom_path = work_dir / "custom_nodes.yaml"
    manager = CustomNodesManager(str(custom_path))
    manager.save(_build_payload())
    with open(custom_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    assert "bwg-us-vless" in content, "Verification failed: node name not found"
    assert "67.216.207.8" in content, "Verification failed: server IP not found"
    _safe_print(f"Wrote custom nodes to: {custom_path}")
    _safe_print("Verification passed")


def _build_payload() -> dict[str, Any]:
    return {
        "exit_nodes": [VPS_NODE],
        "chain_config": {
            "exit_node": "",
            "transit_pattern": "",
            "transit_nodes": [],
        },
    }


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.buffer.write(text.encode(encoding, errors="backslashreplace") + b"\n")


if __name__ == "__main__":
    main()
