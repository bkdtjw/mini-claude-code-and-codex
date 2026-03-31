from __future__ import annotations

import json

from backend.common.types import Message, Session, SessionConfig, ToolCall, ToolResult
from backend.storage.models import MessageRecord, SessionRecord


def _dump_models(items: list[ToolCall] | list[ToolResult] | None) -> str | None:
    if not items:
        return None
    return json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False)


def _load_tool_calls(payload: str | None) -> list[ToolCall] | None:
    if not payload:
        return None
    return [ToolCall.model_validate(item) for item in json.loads(payload)]


def _load_tool_results(payload: str | None) -> list[ToolResult] | None:
    if not payload:
        return None
    return [ToolResult.model_validate(item) for item in json.loads(payload)]


def _dump_provider_metadata(metadata: dict[str, object]) -> str | None:
    if not metadata:
        return None
    return json.dumps(metadata, ensure_ascii=False)


def _load_provider_metadata(payload: str | None) -> dict[str, object]:
    if not payload:
        return {}
    loaded = json.loads(payload)
    return loaded if isinstance(loaded, dict) else {}


def to_message_record(session_id: str, message: Message) -> MessageRecord:
    return MessageRecord(
        id=message.id,
        session_id=session_id,
        role=message.role,
        content=message.content,
        tool_calls_json=_dump_models(message.tool_calls),
        tool_results_json=_dump_models(message.tool_results),
        provider_metadata_json=_dump_provider_metadata(message.provider_metadata),
        timestamp=message.timestamp,
    )


def to_message(record: MessageRecord) -> Message:
    return Message(
        id=record.id,
        role=record.role,
        content=record.content,
        tool_calls=_load_tool_calls(record.tool_calls_json),
        tool_results=_load_tool_results(record.tool_results_json),
        timestamp=record.timestamp,
        provider_metadata=_load_provider_metadata(record.provider_metadata_json),
    )


def to_session(record: SessionRecord, messages: list[Message] | None = None) -> Session:
    return Session(
        id=record.id,
        config=SessionConfig(
            model=record.model,
            provider=record.provider,
            system_prompt=record.system_prompt,
            max_tokens=record.max_tokens,
            temperature=record.temperature,
        ),
        messages=messages or [],
        created_at=record.created_at,
        status=record.status,
    )


__all__ = ["to_message", "to_message_record", "to_session"]
