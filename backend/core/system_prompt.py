from __future__ import annotations

import platform


def build_system_prompt(workspace: str | None = None) -> str:
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
    if workspace:
        parts.append(f"当前工作目录: {workspace}")
    parts.append("回复使用中文。")
    return "\n".join(part for part in parts if part)


__all__ = ["build_system_prompt"]
