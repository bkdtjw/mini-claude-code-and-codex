from __future__ import annotations

from typing import Any

from backend.core.s13_knowledge import KnowledgeService
from backend.core.s13_knowledge.errors import KnowledgeError

CANCEL_WORDS = {"取消", "算了"}


async def start_kb_rename(context: Any, kb: Any) -> None:
    await context.handler._menu_state.set_pending(context.open_id, "awaiting_kb_rename")  # noqa: SLF001
    await context.handler._send_to_user(  # noqa: SLF001
        context.open_id,
        f"请回复新的知识库名称。当前知识库：{kb.name}\n回复「取消」可退出。",
    )


async def rename_kb_from_text(context: Any, text: str) -> None:
    await context.handler._menu_state.clear_pending(context.open_id)  # noqa: SLF001
    if text.strip() in CANCEL_WORDS:
        await context.handler._send_chat_text(context.chat_id, "已取消重命名")  # noqa: SLF001
        return
    kb_id = await context.handler._menu_state.get_current_kb(context.open_id)  # noqa: SLF001
    if not kb_id:
        await context.handler._send_chat_text(context.chat_id, "请先通过菜单选择知识库")  # noqa: SLF001
        return
    try:
        kb = await KnowledgeService().rename_kb(kb_id, text)
    except KnowledgeError as exc:
        await context.handler._send_chat_text(context.chat_id, exc.message or "重命名知识库失败")  # noqa: SLF001
        return
    await context.handler._menu_state.set_current_kb(context.open_id, kb.id)  # noqa: SLF001
    await context.handler._send_chat_text(context.chat_id, f"已重命名知识库：{kb.name}")  # noqa: SLF001


__all__ = ["rename_kb_from_text", "start_kb_rename"]
