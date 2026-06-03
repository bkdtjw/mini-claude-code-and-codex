from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.common.errors import AgentError
from backend.core.s13_knowledge import KnowledgeBase, KnowledgeService, SearchHit, SearchRequest


class KnowledgeRunContext(BaseModel):
    message: str
    display_message: str = ""
    empty_reply: str = ""


async def prepare_knowledge_run(
    settings: Any,
    question: str,
    service: KnowledgeService | None = None,
) -> KnowledgeRunContext:
    try:
        if settings.mode != "knowledge":
            return KnowledgeRunContext(message=question)
        knowledge = service or KnowledgeService()
        kb = await _resolve_kb(knowledge, getattr(settings, "knowledge_base_id", None))
        hits = await knowledge.search(SearchRequest(query=question, kb_id=kb.id, top_k=5))
        if not hits:
            return KnowledgeRunContext(
                message=question,
                empty_reply=_empty_reply(kb.name),
            )
        return KnowledgeRunContext(
            message=_build_augmented_question(question, kb, hits),
            display_message=question,
        )
    except AgentError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AgentError("WS_KNOWLEDGE_PREPARE_ERROR", str(exc)) from exc


async def _resolve_kb(
    service: KnowledgeService,
    kb_id: str | None,
) -> KnowledgeBase:
    try:
        if kb_id:
            kb = await service.get_kb(kb_id)
            if kb is not None:
                return kb
        return await service.get_or_create_default_kb()
    except Exception as exc:  # noqa: BLE001
        raise AgentError("WS_KNOWLEDGE_KB_RESOLVE_ERROR", str(exc)) from exc


def _build_augmented_question(
    question: str,
    kb: KnowledgeBase,
    hits: list[SearchHit],
) -> str:
    sources = _unique_sources(hits)
    context = "\n\n".join(
        f"[{index}] 来源：{hit.document_name}\n{hit.content}"
        for index, hit in enumerate(hits, start=1)
    )
    source_line = "、".join(sources) if sources else "无"
    return (
        "请基于以下知识库检索内容回答用户问题，并标注主要来源文档。"
        "如果资料不足，请明确说明没有找到足够依据。\n\n"
        f"当前知识库：{kb.name}\n"
        f"主要来源：{source_line}\n\n"
        f"知识库检索内容：\n{context}\n\n"
        f"用户问题：{question}\n\n"
        "回答末尾追加三行：\n"
        f"当前知识库：{kb.name}\n"
        f"来源：{source_line}\n"
        "操作：可在首页切换知识库模式"
    )


def _empty_reply(kb_name: str) -> str:
    return (
        f"当前知识库「{kb_name}」未找到相关内容。\n\n"
        f"当前知识库：{kb_name}\n"
        "操作：可在首页切换知识库模式"
    )


def _unique_sources(hits: list[SearchHit], limit: int = 3) -> list[str]:
    sources: list[str] = []
    seen: set[str] = set()
    for hit in hits:
        name = hit.document_name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        sources.append(name)
        if len(sources) >= limit:
            break
    return sources


__all__ = ["KnowledgeRunContext", "prepare_knowledge_run"]
