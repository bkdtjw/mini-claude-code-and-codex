from __future__ import annotations

from datetime import datetime

from backend.common.types import Message, ToolCall, ToolResult
from backend.storage.serializers import to_message, to_message_record


def test_message_serializers_preserve_tool_state_and_provider_metadata() -> None:
    message = Message(
        id="msg_001",
        role="assistant",
        content="answer",
        tool_calls=[ToolCall(id="call_1", name="echo", arguments={"text": "hello"})],
        tool_results=[ToolResult(tool_call_id="call_1", output="ok")],
        timestamp=datetime.utcnow(),
        provider_metadata={"thinking_blocks": [{"type": "thinking", "thinking": "step"}], "thinking": "step"},
    )

    record = to_message_record("session_1", message)
    restored = to_message(record)

    assert record.provider_metadata_json is not None
    assert restored.tool_calls is not None
    assert restored.tool_calls[0].arguments == {"text": "hello"}
    assert restored.tool_results is not None
    assert restored.tool_results[0].output == "ok"
    assert restored.provider_metadata["thinking"] == "step"
    assert restored.provider_metadata["thinking_blocks"][0]["type"] == "thinking"
