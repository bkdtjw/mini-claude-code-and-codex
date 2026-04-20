from __future__ import annotations

import json
from typing import Any

from backend.common.logging import bound_log_context, get_log_context, new_trace_id


def build_feishu_log_context(chat_id: str) -> Any:
    current = get_log_context()
    trace_id = str(current.get("trace_id") or new_trace_id())
    session_id = str(current.get("session_id") or chat_id)
    return bound_log_context(trace_id=trace_id, session_id=session_id)


def extract_text(msg: dict[str, Any], msg_type: str) -> str | None:
    if msg_type != "text":
        return None
    try:
        content = json.loads(msg.get("content", "{}"))
    except (json.JSONDecodeError, TypeError):
        return None
    text: str = content.get("text", "")
    return text.strip() or None


def parse_slash_command(text: str) -> tuple[str, str]:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return "", stripped
    parts = stripped[1:].split(maxsplit=1)
    spec_id = parts[0] if parts else ""
    input_text = parts[1] if len(parts) > 1 else ""
    return spec_id, input_text


__all__ = ["build_feishu_log_context", "extract_text", "parse_slash_command"]
