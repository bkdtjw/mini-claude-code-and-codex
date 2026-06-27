from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _frontend_dist_dir() -> Path:
    candidates: list[Path] = []
    configured = os.getenv("FRONTEND_DIST_DIR", "").strip()
    if configured:
        candidates.append(Path(configured))
    candidates.append(REPO_ROOT / "dist" / "frontend")

    for candidate in candidates:
        if (candidate / "index.html").is_file() and (candidate / "assets").is_dir():
            return candidate
    pytest.skip("frontend dist is not built")


def test_frontend_build_marks_dist_readable() -> None:
    package_json = REPO_ROOT / "frontend" / "package.json"
    data = json.loads(package_json.read_text(encoding="utf-8"))

    build_script = data["scripts"]["build"]

    assert "chmod -R a+rX ../dist/frontend" in build_script


def test_frontend_dist_is_readable_by_web_worker() -> None:
    dist_dir = _frontend_dist_dir()
    unreadable: list[str] = []

    for path in [dist_dir, *dist_dir.rglob("*")]:
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir():
            required = stat.S_IROTH | stat.S_IXOTH
            if mode & required != required:
                unreadable.append(f"{path}: expected other read+execute, got {oct(mode)}")
        elif path.is_file() and mode & stat.S_IROTH != stat.S_IROTH:
            unreadable.append(f"{path}: expected other read, got {oct(mode)}")

    assert unreadable == []
