from __future__ import annotations

import re
from typing import Any

from backend.core.s13_knowledge import KnowledgeService
from backend.core.s13_knowledge.errors import KnowledgeError

MOVE_PATTERN = re.compile(r"^(?:把)?\s*(?P<doc>.+?)\s*(?:移到|移动到|转到|转入)\s*(?P<kb>.+?)\s*$")


async def handle_kb_command(context: Any, text: str) -> bool:
    match = MOVE_PATTERN.match(text.strip())
    if match is None:
        return False
    source_kb_id = await context.handler._menu_state.get_current_kb(context.open_id)  # noqa: SLF001
    if not source_kb_id:
        await context.handler._send_chat_text(context.chat_id, "请先通过菜单选择知识库")  # noqa: SLF001
        return True
    document_query = _clean_target(match.group("doc"))
    target_kb_name = _clean_target(match.group("kb"))
    try:
        document, target = await KnowledgeService().move_document(
            source_kb_id,
            document_query,
            target_kb_name,
        )
    except KnowledgeError as exc:
        await context.handler._send_chat_text(context.chat_id, exc.message or "移动文档失败")  # noqa: SLF001
        return True
    await context.handler._menu_state.set_current_kb(context.open_id, target.id)  # noqa: SLF001
    await context.handler._send_chat_text(  # noqa: SLF001
        context.chat_id,
        f"已将 {document.filename} 移到知识库：{target.name}",
    )
    return True


def _clean_target(value: str) -> str:
    return value.strip().strip("「」《》\"' ")


__all__ = ["handle_kb_command"]
