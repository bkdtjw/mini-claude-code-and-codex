from __future__ import annotations

import json

from backend.common.types import MCPServerConfig, Message, ProviderConfig, Session, SessionConfig, ToolCall, ToolResult
from backend.core.s07_task_system.models import NotifyConfig, OutputConfig, ScheduledTask
from backend.storage.models import MCPServerRecord, MessageRecord, ProviderRecord, ScheduledTaskRecord, SessionRecord


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


def _dump_json(payload: list[object] | dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _load_list(payload: str) -> list[object]:
    loaded = json.loads(payload) if payload else []
    return loaded if isinstance(loaded, list) else []


def _load_dict(payload: str) -> dict[str, object]:
    loaded = json.loads(payload) if payload else {}
    return loaded if isinstance(loaded, dict) else {}


def _load_provider_metadata(payload: str | None) -> dict[str, object]:
    if not payload:
        return {}
    return _load_dict(payload)


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


def to_provider_record(config: ProviderConfig) -> ProviderRecord:
    return ProviderRecord(
        id=config.id,
        name=config.name,
        provider_type=config.provider_type.value,
        base_url=config.base_url,
        api_key=config.api_key,
        default_model=config.default_model,
        available_models_json=_dump_json(config.available_models),
        extra_headers_json=_dump_json(config.extra_headers),
        is_default=config.is_default,
        enabled=config.enabled,
    )


def to_provider_config(record: ProviderRecord) -> ProviderConfig:
    return ProviderConfig(
        id=record.id,
        name=record.name,
        provider_type=record.provider_type,
        base_url=record.base_url,
        api_key=record.api_key,
        default_model=record.default_model,
        available_models=[str(item) for item in _load_list(record.available_models_json)],
        extra_headers={str(key): str(value) for key, value in _load_dict(record.extra_headers_json).items()},
        is_default=record.is_default,
        enabled=record.enabled,
    )


def to_mcp_server_record(config: MCPServerConfig) -> MCPServerRecord:
    return MCPServerRecord(
        id=config.id,
        name=config.name,
        transport=config.transport,
        command=config.command,
        args_json=_dump_json(config.args),
        env_json=_dump_json(config.env),
        url=config.url,
        enabled=config.enabled,
    )


def to_mcp_server_config(record: MCPServerRecord) -> MCPServerConfig:
    return MCPServerConfig(
        id=record.id,
        name=record.name,
        transport=record.transport,
        command=record.command,
        args=[str(item) for item in _load_list(record.args_json)],
        env={str(key): str(value) for key, value in _load_dict(record.env_json).items()},
        url=record.url,
        enabled=record.enabled,
    )


def to_task_record(task: ScheduledTask) -> ScheduledTaskRecord:
    return ScheduledTaskRecord(
        id=task.id,
        name=task.name,
        cron=task.cron,
        timezone=task.timezone,
        prompt=task.prompt,
        spec_id=task.spec_id,
        notify_json=_dump_json(task.notify.model_dump(mode="json")),
        output_json=_dump_json(task.output.model_dump(mode="json")),
        card_scenario=task.card_scenario,
        enabled=task.enabled,
        created_at=task.created_at,
        last_run_at=task.last_run_at,
        last_run_status=task.last_run_status,
        last_run_output=task.last_run_output,
    )


def to_scheduled_task(record: ScheduledTaskRecord) -> ScheduledTask:
    return ScheduledTask(
        id=record.id,
        name=record.name,
        cron=record.cron,
        timezone=record.timezone,
        prompt=record.prompt,
        spec_id=record.spec_id,
        notify=NotifyConfig.model_validate(_load_dict(record.notify_json)),
        output=OutputConfig.model_validate(_load_dict(record.output_json)),
        card_scenario=record.card_scenario,
        enabled=record.enabled,
        created_at=record.created_at,
        last_run_at=record.last_run_at,
        last_run_status=record.last_run_status,
        last_run_output=record.last_run_output,
    )


__all__ = [
    "to_mcp_server_config",
    "to_mcp_server_record",
    "to_message",
    "to_message_record",
    "to_provider_config",
    "to_provider_record",
    "to_scheduled_task",
    "to_session",
    "to_task_record",
]
