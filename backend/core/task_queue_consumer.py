from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Any

from backend.common.errors import AgentError
from backend.common.logging import get_logger, get_worker_id
from backend.core.s05_skills import AgentRuntime
from backend.core.task_queue import TaskPayload, TaskQueue

logger = get_logger(component="sub_agent_consumer")


@dataclass
class SubAgentConsumerContext:
    queue: TaskQueue
    runtime: AgentRuntime


async def consume_next_sub_agent_task(context: SubAgentConsumerContext) -> bool:
    try:
        payload = await context.queue.claim(get_worker_id())
        if payload is None:
            return False
        logger.info(
            "sub_agent_task_claimed",
            task_id=payload.task_id,
            worker_id=payload.worker_id,
            spec_id=str(payload.input_data.get("spec_id", "")),
            role=str(payload.input_data.get("role", "")),
        )
        await execute_sub_agent_task(payload, context)
        return True
    except AgentError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AgentError("SUB_AGENT_CONSUMER_CLAIM_ERROR", str(exc)) from exc


async def execute_sub_agent_task(
    payload: TaskPayload,
    context: SubAgentConsumerContext,
) -> None:
    timeout_seconds = _timeout_seconds(payload.input_data)
    started_at = monotonic()
    try:
        logger.info(
            "sub_agent_task_execute_start",
            task_id=payload.task_id,
            payload_worker_id=payload.worker_id,
            spec_id=str(payload.input_data.get("spec_id", "")),
            role=str(payload.input_data.get("role", "")),
        )
        loop = await _build_sub_agent_loop(payload.input_data, context.runtime, payload.task_id)
        result = await asyncio.wait_for(
            loop.run(str(payload.input_data.get("input", ""))),
            timeout=timeout_seconds,
        )
        await context.queue.complete(
            payload.task_id,
            {
                "content": getattr(result, "content", "") or str(result),
                "tool_call_count": _tool_call_count(loop.messages),
            },
        )
        logger.info(
            "sub_agent_task_completed",
            task_id=payload.task_id,
            worker_id=payload.worker_id,
            status="succeeded",
            duration_ms=int((monotonic() - started_at) * 1000),
        )
    except TimeoutError:
        error = f"子 agent 执行超时（{timeout_seconds}s）"
        await _safe_fail(context.queue, payload.task_id, error)
        logger.error(
            "sub_agent_task_failed",
            task_id=payload.task_id,
            worker_id=payload.worker_id,
            error=error,
            duration_ms=int((monotonic() - started_at) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        error = f"子 agent 执行失败：{exc}"
        await _safe_fail(context.queue, payload.task_id, error)
        logger.exception(
            "sub_agent_task_failed",
            task_id=payload.task_id,
            worker_id=payload.worker_id,
            error=error,
            duration_ms=int((monotonic() - started_at) * 1000),
        )


async def _build_sub_agent_loop(
    input_data: dict[str, Any],
    runtime: AgentRuntime,
    task_id: str,
) -> Any:
    try:
        spec_id = str(input_data.get("spec_id", "")).strip()
        workspace = str(input_data.get("workspace", "")).strip()
        if spec_id:
            return await runtime.create_loop_from_id(
                spec_id,
                workspace=workspace,
                session_id=f"sub-agent:{task_id}",
                is_sub_agent=True,
            )
        return await runtime.create_loop_inline(
            role=str(input_data.get("role", "sub_agent")),
            system_prompt=str(input_data.get("system_prompt", "")),
            tools=[str(name) for name in input_data.get("tools", []) if str(name).strip()],
            model=str(input_data.get("model", "")),
            workspace=workspace,
            is_sub_agent=True,
        )
    except AgentError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AgentError("SUB_AGENT_LOOP_BUILD_ERROR", str(exc)) from exc


def _timeout_seconds(input_data: dict[str, Any]) -> float:
    raw_timeout = input_data.get("timeout_seconds", 120)
    try:
        timeout_seconds = float(raw_timeout)
    except (TypeError, ValueError):
        return 120.0
    return timeout_seconds if timeout_seconds > 0 else 120.0


def _tool_call_count(messages: list[Any]) -> int:
    return sum(
        len(message.tool_calls)
        for message in messages
        if getattr(message, "role", "") == "assistant" and getattr(message, "tool_calls", None)
    )


async def _safe_fail(queue: TaskQueue, task_id: str, error: str) -> None:
    try:
        await queue.fail(task_id, error)
    except Exception as fail_exc:  # noqa: BLE001
        logger.error(
            "sub_agent_task_fail_error",
            task_id=task_id,
            original_error=error,
            fail_error=str(fail_exc),
        )


__all__ = [
    "SubAgentConsumerContext",
    "consume_next_sub_agent_task",
    "execute_sub_agent_task",
]
