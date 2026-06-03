from __future__ import annotations

import json
from typing import Any

from backend.common import LLMError
from backend.common.types import StreamChunk


def parse_stream_line(
    event_type: str,
    raw: str,
    provider: str,
    tool_blocks: dict[int, dict[str, Any]] | None = None,
) -> StreamChunk | None:
    if raw == "[DONE]" or event_type == "message_stop":
        return StreamChunk(type="done")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if event_type == "content_block_delta":
        return _delta_chunk(data, tool_blocks)
    if event_type == "content_block_start":
        return _start_chunk(data, tool_blocks)
    if event_type == "content_block_stop" and tool_blocks is not None:
        return _stop_chunk(data, tool_blocks)
    if event_type == "error":
        detail = data.get("error", {}).get("message", str(data))
        raise LLMError("STREAM_ERROR", detail, provider, None)
    return None


def _delta_chunk(
    data: dict[str, Any],
    tool_blocks: dict[int, dict[str, Any]] | None,
) -> StreamChunk | None:
    delta = data.get("delta", {})
    delta_type = delta.get("type")
    if delta_type == "input_json_delta" and tool_blocks is not None:
        index = int(data.get("index", 0))
        block = tool_blocks.setdefault(index, {"id": "", "name": "", "input": {}, "json": ""})
        block["json"] = f"{block.get('json', '')}{delta.get('partial_json', '')}"
        return None
    if delta_type == "thinking_delta" and delta.get("thinking"):
        return StreamChunk(type="reasoning", data=delta["thinking"])
    if delta_type == "text_delta" and delta.get("text"):
        return StreamChunk(type="text", data=delta["text"])
    return None


def _start_chunk(
    data: dict[str, Any],
    tool_blocks: dict[int, dict[str, Any]] | None,
) -> StreamChunk | None:
    block = data.get("content_block", {})
    if block.get("type") != "tool_use":
        return None
    if tool_blocks is None:
        return _tool_chunk(block.get("id", ""), block.get("name", ""), _as_record(block.get("input")))
    tool_blocks[int(data.get("index", 0))] = {
        "id": block.get("id", ""),
        "name": block.get("name", ""),
        "input": _as_record(block.get("input")),
        "json": "",
    }
    return None


def _stop_chunk(
    data: dict[str, Any],
    tool_blocks: dict[int, dict[str, Any]],
) -> StreamChunk | None:
    block = tool_blocks.pop(int(data.get("index", 0)), None)
    if block is None:
        return None
    arguments = _json_record(str(block.get("json", ""))) or _as_record(block.get("input"))
    return _tool_chunk(block.get("id", ""), block.get("name", ""), arguments)


def _tool_chunk(tool_id: Any, name: Any, arguments: dict[str, Any]) -> StreamChunk:
    return StreamChunk(
        type="tool_call",
        data={"id": str(tool_id), "name": str(name), "arguments": arguments},
    )


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_record(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return _as_record(value)


__all__ = ["parse_stream_line"]
