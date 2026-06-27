from __future__ import annotations

from backend.api.routes.chat_completions import _chat_system_prompt, _without_system
from backend.common.types import Message


def test_chat_completions_system_prompt_keeps_kernel_and_caller_system() -> None:
    messages = [
        Message(role="system", content="你必须用项目规范回答"),
        Message(role="user", content="hello"),
    ]

    prompt = _chat_system_prompt(messages)
    restored = _without_system(messages)

    assert "你是一个编程助手" in prompt
    assert "调用方 system 消息" in prompt
    assert "你必须用项目规范回答" in prompt
    assert [message.role for message in restored] == ["user"]
