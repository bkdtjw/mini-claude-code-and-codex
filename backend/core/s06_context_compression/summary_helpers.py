from __future__ import annotations

from backend.common.types import Message


SUMMARY_PREFIXES = ("[对话历史摘要]", "[压缩摘要]")


def is_summary_message(message: Message) -> bool:
    content = message.content.lstrip()
    return message.kind == "summary" or content.startswith(SUMMARY_PREFIXES)


def build_summary_message(summary: str, archive_path: str = "", error: str = "") -> Message:
    body = summary.strip()
    if archive_path and "无损备份:" not in body:
        body = f"{body}\n无损备份: {archive_path}"
    if error:
        body = f"{body}\n压缩降级原因: {error}"
    return Message(
        role="user",
        kind="summary",
        content=f"<conversation_summary>\n{body}\n</conversation_summary>",
    )


__all__ = ["SUMMARY_PREFIXES", "build_summary_message", "is_summary_message"]
