"""Card notification helper for scheduled task executor.

Handles scenario matching, LLM formatting, and card sending via
FeishuClient (app bot) or webhook (fallback).
Pure Python + asyncio. No FastAPI dependency.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from backend.common.feishu_card import CardRegistry, build_card_content
from backend.common.feishu_card_formatter import CardFormatter
from backend.common.logging import get_logger
from backend.core.s02_tools.builtin.feishu_client import FeishuClient
from backend.core.s02_tools.builtin.feishu_notify import _generate_sign

logger = get_logger(component="task_card_notify")


def extract_tool_names(messages: list[Any]) -> set[str]:
    """Extract all tool call names from message list."""
    names: set[str] = set()
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                names.add(tc.name)
    return names


def match_card_scenario(
    task_card_scenario: str | None,
    tool_names: set[str],
) -> str:
    """Three-level matching: manual override > auto match > default fallback."""
    if task_card_scenario:
        return task_card_scenario
    registry = CardRegistry()
    matched = registry.match_scenario(tool_names)
    return matched or "task_execution_report"


async def _build_card_variables(
    adapter: Any,
    model: str,
    agent_reply: str,
    meta: dict[str, str],
    scenario: str,
    registry: CardRegistry,
) -> tuple[str, dict[str, Any]]:
    """Build card variables via LLM formatter + meta merge.

    Returns (scenario, variables).
    """
    formatter = CardFormatter(adapter, model)
    try:
        llm_variables = await formatter.format(
            scenario=scenario,
            agent_reply=agent_reply or "(无输出)",
            tool_name="scheduled_task",
            tool_arguments={
                "task_name": meta.get("task_name", ""),
                "task_id": meta.get("task_id", ""),
            },
            registry=registry,
            existing_variables=meta,
        )
    except Exception:
        logger.warning("task_card_format_fallback")
        llm_variables = {
            "summary_md": (agent_reply or "(无输出)")[:300] + "...",
            "result_summary": (agent_reply or "(无输出)")[:300] + "...",
        }

    # meta overrides LLM-extracted values for accuracy
    variables: dict[str, Any] = {**llm_variables, **meta}
    # Feishu URL type requires object format, not plain string
    url_val = variables.get("report_url", "")
    if isinstance(url_val, str):
        variables["report_url"] = {
            "url": url_val or "about:blank",
            "pc_url": url_val or "about:blank",
            "android_url": url_val or "about:blank",
            "ios_url": url_val or "about:blank",
        }
    return scenario, variables


async def try_send_card(
    adapter: Any,
    model: str,
    agent_reply: str,
    meta: dict[str, str],
    tool_names: set[str],
    task_card_scenario: str | None = None,
    *,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
    feishu_client: FeishuClient | None = None,
    chat_id: str | None = None,
) -> bool:
    """Try to build and send a card notification.

    Supports two channels:
    - FeishuClient (app bot): set feishu_client + chat_id for card callback support
    - Webhook: set webhook_url for basic card delivery (no callback support)

    Returns True if card was sent successfully, False to signal text fallback.
    """
    try:
        registry = CardRegistry()
        scenario = match_card_scenario(task_card_scenario, tool_names)
        card_config = registry.get_scenario(scenario)
        if card_config is None:
            logger.info("task_card_scenario_missing", scenario=scenario)
            return False

        _, variables = await _build_card_variables(
            adapter, model, agent_reply, meta, scenario, registry,
        )
        card_content = build_card_content(scenario, variables, registry)

        # Channel 1: FeishuClient (app bot — supports card button callbacks)
        if feishu_client and chat_id:
            result = await feishu_client.send_message(
                chat_id=chat_id,
                content=card_content,
                msg_type="interactive",
            )
            code = result.get("code", -1)
            if code == 0:
                logger.info("task_card_sent", channel="app_bot", chat_id=chat_id)
                return True
            logger.warning("task_card_send_failed", channel="app_bot", code=code, error=str(result.get("msg", "")))

        # Channel 2: Webhook (no card callback support)
        if webhook_url:
            body: dict[str, Any] = {
                "msg_type": "interactive",
                "card": json.loads(card_content),
            }
            if webhook_secret:
                timestamp, sign = _generate_sign(webhook_secret)
                body["timestamp"] = timestamp
                body["sign"] = sign

            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.post(webhook_url, json=body)
                logger.info("task_card_sent", channel="webhook", status_code=resp.status_code)
            return True

        logger.warning("task_card_channel_missing")
        return False
    except Exception:
        logger.warning("task_card_send_fallback")
        return False


__all__ = ["extract_tool_names", "match_card_scenario", "try_send_card"]
