from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from backend.core.s02_tools.builtin.proxy_custom_nodes import CustomNodesManager


def test_add_vps_node_writes_custom_nodes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script_module("add_vps_node")
    work_dir = _make_temp_dir("add_vps")
    monkeypatch.setenv("MIHOMO_WORK_DIR", str(work_dir))
    module.main()
    data = yaml.safe_load((work_dir / "custom_nodes.yaml").read_text(encoding="utf-8"))
    assert data["exit_nodes"] == [module.VPS_NODE]
    assert data["chain_config"] == {"exit_node": "", "transit_pattern": "", "transit_nodes": []}
    output = capsys.readouterr().out
    assert "Wrote custom nodes to" in output
    assert "Verification passed" in output


def test_add_vps_node_overwrites_old_data(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_script_module("add_vps_node")
    work_dir = _make_temp_dir("overwrite")
    custom_path = work_dir / "custom_nodes.yaml"
    custom_path.write_text("garbage: true\nexit_nodes:\n  - name: OneProxy\n", encoding="utf-8")
    monkeypatch.setenv("MIHOMO_WORK_DIR", str(work_dir))
    module.main()
    data = yaml.safe_load(custom_path.read_text(encoding="utf-8"))
    assert data["exit_nodes"] == [module.VPS_NODE]
    assert data["chain_config"] == {"exit_node": "", "transit_pattern": "", "transit_nodes": []}
    content = custom_path.read_text(encoding="utf-8")
    assert "OneProxy" not in content
    assert "garbage" not in content


def test_regenerate_includes_custom_node(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script_module("regenerate_config")
    work_dir = _make_temp_dir("regenerate")
    sub_path = work_dir / "sub_raw.yaml"
    out_path = work_dir / "config.yaml"
    sub_path.write_text(
        yaml.dump(
            {"proxies": [{"name": "JP1", "type": "ss"}]},
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    CustomNodesManager(str(work_dir / "custom_nodes.yaml")).save(
        {
            "exit_nodes": [
                {
                    "name": "bwg-us-vless",
                    "type": "vless",
                    "server": "67.216.207.8",
                    "port": 443,
                    "uuid": "demo-uuid",
                    "network": "tcp",
                    "tls": True,
                    "servername": "www.intel.com",
                }
            ],
            "chain_config": {"exit_node": "", "transit_pattern": "", "transit_nodes": []},
        }
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["regenerate_config.py", "--sub", str(sub_path), "--out", str(out_path)],
    )
    assert module.main() == 0
    data = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert any(str(proxy["name"]) == "bwg-us-vless" for proxy in data["proxies"])
    assert "Merged custom nodes" in capsys.readouterr().out


def _load_script_module(script_name: str):
    script_path = Path(__file__).resolve().parents[3] / "scripts" / f"{script_name}.py"
    module_name = f"test_{script_name}_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _make_temp_dir(name: str) -> Path:
    path = Path("tests/.tmp_proxy_scripts") / f"{name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path
