from __future__ import annotations

import platform


def build_system_prompt(workspace: str | None = None) -> str:
    os_name = platform.system()
    if os_name == "Windows":
        shell_info = "cmd.exe。使用 dir（不要用 ls）、type（不要用 cat）、cd 等 Windows 命令。"
    else:
        shell_info = "bash。使用 ls、cat、cd 等 Unix 命令。"

    parts = [
        f"你是一个编程助手。当前操作系统: {os_name}。",
        f"执行 shell 命令时使用 {shell_info}",
        "绝对不要使用 Linux 命令（pwd、ls、cat、grep），只用 Windows 命令（dir、type、cd、findstr）。" if os_name == "Windows" else "",
    ]
    if workspace:
        parts.append(f"当前工作目录: {workspace}")
    parts.append("回复使用中文。")
    return "\n".join(part for part in parts if part)


__all__ = ["build_system_prompt"]
