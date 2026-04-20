"""LLM-based card formatter — converts agent reply into card variable JSON.

Pure Python + asyncio. Depends on LLMAdapter (injected), not on httpx or FastAPI.
"""
from __future__ import annotations

import json
from typing import Any

from backend.adapters.base import LLMAdapter
from backend.common.feishu_card import (
    CardRegistry,
    FeishuCardError,
    build_formatter_prompt,
)
from backend.common.logging import get_logger
from backend.common.types import LLMRequest, Message

logger = get_logger(component="feishu_card_formatter")


class CardFormatter:
    """Uses an LLM to reformat an agent reply into card template variables."""

    def __init__(self, adapter: LLMAdapter, model: str) -> None:
        self._adapter = adapter
        self._model = model

    async def format(
        self,
        scenario: str,
        agent_reply: str,
        tool_name: str,
        tool_arguments: dict[str, Any],
        registry: CardRegistry | None = None,
        existing_variables: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Call the LLM to produce card variable JSON for variables not yet filled.

        Args:
            existing_variables: Variables already collected by executor code
                (e.g. task_name, status_text, started_at). These will be excluded
                from LLM extraction — only missing variables are sent to the LLM.
        """
        reg = registry or CardRegistry()
        cfg = reg.get_scenario(scenario)
        if cfg is None:
            return {}

        existing = existing_variables or {}
        # Only ask LLM to extract variables not already provided
        missing_vars = {
            k: v for k, v in cfg.variables.items() if k not in existing
        }

        # Nothing for LLM to extract — skip the call entirely
        if not missing_vars:
            return {}

        prompt = build_formatter_prompt(
            scenario, agent_reply, tool_name, tool_arguments,
            variables_to_extract=missing_vars, registry=reg,
        )

        try:
            request = LLMRequest(
                model=self._model,
                messages=[Message(role="user", content=prompt)],
                temperature=0.2,
                max_tokens=2000,
            )
            response = await self._adapter.complete(request)
            raw = _clean_llm_json(response.content)

            variables: dict[str, str] = json.loads(raw)

            if not isinstance(variables, dict):
                raise FeishuCardError(
                    "CARD_FORMAT_TYPE_ERROR",
                    f"LLM returned non-object JSON: {type(variables).__name__}",
                )

            return {k: str(v) for k, v in variables.items()}

        except Exception:
            logger.warning("feishu_card_format_fallback", scenario=scenario)
            return _build_fallback(missing_vars, agent_reply)


def _clean_llm_json(raw: str) -> str:
    """Strip markdown fences and noise from LLM JSON output."""
    raw = raw.strip()

    # Remove markdown code block wrapping: ```json ... ``` or ``` ... ```
    if raw.startswith("```"):
        # Drop first line (```json or ```)
        first_newline = raw.find("\n")
        raw = raw[first_newline + 1:] if first_newline != -1 else ""
        # Drop trailing ```
        if "```" in raw:
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

    # LLM may prepend explanatory text before the JSON object
    if raw and not raw.startswith("{"):
        idx = raw.find("{")
        if idx != -1:
            raw = raw[idx:]

    if not raw:
        raise FeishuCardError("CARD_FORMAT_JSON_ERROR", "LLM returned empty response")

    return raw


def _build_fallback(
    missing_vars: dict[str, Any], agent_reply: str,
) -> dict[str, str]:
    """Generate fallback values when LLM formatting fails."""
    fallback: dict[str, str] = {}
    text = agent_reply or "(无输出)"
    for key in missing_vars:
        if "summary" in key.lower():
            fallback[key] = text[:300] + ("..." if len(text) > 300 else "")
        else:
            fallback[key] = ""
    return fallback


__all__ = ["CardFormatter"]
