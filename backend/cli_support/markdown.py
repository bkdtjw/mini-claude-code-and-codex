from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

_BOLD_MARKDOWN_PATTERN = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_HEADER_MARKDOWN_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
_TABLE_SEPARATOR_CHARS = {"-", ":", " "}


def render_markdown(text: str, ansi: bool, paint: Callable[[str, str], str]) -> str:
    rendered_lines: list[str] = []
    table_lines: list[str] = []

    def flush_table() -> None:
        if table_lines:
            rendered_lines.append(render_table(table_lines, ansi))
            table_lines.clear()

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(line)
            continue
        flush_table()
        rendered_lines.append(render_markdown_line(line, ansi, paint))
    flush_table()
    return "\n".join(rendered_lines)


def render_markdown_line(line: str, ansi: bool, paint: Callable[[str, str], str]) -> str:
    header_match = _HEADER_MARKDOWN_PATTERN.match(line)
    if header_match is None:
        return render_inline_bold(line, ansi)
    content = strip_bold_markdown(header_match.group(2))
    return content if not ansi else paint(content, "1")


def render_inline_bold(text: str, ansi: bool) -> str:
    def replace(match: re.Match[str]) -> str:
        content = match.group(1)
        return content if not ansi else f"\033[1m{content}\033[0m"

    return _BOLD_MARKDOWN_PATTERN.sub(replace, text)


def strip_bold_markdown(text: str) -> str:
    return _BOLD_MARKDOWN_PATTERN.sub(lambda match: match.group(1), text)


def display_width(text: str) -> int:
    width = 0
    for char in text:
        width += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
    return width


def pad(text: str, target_width: int, ansi: bool) -> str:
    visible = strip_bold_markdown(text)
    padding = max(target_width - display_width(visible), 0)
    return f"{render_inline_bold(text, ansi)}{' ' * padding}"


def render_table(lines: list[str], ansi: bool) -> str:
    rows: list[list[str]] = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(cell and set(cell) <= _TABLE_SEPARATOR_CHARS for cell in cells):
            continue
        rows.append(cells)
    if not rows:
        return ""
    column_count = max(len(row) for row in rows)
    widths = [0] * column_count
    for row in rows:
        for index in range(column_count):
            cell = row[index] if index < len(row) else ""
            visible = strip_bold_markdown(cell)
            widths[index] = max(widths[index], display_width(visible))
    rendered_rows: list[str] = []
    for index, row in enumerate(rows):
        cells = [
            pad(row[column] if column < len(row) else "", widths[column], ansi)
            for column in range(column_count)
        ]
        rendered_rows.append("  ".join(cells).rstrip())
        if index == 0:
            rendered_rows.append("  ".join("─" * width for width in widths).rstrip())
    return "\n".join(rendered_rows)
