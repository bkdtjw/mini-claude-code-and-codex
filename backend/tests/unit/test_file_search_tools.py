from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.common.types import ToolResult
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.s02_tools.builtin.file_glob import create_glob_tool
from backend.core.s02_tools.builtin.file_grep import create_grep_tool


async def _run_glob(workspace: Path, args: dict[str, object]) -> ToolResult:
    _, execute = create_glob_tool(str(workspace))
    return await execute(args)


async def _run_grep(workspace: Path, args: dict[str, object]) -> ToolResult:
    _, execute = create_grep_tool(str(workspace))
    return await execute(args)


@pytest.mark.asyncio
async def test_glob_returns_structured_file_matches(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "backend" / "note.md").write_text("text\n", encoding="utf-8")

    result = await _run_glob(tmp_path, {"pattern": "**/*.py"})
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload == {"matches": [{"path": "backend/app.py"}], "truncated": False}


@pytest.mark.asyncio
async def test_glob_rejects_unsafe_pattern(tmp_path: Path) -> None:
    result = await _run_glob(tmp_path, {"pattern": "../*.py"})

    assert result.is_error is True
    assert result.output == "Invalid pattern"


@pytest.mark.asyncio
async def test_grep_returns_path_line_number_and_line(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("alpha\nToolResult(output='ok')\nomega\n", encoding="utf-8")

    result = await _run_grep(tmp_path, {"pattern": "ToolResult", "include": "**/*.py"})
    payload = json.loads(result.output)

    assert result.is_error is False
    assert payload["matches"] == [
        {"path": "sample.py", "line_number": 2, "line": "ToolResult(output='ok')"}
    ]
    assert payload["truncated"] is False


@pytest.mark.asyncio
async def test_grep_supports_case_insensitive_and_regex(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("Alpha\nbeta-42\n", encoding="utf-8")

    insensitive = await _run_grep(tmp_path, {"pattern": "alpha", "case_sensitive": False})
    regex = await _run_grep(tmp_path, {"pattern": r"beta-\d+", "regex": True})

    assert json.loads(insensitive.output)["matches"][0]["line"] == "Alpha"
    assert json.loads(regex.output)["matches"][0]["line"] == "beta-42"


@pytest.mark.asyncio
async def test_grep_limits_results_and_skips_binary_files(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hit\nhit\nhit\n", encoding="utf-8")
    (tmp_path / "binary.txt").write_bytes(b"hit\x00hit")

    result = await _run_grep(tmp_path, {"pattern": "hit", "max_results": 2})
    payload = json.loads(result.output)

    assert [item["line_number"] for item in payload["matches"]] == [1, 2]
    assert payload["truncated"] is True
    assert all(item["path"] == "a.txt" for item in payload["matches"])


def test_register_builtin_tools_includes_search_tools(tmp_path: Path) -> None:
    registry = ToolRegistry()

    register_builtin_tools(registry, str(tmp_path), mode="auto")

    names = [definition.name for definition in registry.list_definitions()]
    assert names[:6] == ["Read", "Glob", "Grep", "str_replace", "file_edit", "Write"]
