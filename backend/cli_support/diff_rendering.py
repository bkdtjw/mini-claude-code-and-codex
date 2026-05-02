from __future__ import annotations

from collections.abc import Callable

from backend.common.types import FileDiff

PaintFn = Callable[[str, str], str]


def render_file_diffs(diffs: list[FileDiff], paint: PaintFn) -> str:
    blocks = [_render_diff(diff, paint) for diff in diffs if diff.unified_diff.strip()]
    return "\n".join(block for block in blocks if block)


def _render_diff(diff: FileDiff, paint: PaintFn) -> str:
    return "\n".join(_render_line(line, paint) for line in diff.unified_diff.splitlines())


def _render_line(line: str, paint: PaintFn) -> str:
    if line.startswith("+") and not line.startswith("+++"):
        return paint(line, "32")
    if line.startswith("-") and not line.startswith("---"):
        return paint(line, "31")
    if line.startswith("@@"):
        return paint(line, "33")
    if line.startswith(("---", "+++", "diff --git")):
        return paint(line, "90")
    return line


__all__ = ["render_file_diffs"]
