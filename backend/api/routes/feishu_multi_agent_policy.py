from __future__ import annotations

from backend.config.settings import settings as app_settings
from backend.core.s05_skills.models import SubAgentPolicy

FEISHU_MULTI_AGENT_HINT = """

飞书多 Agent 任务只能使用 spawn_agent 工具创建子 agent，并等待工具返回后再汇总。
不要使用 dispatch_agent 或 orchestrate_agents。
用户通常只会用自然语言描述目标，不会手写 role/template/max_iterations。
当用户要求“多 agent / 多专家 / 分头排查 / 并行调研 / 多角色审查”时，你必须自己完成任务拆分：
1. 根据目标选择 2-5 个子任务，避免无意义拆分；
2. 为每个子任务自动选择 template、role、input、permission、max_iterations；
3. 简单任务 max_iterations 6-10，中等任务 10-16，复杂排查 16-24；
4. 默认 permission=readonly，只有用户明确要求实施改代码时才考虑 writable；
5. 每个子任务 input 必须写清交付物和禁止事项。
优先使用 spec_id；需要临时角色时必须提供 template + role + input。
允许的动态模板：research-specialist、code-reader、code-reviewer、test-strategist、verifier、synthesis-specialist、product-pm。
final-reviewer 是平台自动追加的最终发布审核专家；不要手动提前派遣它。
动态 role 可以写成“字节研究员”“阿里研究员”，但必须挂在固定模板下。
max_iterations 是单个子任务预算，会被平台 cap 限制；复杂任务可显式提高预算。
子 agent 返回后请直接汇总，不要再读取无关文件或执行无关 shell 命令。
"""

FEISHU_INLINE_SUB_AGENT_TOOLS = ("dispatch_agent", "orchestrate_agents")
FEISHU_INLINE_TEMPLATES = [
    "research-specialist",
    "code-reader",
    "code-reviewer",
    "test-strategist",
    "verifier",
    "synthesis-specialist",
    "product-pm",
]
FEISHU_INLINE_TOOLS = ["Read", "Glob", "Grep", "WebSearch", "browse_web", "read_history"]
FEISHU_SUB_AGENT_ROLES = [
    "runtime-architect", "security-reviewer", "test-strategist", "product-pm",
    "schema-reviewer", "code-reviewer", "tech-research", "daily-ai-news",
    "interview-daily", "researcher", "planner", "summarizer",
    "架构 reviewer", "安全 reviewer", "测试 reviewer", "产品 reviewer", "架构师",
    "安全审查员", "安全工程师", "测试负责人", "测试专家", "测试工程师",
    "产品经理", "产品负责人", "汇总 agent", "总结 agent", "研究员", "调研员",
]


def build_feishu_sub_agent_policy() -> SubAgentPolicy:
    return SubAgentPolicy(
        allowed_specs=FEISHU_SUB_AGENT_ROLES,
        max_concurrent=app_settings.sub_worker_max_concurrency,
        max_depth=1,
        allow_inline_roles=True,
        allowed_inline_templates=FEISHU_INLINE_TEMPLATES,
        allowed_inline_tools=FEISHU_INLINE_TOOLS,
        max_iterations_default=12,
        max_iterations_cap=40,
        role_name_max_length=50,
        enable_legacy_tools=False,
    )


__all__ = [
    "FEISHU_INLINE_SUB_AGENT_TOOLS",
    "FEISHU_MULTI_AGENT_HINT",
    "build_feishu_sub_agent_policy",
]
