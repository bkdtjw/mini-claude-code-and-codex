from __future__ import annotations

from typing import Any

from backend.common.types import LLMRequest


def apply_thinking_payload(payload: dict[str, Any], request: LLMRequest) -> None:
    model = str(payload.get("model", "")).lower()
    if not is_kimi_thinking_model(model):
        return
    if request.thinking:
        payload["thinking"] = {"type": "enabled"}
        payload["temperature"] = 1.0
        payload["max_tokens"] = max(int(payload.get("max_tokens") or 0), 16000)
        return
    payload["thinking"] = {"type": "disabled"}


def is_kimi_thinking_model(model: str) -> bool:
    return (
        "kimi-k2-thinking" in model
        or "kimi-k2.5" in model
        or "kimi-k2.6" in model
    )


__all__ = ["apply_thinking_payload", "is_kimi_thinking_model"]
