from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from backend.api.routes import feishu_knowledge_response as kb_response
from backend.api.routes import feishu_knowledge_upload_batch as upload_batch
from backend.api.routes.feishu_handler_support import resolve_reply_text, resolve_session_model
from backend.api.routes.feishu_knowledge_cards import build_kb_switch_card
from backend.api.routes.feishu_knowledge_commands import handle_kb_command
from backend.api.routes.feishu_knowledge_rename import rename_kb_from_text, start_kb_rename
from backend.api.routes.feishu_runtime import build_agent_loop
from backend.core.s13_knowledge import KnowledgeService, SearchRequest
from backend.core.s13_knowledge.errors import KnowledgeError
from backend.core.system_prompt import build_system_prompt

CANCEL_WORDS = {"取消", "算了"}

@dataclass
class KbContext:
    handler: Any
    open_id: str
    chat_id: str
    message_id: str

async def handle_kb_menu(context: KbContext, event_key: str) -> bool:
    await context.handler._menu_state.clear_pending(context.open_id)  # noqa: SLF001
    if event_key == "kb_mode_on":
        kb = await _current_or_default(context)
        await context.handler._menu_state.set_mode(context.open_id, "knowledge")  # noqa: SLF001
        await context.handler._send_to_user(  # noqa: SLF001
            context.open_id,
            f"已开启知识库模式，我会优先从知识库检索内容回答。\n当前知识库：{kb.name}",
        )
        return True
    if event_key == "kb_switch":
        await _send_switch_card(context)
        return True
    if event_key == "kb_upload":
        kb = await _current_or_default(context)
        await context.handler._menu_state.set_pending(context.open_id, "awaiting_kb_file")  # noqa: SLF001
        await context.handler._send_to_user(  # noqa: SLF001
            context.open_id,
            f"请直接把文件发给我，将存入当前知识库：{kb.name}。\n"
            "支持 PDF、Word、Markdown、TXT，单文件不超过 20MB。",
        )
        return True
    if event_key == "kb_create":
        await context.handler._menu_state.set_pending(context.open_id, "awaiting_kb_name")  # noqa: SLF001
        await context.handler._send_to_user(context.open_id, "请回复新知识库的名称。例如：技术笔记")  # noqa: SLF001
        return True
    if event_key == "kb_rename":
        await start_kb_rename(context, await _current_or_default(context))
        return True
    return False

async def route_kb_text(context: KbContext, text: str) -> bool:
    pending = await context.handler._menu_state.get_pending(context.open_id)  # noqa: SLF001
    if pending == "awaiting_kb_name":
        await _create_kb_from_text(context, text)
        return True
    if pending == "awaiting_kb_rename":
        await rename_kb_from_text(context, text)
        return True
    if pending == "awaiting_kb_file":
        await context.handler._send_chat_text(context.chat_id, "请先发送文件或点菜单取消")  # noqa: SLF001
        return True
    if await handle_kb_command(context, text):
        return True
    mode = await context.handler._menu_state.get_mode(context.open_id)  # noqa: SLF001
    if mode == "knowledge":
        await answer_with_knowledge(context, text)
        return True
    return False

async def route_kb_file(context: KbContext, message: dict[str, Any]) -> bool:
    pending = await context.handler._menu_state.get_pending(context.open_id)  # noqa: SLF001
    if pending in {"awaiting_kb_name", "awaiting_kb_rename"}:
        await context.handler._send_chat_text(context.chat_id, "请先回复库名或点菜单取消")  # noqa: SLF001
        return True
    mode = await context.handler._menu_state.get_mode(context.open_id)  # noqa: SLF001
    if pending != "awaiting_kb_file" and mode != "knowledge":
        return False
    kb = await _current_or_default(context)
    content = _json_content(message)
    file_key = str(content.get("file_key", "") or content.get("file_id", ""))
    file_name = str(content.get("file_name", "") or content.get("name", "uploaded_file"))
    if not file_key:
        await context.handler._send_chat_text(context.chat_id, "文件消息缺少 file_key，无法入库")  # noqa: SLF001
        return True
    await upload_batch.add_file_to_upload_batch(
        context,
        upload_batch.FeishuFileItem(
            open_id=context.open_id,
            chat_id=context.chat_id,
            message_id=context.message_id,
            file_key=file_key,
            file_name=file_name,
            kb_id=kb.id,
            kb_name=kb.name,
            file_size=_file_size(content),
        ),
    )
    return True

async def answer_with_knowledge(context: KbContext, question: str) -> None:
    service = KnowledgeService()
    kb_id = await context.handler._menu_state.get_current_kb(context.open_id)  # noqa: SLF001
    kb = await service.get_kb(kb_id) if kb_id else None
    if kb is None:
        try:
            kb = await service.get_or_create_default_kb()
        except Exception:  # noqa: BLE001
            await context.handler._send_chat_text(context.chat_id, "请先通过菜单选择知识库")  # noqa: SLF001
            return
        await context.handler._menu_state.set_current_kb(context.open_id, kb.id)  # noqa: SLF001
    hits = await service.search(SearchRequest(query=question, kb_id=kb.id, top_k=5))
    if not hits:
        await context.handler._send_chat_text(context.chat_id, kb_response.build_empty_knowledge_reply(kb.name))  # noqa: E501, SLF001
        return
    prompt = _knowledge_prompt(hits)
    provider = await context.handler._resolve_provider(None)  # noqa: SLF001
    session = await context.handler._store.get(context.chat_id)  # noqa: SLF001
    model = resolve_session_model(session, provider)
    loop = await build_agent_loop(
        await context.handler._pm.get_adapter(provider.id),  # noqa: SLF001
        session_id=f"feishu-kb:{context.chat_id}:{context.message_id}",
        model=model,
        provider=provider.id,
        system_prompt=f"{build_system_prompt()}\n\n{prompt}",
        agent_runtime=context.handler._agent_runtime,  # noqa: SLF001
        spec_registry=context.handler._spec_registry,  # noqa: SLF001
        task_queue=context.handler._task_queue,  # noqa: SLF001
        owner_id=context.open_id or context.chat_id,
    )
    result = await loop.run(question)
    await context.handler._reply_loop_result(  # noqa: SLF001
        loop,
        context.message_id,
        kb_response.append_knowledge_footer(resolve_reply_text(result), kb.name, hits),
    )

async def _create_kb_from_text(context: KbContext, text: str) -> None:
    await context.handler._menu_state.clear_pending(context.open_id)  # noqa: SLF001
    if text.strip() in CANCEL_WORDS:
        await context.handler._send_chat_text(context.chat_id, "已取消新建")  # noqa: SLF001
        return
    try:
        kb = await KnowledgeService().create_kb(text)
    except KnowledgeError as exc:
        await context.handler._send_chat_text(context.chat_id, exc.message or "新建知识库失败")  # noqa: SLF001
        return
    await context.handler._menu_state.set_current_kb(context.open_id, kb.id)  # noqa: SLF001
    await context.handler._send_chat_text(context.chat_id, f"已新建并切换到知识库：{kb.name}")  # noqa: SLF001

async def _current_or_default(context: KbContext) -> Any:
    service = KnowledgeService()
    kb_id = await context.handler._menu_state.get_current_kb(context.open_id)  # noqa: SLF001
    kb = await service.get_kb(kb_id) if kb_id else None
    if kb is None:
        kb = await service.get_or_create_default_kb()
        await context.handler._menu_state.set_current_kb(context.open_id, kb.id)  # noqa: SLF001
    return kb

async def _send_switch_card(context: KbContext) -> None:
    service = KnowledgeService()
    current = await _current_or_default(context)
    kbs = await service.list_kbs()
    await context.handler._client.send_message(  # noqa: SLF001
        context.chat_id,
        json.dumps(build_kb_switch_card(kbs, current.id), ensure_ascii=False),
        msg_type="interactive",
    )

def _knowledge_prompt(hits: list[Any]) -> str:
    lines = ["以下是知识库检索内容，请基于这些回答并标注来源文档；若不足以回答则明确告知未找到："]
    for index, hit in enumerate(hits, start=1):
        lines.append(f"[{index}] 来源：{hit.document_name}#{hit.chunk_index}\n{hit.content}")
    return "\n\n".join(lines)


def _json_content(message: dict[str, Any]) -> dict[str, Any]:
    try:
        content = json.loads(message.get("content", "{}"))
        return content if isinstance(content, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _file_size(content: dict[str, Any]) -> int:
    try:
        return int(content.get("file_size", 0) or content.get("size", 0) or 0)
    except (TypeError, ValueError):
        return 0
__all__ = [
    "KbContext", "answer_with_knowledge", "handle_kb_menu", "route_kb_file", "route_kb_text",
]
