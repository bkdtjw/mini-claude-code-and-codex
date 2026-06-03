from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from backend.common.types import AgentConfig


class LoopGuardPrompt(BaseModel):
    kind: Literal["dead_end_reflection", "final_convergence"]
    content: str


class AgentLoopGuard:
    def __init__(self, config: AgentConfig) -> None:
        self._max_iterations = max(1, config.max_iterations)
        self._dead_end_iteration = max(1, config.dead_end_reflection_iteration)
        self._dead_end_emitted = False
        self._final_emitted = False

    def prompt_for_iteration(self, iteration: int) -> LoopGuardPrompt | None:
        remaining = self._max_iterations - iteration
        if remaining <= 0 and not self._final_emitted:
            self._final_emitted = True
            return LoopGuardPrompt(
                kind="final_convergence",
                content=_final_convergence_prompt(iteration, self._max_iterations),
            )
        if iteration >= self._dead_end_iteration and not self._dead_end_emitted:
            self._dead_end_emitted = True
            return LoopGuardPrompt(
                kind="dead_end_reflection",
                content=_dead_end_reflection_prompt(iteration),
            )
        return None


def _dead_end_reflection_prompt(iteration: int) -> str:
    return "\n".join(
        [
            "[死胡同反思]",
            f"你已经进行了 {iteration} 轮思考/工具调用，继续重复探索的收益可能很低。",
            "请先停下来判断：当前是否卡在错误路径、无关细节、重复读取、重复失败或目标不清。",
            "下一步只能选择一种策略：",
            "1. 明确换策略：换工具、换参数、缩小范围，说明为什么新策略不同。",
            "2. 已有信息足够：停止调用工具，直接输出阶段性结论或最终答案。",
            "3. 信息不足且无法推进：明确说明卡点，并向用户提出一个具体问题。",
            "不要继续进行没有新增信息的读取、搜索或重试。",
            "必须继续遵守本次任务原有的输出协议和格式；",
            "如果原任务要求 JSON、代码块或固定模板，最终输出仍必须使用该格式。",
        ]
    )


def _final_convergence_prompt(iteration: int, max_iterations: int) -> str:
    return "\n".join(
        [
            "[最终收口提示]",
            f"这是第 {iteration}/{max_iterations} 轮，已经到达本次 AgentLoop 的执行上限。",
            "本轮必须优先收口：如果没有绝对必要，不要再调用工具。",
            "请基于已有上下文给出最可靠的结论；如仍不能完成，说明已尝试路径、失败原因和下一步建议。",
            "必须继续遵守本次任务原有的输出协议和格式；",
            "如果原任务要求 JSON、代码块或固定模板，最终输出仍必须使用该格式。",
        ]
    )


__all__ = ["AgentLoopGuard", "LoopGuardPrompt"]
