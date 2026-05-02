from __future__ import annotations

import os

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from .diff_support import build_unified_diff


def _is_safe_path(path: str) -> bool:
    if not path or os.path.isabs(path):
        return False
    return ".." not in path.replace("\\", "/").split("/")


def _full_path(root: str, relative_path: str) -> str | None:
    if not _is_safe_path(relative_path):
        return None
    full_path = os.path.abspath(os.path.join(root, relative_path))
    if not full_path.startswith(root + os.sep) and full_path != root:
        return None
    return full_path


def _read_text(full_path: str, relative_path: str) -> tuple[str | None, ToolResult | None]:
    if not os.path.isfile(full_path):
        return None, ToolResult(output=f"File not found: {relative_path}", is_error=True)
    try:
        with open(full_path, encoding="utf-8") as file:
            return file.read(), None
    except UnicodeDecodeError:
        return None, ToolResult(output=f"File is not valid UTF-8: {relative_path}", is_error=True)


def _write_text(full_path: str, content: str) -> None:
    with open(full_path, "w", encoding="utf-8") as file:
        file.write(content)


def _line_count(content: str) -> int:
    return len(content.splitlines())


def _line_number_for_offset(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _line_numbers_for_offsets(content: str, offsets: list[int]) -> list[int]:
    lines: list[int] = []
    line_number = 1
    newline_index = content.find("\n")
    for offset in offsets:
        while newline_index >= 0 and newline_index < offset:
            line_number += 1
            newline_index = content.find("\n", newline_index + 1)
        lines.append(line_number)
    return lines


def _match_offsets(content: str, old_str: str) -> list[int]:
    offsets: list[int] = []
    start = 0
    while True:
        index = content.find(old_str, start)
        if index < 0:
            return offsets
        offsets.append(index)
        start = index + len(old_str)


def create_str_replace_tool(base_path: str) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="str_replace",
        description=(
            "Replace one exact text fragment in an existing file. Use this as the "
            "default editing tool instead of rewriting the whole file."
        ),
        category="file-ops",
        parameters=ToolParameterSchema(
            properties={
                "path": {"type": "string", "description": "Relative file path"},
                "old_str": {"type": "string", "description": "Exact existing text"},
                "new_str": {"type": "string", "description": "Replacement text"},
            },
            required=["path", "old_str", "new_str"],
        ),
    )
    root = os.path.abspath(base_path)

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            relative_path = str(args.get("path", ""))
            old_str = str(args.get("old_str", ""))
            new_str = str(args.get("new_str", ""))
            full_path = _full_path(root, relative_path)
            if full_path is None:
                return ToolResult(output="Invalid path", is_error=True)
            if not old_str:
                return ToolResult(output="old_str must not be empty", is_error=True)
            content, error = _read_text(full_path, relative_path)
            if error is not None:
                return error
            if content is None:
                return ToolResult(output=f"Unable to read file: {relative_path}", is_error=True)
            offsets = _match_offsets(content, old_str)
            if not offsets:
                return ToolResult(
                    output=(
                        f"No match for old_str in {relative_path}. "
                        f"File has {_line_count(content)} lines. "
                        "Read the surrounding context and provide an exact old_str."
                    ),
                    is_error=True,
                )
            if len(offsets) > 1:
                lines = _line_numbers_for_offsets(content, offsets)
                return ToolResult(
                    output=(
                        f"old_str matched {len(offsets)} times in {relative_path}. "
                        f"Match start lines: {', '.join(str(line) for line in lines)}. "
                        "Provide a longer, more specific old_str."
                    ),
                    is_error=True,
                )
            updated = content.replace(old_str, new_str, 1)
            diff = build_unified_diff(relative_path, content, updated)
            _write_text(full_path, updated)
            line = _line_number_for_offset(content, offsets[0])
            return ToolResult(output=f"Replaced text in {relative_path} at line {line}", diffs=[diff] if diff else [])
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def create_file_edit_tool(base_path: str) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="file_edit",
        description=(
            "Replace an inclusive 1-based line range in an existing file. Use this "
            "when str_replace cannot be made unique."
        ),
        category="file-ops",
        parameters=ToolParameterSchema(
            properties={
                "path": {"type": "string", "description": "Relative file path"},
                "start_line": {"type": "integer", "description": "1-based start line"},
                "end_line": {"type": "integer", "description": "1-based end line"},
                "new_content": {"type": "string", "description": "Replacement text"},
            },
            required=["path", "start_line", "end_line", "new_content"],
        ),
    )
    root = os.path.abspath(base_path)

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            relative_path = str(args.get("path", ""))
            full_path = _full_path(root, relative_path)
            if full_path is None:
                return ToolResult(output="Invalid path", is_error=True)
            try:
                start_line = int(args.get("start_line", 0))
                end_line = int(args.get("end_line", 0))
            except (TypeError, ValueError):
                return ToolResult(output="start_line and end_line must be integers", is_error=True)
            content, error = _read_text(full_path, relative_path)
            if error is not None:
                return error
            if content is None:
                return ToolResult(output=f"Unable to read file: {relative_path}", is_error=True)
            lines = content.splitlines()
            total_lines = len(lines)
            if start_line < 1 or end_line < start_line or end_line > total_lines:
                return ToolResult(
                    output=(
                        f"Invalid line range {start_line}-{end_line} for {relative_path}. "
                        f"File has {total_lines} lines."
                    ),
                    is_error=True,
                )
            newline = "\r\n" if "\r\n" in content else "\n"
            final_newline = content.endswith(("\n", "\r"))
            replacement = str(args.get("new_content", "")).splitlines()
            updated_lines = lines[: start_line - 1] + replacement + lines[end_line:]
            updated = newline.join(updated_lines)
            if final_newline and updated_lines:
                updated += newline
            diff = build_unified_diff(relative_path, content, updated)
            _write_text(full_path, updated)
            return ToolResult(output=f"Edited {relative_path} lines {start_line}-{end_line}", diffs=[diff] if diff else [])
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


__all__ = ["create_file_edit_tool", "create_str_replace_tool"]
