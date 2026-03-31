from __future__ import annotations

import json

from backend.common.types import Message, ToolDefinition


class TokenCounter:
    @staticmethod
    def _estimate_text_tokens(text: str) -> int:
        return len(text) // 4

    def estimate_messages_tokens(self, messages: list[Message]) -> int:
        total = 0
        for message in messages:
            total += self._estimate_text_tokens(message.content)
            for tool_call in message.tool_calls or []:
                arguments = json.dumps(
                    tool_call.arguments,
                    default=str,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                total += self._estimate_text_tokens(arguments)
            for tool_result in message.tool_results or []:
                total += self._estimate_text_tokens(tool_result.output)
        return total

    def estimate_tools_tokens(self, definitions: list[ToolDefinition]) -> int:
        total = 0
        for definition in definitions:
            tool_text = json.dumps(
                definition.model_dump(),
                default=str,
                ensure_ascii=False,
                sort_keys=True,
            )
            total += self._estimate_text_tokens(tool_text)
        return total


__all__ = ["TokenCounter"]
