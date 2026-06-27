from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from backend.adapters.base import LLMAdapter
from backend.common.metrics import incr
from backend.common.types import LLMRequest, Message

ResultStatus = Literal["passed", "warning", "failed", "unparsed"]
FindingSeverity = Literal["P0", "P1", "P2"]
DEFAULT_MAX_REPAIR_ATTEMPTS = 2
MAX_REPAIR_INPUT_CHARS = 12000
REPAIR_TIMEOUT_SECONDS = 20.0


class ResultContractError(ValueError):
    pass


class Finding(BaseModel):
    severity: FindingSeverity
    title: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    recommendation: str = ""


class AgentResultV1(BaseModel):
    status: ResultStatus
    summary: str = Field(min_length=1)
    findings: list[Finding] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
    raw_output: str | None = None


def parse_agent_result(raw_output: str) -> AgentResultV1:
    try:
        value = json.loads(_extract_json(raw_output))
        if not isinstance(value, dict):
            raise ResultContractError("结果必须是 JSON object")
        return AgentResultV1.model_validate(value)
    except (json.JSONDecodeError, ValidationError, ResultContractError) as exc:
        raise ResultContractError(str(exc)) from exc


async def coerce_agent_result(
    raw_output: str,
    adapter: LLMAdapter | None = None,
    model: str = "",
    max_repair_attempts: int = DEFAULT_MAX_REPAIR_ATTEMPTS,
    repair_timeout_seconds: float = REPAIR_TIMEOUT_SECONDS,
) -> AgentResultV1:
    try:
        parsed = parse_agent_result(raw_output)
        await incr("sub_agent_result_parsed")
        return parsed
    except ResultContractError as first_error:
        last_error = str(first_error)
    if adapter is None or not model:
        await incr("sub_agent_result_fallbacks")
        return fallback_agent_result(raw_output, last_error)
    if len(raw_output) > MAX_REPAIR_INPUT_CHARS:
        reason = f"{last_error}; output too large for LLM repair ({len(raw_output)} chars)"
        await incr("sub_agent_result_fallbacks")
        return fallback_agent_result(raw_output, reason)
    candidate = raw_output
    for _ in range(max_repair_attempts):
        try:
            candidate = await asyncio.wait_for(
                request_agent_result_repair(adapter, model, candidate, last_error),
                timeout=repair_timeout_seconds,
            )
            repaired = parse_agent_result(candidate)
            await incr("sub_agent_result_repaired")
            return repaired
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
    await incr("sub_agent_result_fallbacks")
    return fallback_agent_result(raw_output, last_error)


async def request_agent_result_repair(
    adapter: LLMAdapter,
    model: str,
    bad_output: str,
    error: str,
) -> str:
    try:
        response = await adapter.complete(
            LLMRequest(
                model=model,
                system_prompt=_repair_system_prompt(),
                messages=[Message(role="user", content=_repair_user_prompt(bad_output, error))],
                temperature=0.0,
                max_tokens=4096,
            )
        )
        return response.content
    except Exception as exc:  # noqa: BLE001
        raise ResultContractError(f"结果返修调用失败: {exc}") from exc


def fallback_agent_result(raw_output: str, error: str) -> AgentResultV1:
    return AgentResultV1(
        status="unparsed",
        summary="原始输出无法解析，已降级保存",
        findings=[
            Finding(
                severity="P1",
                title="子 agent 输出格式错误",
                evidence=[error[:500]],
                recommendation="检查该 role 的 prompt 或 result_contract",
            )
        ],
        raw_output=raw_output,
    )


def _extract_json(raw_output: str) -> str:
    text = raw_output.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.I)
    if fenced:
        text = fenced.group(1).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _repair_system_prompt() -> str:
    return (
        "你只负责把子 agent 的原始输出修正为合法 JSON。"
        "只返回 JSON object，不要 Markdown，不要解释。"
        "JSON 必须符合 AgentResultV1: "
        "status 为 passed/warning/failed/unparsed; "
        "summary 为非空字符串; findings 为数组，每项包含 "
        "severity(P0/P1/P2)、title、evidence、recommendation; "
        "artifacts、next_steps 为字符串数组; extra 为 object; raw_output 可为字符串或 null。"
    )


def _repair_user_prompt(bad_output: str, error: str) -> str:
    return (
        f"校验错误:\n{error}\n\n"
        "请把下面原始输出改写为合法 AgentResultV1 JSON。"
        "不要重做任务，只修正格式并保留原意。\n\n"
        f"原始输出:\n{bad_output}"
    )


__all__ = [
    "AgentResultV1",
    "DEFAULT_MAX_REPAIR_ATTEMPTS",
    "Finding",
    "MAX_REPAIR_INPUT_CHARS",
    "REPAIR_TIMEOUT_SECONDS",
    "ResultContractError",
    "coerce_agent_result",
    "fallback_agent_result",
    "parse_agent_result",
    "request_agent_result_repair",
]
