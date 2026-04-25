from __future__ import annotations

__all__ = [
    "AgentLoop",
    "ContextCompressor",
    "ThresholdPolicy",
    "TokenCounter",
    "ToolExecutor",
    "ToolRegistry",
    "create_sub_agent_task_queue",
    "init_agent_runtime",
]


def __getattr__(name: str) -> object:
    if name == "AgentLoop":
        from .s01_agent_loop import AgentLoop

        return AgentLoop
    if name in {"ToolExecutor", "ToolRegistry"}:
        from .s02_tools import ToolExecutor, ToolRegistry

        return {"ToolExecutor": ToolExecutor, "ToolRegistry": ToolRegistry}[name]
    if name == "create_sub_agent_task_queue":
        from .sub_agent_queue import create_sub_agent_task_queue

        return create_sub_agent_task_queue
    if name == "init_agent_runtime":
        from .runtime_init import init_agent_runtime

        return init_agent_runtime
    if name in {"ContextCompressor", "ThresholdPolicy", "TokenCounter"}:
        from .s06_context_compression import ContextCompressor, ThresholdPolicy, TokenCounter

        return {
            "ContextCompressor": ContextCompressor,
            "ThresholdPolicy": ThresholdPolicy,
            "TokenCounter": TokenCounter,
        }[name]
    raise AttributeError(name)
