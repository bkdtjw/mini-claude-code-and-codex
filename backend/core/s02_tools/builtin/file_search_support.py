from __future__ import annotations

import fnmatch
import os
from pathlib import Path

MAX_SEARCH_BYTES = 1024 * 1024
IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}


class FileSearchToolError(Exception):
    """File search tool validation or IO error."""


def is_safe_pattern(pattern: str) -> bool:
    if not pattern or os.path.isabs(pattern):
        return False
    return ".." not in pattern.replace("\\", "/").split("/")


def iter_matching_files(root: Path, pattern: str) -> list[Path]:
    if not is_safe_pattern(pattern):
        raise FileSearchToolError("Invalid pattern")
    matches: list[Path] = []
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [item for item in dirs if item not in IGNORED_DIRS]
        base = Path(current_root)
        for name in files:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if _matches(relative, name, pattern):
                matches.append(path)
    return sorted(matches, key=lambda item: item.relative_to(root).as_posix())


def read_searchable_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_SEARCH_BYTES:
            return None
        data = path.read_bytes()
        if b"\x00" in data:
            return None
        return data.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _matches(relative: str, name: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/")
    patterns = [normalized]
    if normalized.startswith("**/"):
        patterns.append(normalized[3:])
    return any(fnmatch.fnmatch(relative, item) or fnmatch.fnmatch(name, item) for item in patterns)


__all__ = [
    "FileSearchToolError",
    "MAX_SEARCH_BYTES",
    "is_safe_pattern",
    "iter_matching_files",
    "read_searchable_text",
    "relative_path",
]
