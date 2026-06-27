from __future__ import annotations

import platform

from backend.core.s02_tools.commerce_tool_guidance import COMMERCE_TOOL_RESULT_RULES

COMPRESSION_RETENTION_TEMPLATE = """
压缩时按以下优先级保留信息：
P1 绝不删：标识符（商品ID、短链URL、淘口令、item_id、shop_id、订单号）。标识符一个字符都不能改。
P2 绝不删：用户决策（选了什么、排除了什么、为什么）、用户纠正、否定例外、具体数字、用户约束。
P3 保留结论：失败路径（什么失败了、原因、换了什么策略）、因果关系、架构决策、环境状态变更。
P4 保留摘要：关键结果（top 3 名称+价格，不需要完整 JSON）、未完成任务、工具调用结论。
P5 可删但存文件：工具原始输出（写入文件，保留路径）
P6 可删：日常寒暄、确认语句
标识符必须原样保留，不得修改任何字符。
当摘要或工具结果只给出文件路径且信息不足时，调用 read_history 回查原文。
""".strip()


COMMERCE_TOOL_KEYWORDS = (
    "taobao",
    "tmall",
    "jd",
    "jingdong",
    "pinduoduo",
    "coupon",
    "zhetaoke",
    "product_coupon",
    "product_search",
    "product_source_health_check",
)


def build_system_prompt() -> str:
    os_name = platform.system()
    if os_name == "Windows":
        shell_info = (
            "cmd.exe。使用 dir（不要用 ls）、type（不要用 cat）、cd、findstr "
            "等 Windows 命令。"
        )
        command_rule = (
            "绝对不要使用 Linux 命令（pwd、ls、cat、grep），只用 Windows 命令"
            "（dir、type、cd、findstr）。"
        )
    else:
        shell_info = "bash。使用 ls、cat、cd、grep 等 Unix 命令。"
        command_rule = "优先使用当前系统原生命令，不要混用其他操作系统的命令。"

    parts = [
        f"你是一个编程助手。当前操作系统: {os_name}。",
        f"执行 shell 命令时使用 {shell_info}",
        command_rule,
        "如果工具调用失败，必须先阅读错误输出，再决定是否调整命令。",
        "不要原样重复同一个失败命令；只有在参数、路径或策略发生变化时才允许重试，并说明为什么要重试。",
        (
            "如果连续 3 次工具调用失败，停止继续调用工具，直接向用户解释失败"
            "原因、当前限制和下一步建议。"
        ),
    ]
    parts.extend(
        [
            "你有 spawn_agent 工具可以派生子 agent 并行执行任务。",
            "多个子任务互不依赖、可以同时进行时，用 spawn_agent 一次传多个任务并行执行。",
            "子任务之间有先后依赖，或任务简单到你自己几步就能完成时，不要派子 agent。",
            "子 agent 执行完成后你会收到全部结果，请汇总后再回复用户。",
        ]
    )
    parts.append("回复使用中文。")
    return "\n".join(part for part in parts if part)


def build_runtime_context(workspace: str | None = None, tools: list[object] | None = None) -> str:
    parts: list[str] = []
    if workspace:
        parts.append(f"当前工作目录: {workspace}")
        parts.append("本地项目相关任务使用已提供的本地工具完成。")
        parts.append("browse_web 是浏览器自动化工具，用于观察和操作网页。")
    else:
        parts.append("当前没有选择工作目录。涉及本地文件的请求应先让用户选择工作区。")
    if tools and _has_commerce_tools(tools):
        parts.append(COMMERCE_TOOL_RESULT_RULES)
    return "\n".join(parts)


def _has_commerce_tools(tools: list[object]) -> bool:
    for tool in tools:
        name = str(getattr(tool, "name", "")).lower()
        if any(keyword in name for keyword in COMMERCE_TOOL_KEYWORDS):
            return True
    return False


__all__ = [
    "COMMERCE_TOOL_KEYWORDS",
    "COMPRESSION_RETENTION_TEMPLATE",
    "build_runtime_context",
    "build_system_prompt",
]
