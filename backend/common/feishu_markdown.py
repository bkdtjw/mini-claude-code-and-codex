"""Markdown to plain text converter for Feishu messages."""
from __future__ import annotations

import re
import unicodedata


def _display_width(text: str) -> int:
    """Calculate display width, treating CJK characters as width 2."""
    width = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def _is_separator_cell(cell: str) -> bool:
    """Check if a table cell is a separator like |:---| or |---:|."""
    stripped = cell.strip()
    return bool(re.match(r"^:?-{3,}:?$", stripped))


def _strip_inline_marks(text: str) -> str:
    """Strip inline markdown: bold, italic, inline code."""
    # Code backticks: `code` -> code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Bold+italic: ***text*** -> text
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", text)
    # Bold: **text** -> text
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    # Italic: *text* -> text (single stars only)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    return text


def _flush_table(buffer: list[str], output: list[str]) -> None:
    """Convert buffered markdown table rows to aligned plain text."""
    if not buffer:
        return

    rows: list[list[str]] = []
    for line in buffer:
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in line[1:-1].split("|")]
        # Skip separator row
        if all(_is_separator_cell(c) for c in cells):
            continue
        rows.append([_strip_inline_marks(c) for c in cells])

    if not rows:
        return

    col_count = max(len(r) for r in rows)
    col_widths = [0] * col_count
    for row in rows:
        for i, cell in enumerate(row):
            if i < col_count:
                col_widths[i] = max(col_widths[i], _display_width(cell))

    for row in rows:
        parts: list[str] = []
        for i in range(col_count):
            cell = row[i] if i < len(row) else ""
            pad = col_widths[i] - _display_width(cell)
            parts.append(cell + " " * pad)
        output.append("  ".join(parts))


def strip_markdown_for_feishu(text: str) -> str:
    """Convert markdown text to plain text suitable for Feishu display."""
    if not text:
        return text

    lines = text.split("\n")
    output: list[str] = []
    table_buffer: list[str] = []
    in_code_block = False

    for line in lines:
        # Code block fence detection
        if line.strip().startswith("```"):
            if in_code_block:
                in_code_block = False
                output.append("---")
            else:
                _flush_table(table_buffer, output)
                table_buffer = []
                in_code_block = True
                output.append("---")
            continue

        if in_code_block:
            output.append(line)
            continue

        # Table row detection
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            table_buffer.append(line)
            continue

        # Flush any pending table
        _flush_table(table_buffer, output)
        table_buffer = []

        # Heading: ## title -> title
        heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if heading_match:
            output.append(_strip_inline_marks(heading_match.group(2)))
            continue

        # Regular line: strip inline marks
        output.append(_strip_inline_marks(line))

    # Flush any remaining table
    _flush_table(table_buffer, output)

    return "\n".join(output)
