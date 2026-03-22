from __future__ import annotations


class AgentError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class ToolError(AgentError):
    def __init__(
        self, code: str, message: str, tool_name: str, tool_call_id: str
    ) -> None:
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id
        super().__init__(code=code, message=message)


class LLMError(AgentError):
    def __init__(
        self, code: str, message: str, provider: str, status_code: int | None = None
    ) -> None:
        self.status_code = status_code
        self.provider = provider
        super().__init__(code=code, message=message)


__all__ = ["AgentError", "ToolError", "LLMError"]
