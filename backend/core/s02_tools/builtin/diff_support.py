from __future__ import annotations

import difflib
from typing import Literal

from backend.common.types import FileDiff


def build_unified_diff(
    relative_path: str,
    old_content: str,
    new_content: str,
    *,
    old_exists: bool = True,
    new_exists: bool = True,
) -> FileDiff | None:
    if old_content == new_content and old_exists == new_exists:
        return None
    old_lines = old_content.splitlines(keepends=True) if old_exists else []
    new_lines = new_content.splitlines(keepends=True) if new_exists else []
    diff = "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
        )
    )
    if not diff:
        return None
    return FileDiff(
        path=relative_path,
        unified_diff=diff,
        change_type=_change_type(old_exists, new_exists),
    )


def _change_type(old_exists: bool, new_exists: bool) -> Literal["create", "modify", "delete"]:
    if not old_exists:
        return "create"
    if not new_exists:
        return "delete"
    return "modify"


__all__ = ["build_unified_diff"]
