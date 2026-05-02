from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.s02_tools.builtin.file_edit import (
    create_file_edit_tool,
    create_str_replace_tool,
)


async def _run_str_replace(workspace: Path, args: dict[str, object]):
    _, execute = create_str_replace_tool(str(workspace))
    return await execute(args)


async def _run_file_edit(workspace: Path, args: dict[str, object]):
    _, execute = create_file_edit_tool(str(workspace))
    return await execute(args)


@pytest.mark.asyncio
async def test_str_replace_replaces_single_exact_match(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    result = await _run_str_replace(
        tmp_path,
        {"path": "sample.txt", "old_str": "beta", "new_str": "BETA"},
    )

    assert result.is_error is False
    assert "line 2" in result.output
    assert target.read_text(encoding="utf-8") == "alpha\nBETA\ngamma\n"


@pytest.mark.asyncio
async def test_str_replace_zero_matches_returns_context_for_retry(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")

    result = await _run_str_replace(
        tmp_path,
        {"path": "sample.txt", "old_str": "missing", "new_str": "x"},
    )

    assert result.is_error is True
    assert "No match" in result.output
    assert "File has 2 lines" in result.output
    assert target.read_text(encoding="utf-8") == "alpha\nbeta\n"


@pytest.mark.asyncio
async def test_str_replace_multiple_matches_returns_all_start_lines(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("same\nother\nsame\n", encoding="utf-8")

    result = await _run_str_replace(
        tmp_path,
        {"path": "sample.txt", "old_str": "same", "new_str": "changed"},
    )

    assert result.is_error is True
    assert "matched 2 times" in result.output
    assert "Match start lines: 1, 3" in result.output
    assert target.read_text(encoding="utf-8") == "same\nother\nsame\n"


@pytest.mark.asyncio
async def test_str_replace_rejects_unsafe_or_missing_paths(tmp_path: Path) -> None:
    absolute = await _run_str_replace(
        tmp_path,
        {"path": str(tmp_path / "x.txt"), "old_str": "a", "new_str": "b"},
    )
    parent = await _run_str_replace(
        tmp_path,
        {"path": "../x.txt", "old_str": "a", "new_str": "b"},
    )
    missing = await _run_str_replace(
        tmp_path,
        {"path": "missing.txt", "old_str": "a", "new_str": "b"},
    )

    assert absolute.is_error is True
    assert parent.is_error is True
    assert missing.is_error is True
    assert absolute.output == "Invalid path"
    assert parent.output == "Invalid path"
    assert "File not found" in missing.output


@pytest.mark.asyncio
async def test_file_edit_replaces_single_and_multiple_lines(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    first = await _run_file_edit(
        tmp_path,
        {"path": "sample.txt", "start_line": 2, "end_line": 2, "new_content": "TWO"},
    )
    second = await _run_file_edit(
        tmp_path,
        {
            "path": "sample.txt",
            "start_line": 3,
            "end_line": 4,
            "new_content": "THREE\nFOUR",
        },
    )

    assert first.is_error is False
    assert second.is_error is False
    assert target.read_text(encoding="utf-8") == "one\nTWO\nTHREE\nFOUR\n"


@pytest.mark.asyncio
async def test_file_edit_empty_content_deletes_range(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = await _run_file_edit(
        tmp_path,
        {"path": "sample.txt", "start_line": 2, "end_line": 2, "new_content": ""},
    )

    assert result.is_error is False
    assert target.read_text(encoding="utf-8") == "one\nthree\n"


@pytest.mark.asyncio
async def test_file_edit_rejects_invalid_line_range(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("one\ntwo\n", encoding="utf-8")

    result = await _run_file_edit(
        tmp_path,
        {"path": "sample.txt", "start_line": 3, "end_line": 2, "new_content": "x"},
    )

    assert result.is_error is True
    assert "Invalid line range 3-2" in result.output
    assert "File has 2 lines" in result.output
    assert target.read_text(encoding="utf-8") == "one\ntwo\n"


def test_register_builtin_tools_includes_edit_tools(tmp_path: Path) -> None:
    registry = ToolRegistry()

    register_builtin_tools(registry, str(tmp_path), mode="auto")

    names = [definition.name for definition in registry.list_definitions()]
    assert "str_replace" in names
    assert "file_edit" in names
    assert names.index("str_replace") < names.index("Write")
    assert names.index("file_edit") < names.index("Write")
