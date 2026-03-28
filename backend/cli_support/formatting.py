from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.common.types import ToolDefinition


@dataclass
class ToolRun:
    label: str
    started_at: datetime


def shorten(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def load_version() -> str:
    try:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str(data.get("project", {}).get("version", "0.1.0"))
    except Exception:
        return "0.1.0"


def short_workspace(path: str, limit: int = 40) -> str:
    normalized = path.replace("\\", "/")
    home = os.path.expanduser("~").replace("\\", "/")
    if normalized.startswith(home):
        normalized = f"~{normalized[len(home):]}"
    if len(normalized) <= limit:
        return normalized
    parts = [part for part in normalized.split("/") if part and part != "~"]
    if len(parts) < 2:
        return shorten(normalized, limit)
    return shorten(f".../{'/'.join(parts[-2:])}", limit)


def group_tools(definitions: list[ToolDefinition]) -> list[tuple[str, list[str]]]:
    builtin: list[str] = []
    servers: dict[str, list[str]] = {}
    for definition in definitions:
        if definition.name.startswith("mcp__") and definition.name.count("__") >= 2:
            _, server, short_name = definition.name.split("__", 2)
            servers.setdefault(server, []).append(short_name)
            continue
        builtin.append(definition.name)
    groups: list[tuple[str, list[str]]] = []
    if builtin:
        groups.append(("builtin", builtin))
    groups.extend((server, names) for server, names in servers.items())
    return groups


def summarize_tools(names: list[str]) -> str:
    if len(names) <= 5:
        return ", ".join(names)
    return f"{', '.join(names[:3])} (+{len(names) - 3})"


def frame(lines: list[str]) -> str:
    width = max(len(line) for line in lines)
    top = f"┌{'─' * (width + 2)}┐"
    body = [f"│ {line.ljust(width)} │" for line in lines]
    bottom = f"└{'─' * (width + 2)}┘"
    return "\n".join([top, *body, bottom])


def format_output(text: str) -> list[str]:
    content = text.strip()
    if not content:
        return []
    lines = content.splitlines()
    if len(lines) > 10:
        lines = [*lines[:5], f"... (共 {len(content.splitlines())} 行)"]
    elif len(lines) == 1:
        lines = [shorten(lines[0], 160)]
    return lines


__all__ = [
    "ToolRun",
    "format_output",
    "frame",
    "group_tools",
    "load_version",
    "short_workspace",
    "shorten",
    "summarize_tools",
]
