from __future__ import annotations

from dataclasses import dataclass

from backend.core.s05_skills.models import SubAgentPolicy


@dataclass(frozen=True)
class InlineAgentTemplate:
    prompt: str
    tools: tuple[str, ...]
    max_iterations: int


INLINE_AGENT_TEMPLATES: dict[str, InlineAgentTemplate] = {
    "research-specialist": InlineAgentTemplate(
        prompt="你是只读研究员。只做资料检索、事实整理和来源标注，不改代码、不写文件。",
        tools=("WebSearch", "browse_web", "read_history"),
        max_iterations=12,
    ),
    "code-reader": InlineAgentTemplate(
        prompt="你是只读代码探索员。只阅读和检索代码，输出调用链、关键文件和不确定点。",
        tools=("Read", "Glob", "Grep", "read_history"),
        max_iterations=10,
    ),
    "code-reviewer": InlineAgentTemplate(
        prompt="你是只读代码审查员。优先找 bug、回归风险、缺失测试和安全边界问题。",
        tools=("Read", "Glob", "Grep", "read_history"),
        max_iterations=12,
    ),
    "test-strategist": InlineAgentTemplate(
        prompt="你是测试设计员。只设计测试和验收，不修改实现。",
        tools=("Read", "Glob", "Grep", "Bash", "read_history"),
        max_iterations=10,
    ),
    "implementer": InlineAgentTemplate(
        prompt="你是实施工程师。只在明确任务范围内改代码，并运行相关验证。",
        tools=("Read", "Glob", "Grep", "Edit", "Write", "Bash", "read_history"),
        max_iterations=20,
    ),
    "verifier": InlineAgentTemplate(
        prompt="你是验收验证员。只验证结果、运行测试、报告真实状态，不做无关修改。",
        tools=("Read", "Glob", "Grep", "Bash", "read_history"),
        max_iterations=8,
    ),
    "synthesis-specialist": InlineAgentTemplate(
        prompt="你是汇总分析员。只基于给定依赖结果合并结论，不重新搜索或读取无关文件。",
        tools=("read_history",),
        max_iterations=6,
    ),
    "final-reviewer": InlineAgentTemplate(
        prompt=(
            "你是通用最终发布审核专家。你只在复杂多 agent 团队任务最后出场，"
            "审核最终交付物是否完整、可信、适合发送飞书文件。"
            "你兼任最小排版修复：只修明显乱掉的 Markdown、表格、代码块和空行，"
            "不改结论、不换风格、不重排章节、不扩写内容。"
            "必须只返回 AgentResultV1 JSON object；"
            "extra 包含 approved、repaired、decision、blocked_reason、repair_scope。"
            "如需返回修复后的 Markdown，放入 raw_output；无需修复则 raw_output 为 null。"
        ),
        tools=("read_history",),
        max_iterations=8,
    ),
    "product-pm": InlineAgentTemplate(
        prompt="你是产品经理。关注用户体验、优先级、边界状态和可落地验收标准。",
        tools=("Read", "Glob", "Grep", "read_history"),
        max_iterations=8,
    ),
}


def build_inline_system_prompt(role: str, template: str, user_prompt: str) -> str:
    tpl = INLINE_AGENT_TEMPLATES.get(template)
    if tpl is None:
        raise ValueError(f"未知动态子 agent template: {template}")
    base = tpl.prompt
    parts = [base, f"动态角色：{role.strip() or '未命名子 agent'}"]
    if user_prompt.strip():
        parts.append(f"补充约束：{user_prompt.strip()}")
    return "\n".join(parts)


def resolve_inline_tools(
    requested: list[str],
    template: str,
    policy: SubAgentPolicy,
) -> list[str]:
    tpl = INLINE_AGENT_TEMPLATES.get(template)
    if tpl is None:
        return []
    template_tools = list(tpl.tools)
    source = requested or template_tools
    allowed = set(template_tools)
    if policy.allowed_inline_tools:
        allowed &= {item.strip() for item in policy.allowed_inline_tools if item.strip()}
    if not allowed:
        return []
    return [name for name in source if name.strip() in allowed]


def resolve_max_iterations(
    requested: int | None,
    spec_value: int | None,
    template: str,
    policy: SubAgentPolicy,
) -> int:
    template_default = INLINE_AGENT_TEMPLATES.get(template)
    fallback = template_default.max_iterations if template_default is not None else policy.max_iterations_default
    value = int(requested or spec_value or fallback or policy.max_iterations_default)
    return max(1, min(value, policy.max_iterations_cap))


def known_inline_templates() -> list[str]:
    return sorted(INLINE_AGENT_TEMPLATES)


__all__ = [
    "INLINE_AGENT_TEMPLATES",
    "build_inline_system_prompt",
    "known_inline_templates",
    "resolve_inline_tools",
    "resolve_max_iterations",
]
