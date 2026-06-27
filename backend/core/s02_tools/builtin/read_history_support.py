from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

ALLOWED_ROOTS = ("data/artifacts", "data/sessions", "data/steps")
MAX_SEARCH_CHARS = 2000
DEFAULT_PAGE_CHARS = 12000
MAX_PAGE_CHARS = 20000


class HistoryReadRequest(BaseModel):
    file_path: str
    query: str = ""
    mode: Literal["search", "full", "range"] = "search"
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=0, ge=0)
    json_path: str = ""


def read_history_content(request: HistoryReadRequest) -> str:
    path = resolve_allowed(request.file_path)
    if not path.is_file():
        raise FileNotFoundError(f"History file not found: {request.file_path}")
    if request.mode in {"full", "range"}:
        return _read_page(path, request)
    if not request.query:
        return "query is required for search mode"
    return _clip(_search_file(path, request.query), _limit(request.limit, MAX_SEARCH_CHARS))


def resolve_allowed(file_path: str) -> Path:
    cwd = Path.cwd().resolve()
    raw_path = Path(file_path).expanduser()
    requested = raw_path.resolve() if raw_path.is_absolute() else (cwd / raw_path).resolve()
    roots = [(cwd / root).resolve() for root in ALLOWED_ROOTS]
    if not any(requested == root or root in requested.parents for root in roots):
        raise ValueError("file_path must be under data/artifacts, data/sessions, or data/steps")
    return requested


def _read_page(path: Path, request: HistoryReadRequest) -> str:
    text = _source_text(path, request)
    limit = _limit(request.limit, DEFAULT_PAGE_CHARS, MAX_PAGE_CHARS)
    start = min(request.offset, len(text))
    end = min(start + limit, len(text))
    page = text[start:end]
    return (
        f"[history_page] offset={start} returned_chars={len(page)} "
        f"total_chars={len(text)} has_more={str(end < len(text)).lower()}\n"
        f"{page}"
    )


def _source_text(path: Path, request: HistoryReadRequest) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    selector = request.json_path or (request.query if request.query.startswith(".") else "")
    if path.suffix != ".json":
        return text
    data = json.loads(text)
    if selector:
        selected = _json_path(data, selector)
        return selected if isinstance(selected, str) else _json_dump(selected)
    if isinstance(data, dict) and isinstance(data.get("raw"), str):
        return str(data["raw"])
    return _json_dump(data)


def _search_file(path: Path, query: str) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".json":
        return _search_json(text, query)
    if path.suffix == ".jsonl":
        return _search_jsonl(text, query)
    return _search_text(text, query)


def _search_json(text: str, query: str) -> str:
    data = json.loads(text)
    if query.startswith("."):
        return _json_dump(_json_path(data, query))
    return _search_text(_json_dump(data), query)


def _search_jsonl(text: str, query: str) -> str:
    matches: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if query.startswith("."):
            try:
                matches.append(_json_dump(_json_path(json.loads(line), query)))
            except Exception:
                continue
        elif _contains(line, query):
            matches.append(line)
    return "\n".join(matches) or "未找到匹配片段"


def _search_text(text: str, query: str) -> str:
    paragraphs = re.split(r"\n\s*\n", text)
    matches = [part.strip() for part in paragraphs if _contains(part, query)]
    if not matches:
        matches = [line for line in text.splitlines() if _contains(line, query)]
    return "\n\n".join(matches) if matches else "未找到匹配片段"


def _json_path(data: Any, expression: str) -> Any:
    current = data
    for token in _path_tokens(expression):
        if isinstance(token, int):
            current = current[token]
        elif isinstance(current, dict):
            current = current[token]
        else:
            raise ValueError(f"Cannot select {token!r}")
    return current


def _path_tokens(expression: str) -> list[str | int]:
    path = expression.strip().lstrip(".")
    if not path:
        return []
    tokens: list[str | int] = []
    for part in path.split("."):
        match = re.fullmatch(r"([^\[]+)(?:\[(\d+)])?", part)
        if not match:
            raise ValueError(f"Unsupported json path: {expression}")
        tokens.append(match.group(1))
        if match.group(2) is not None:
            tokens.append(int(match.group(2)))
    return tokens


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _contains(text: str, query: str) -> bool:
    return query.lower() in text.lower()


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit]


def _limit(value: int, default: int, maximum: int | None = None) -> int:
    if value <= 0:
        return default
    return min(value, maximum or default)


__all__ = [
    "ALLOWED_ROOTS",
    "DEFAULT_PAGE_CHARS",
    "HistoryReadRequest",
    "MAX_PAGE_CHARS",
    "MAX_SEARCH_CHARS",
    "read_history_content",
    "resolve_allowed",
]
