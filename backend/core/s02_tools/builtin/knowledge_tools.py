from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult
from backend.core.s13_knowledge import IngestRequest, KnowledgeService, SearchRequest

KnowledgeStateSetter = Callable[[str, str], Awaitable[None]]


def create_knowledge_tools(
    owner_id: str = "",
    set_current_kb: KnowledgeStateSetter | None = None,
) -> list[tuple[ToolDefinition, ToolExecuteFn]]:
    service = KnowledgeService()
    return [
        _ingest_tool(service),
        _search_tool(service),
        _list_tool(service),
        _switch_tool(service, owner_id, set_current_kb),
    ]


def _ingest_tool(service: KnowledgeService) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="knowledge_ingest",
        description="Parse and ingest a local file into a knowledge base.",
        category="file-ops",
        parameters=ToolParameterSchema(
            properties={
                "file_path": {"type": "string", "description": "Local file path"},
                "kb_id": {"type": "string", "description": "Knowledge base id"},
            },
            required=["file_path", "kb_id"],
        ),
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            result = await service.ingest_document(
                IngestRequest(
                    file_path=Path(str(args.get("file_path", ""))),
                    kb_id=str(args.get("kb_id", "")),
                )
            )
            return ToolResult(output=result.model_dump_json())
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def _search_tool(service: KnowledgeService) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="knowledge_search",
        description="Search relevant chunks in a knowledge base.",
        category="search",
        parameters=ToolParameterSchema(
            properties={
                "query": {"type": "string", "description": "Search query"},
                "kb_id": {"type": "string", "description": "Knowledge base id"},
                "top_k": {"type": "integer", "description": "Max result count"},
            },
            required=["query", "kb_id"],
        ),
        side_effect=False,
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            hits = await service.search(
                SearchRequest(
                    query=str(args.get("query", "")),
                    kb_id=str(args.get("kb_id", "")),
                    top_k=int(args.get("top_k", 5) or 5),
                )
            )
            return ToolResult(output="\n\n".join(_format_hit(hit) for hit in hits))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def _list_tool(service: KnowledgeService) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="knowledge_list_kbs",
        description="List all shared knowledge bases.",
        category="search",
        parameters=ToolParameterSchema(properties={}),
        side_effect=False,
    )

    async def execute(_args: dict[str, Any]) -> ToolResult:
        try:
            items = await service.list_kbs()
            return ToolResult(output="\n".join(f"{item.id}\t{item.name}" for item in items))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def _switch_tool(
    service: KnowledgeService,
    owner_id: str,
    set_current_kb: KnowledgeStateSetter | None,
) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="knowledge_switch",
        description="Validate and switch to a knowledge base by id.",
        category="search",
        parameters=ToolParameterSchema(
            properties={"kb_id": {"type": "string", "description": "Knowledge base id"}},
            required=["kb_id"],
        ),
    )

    async def execute(args: dict[str, Any]) -> ToolResult:
        try:
            kb = await service.get_kb(str(args.get("kb_id", "")))
            if kb is None:
                return ToolResult(output="Knowledge base not found", is_error=True)
            if not owner_id or set_current_kb is None:
                return ToolResult(output="当前上下文无法切换知识库", is_error=True)
            await set_current_kb(owner_id, kb.id)
            return ToolResult(output=f"已切换到知识库：{kb.name} ({kb.id})")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


def _format_hit(hit: Any) -> str:
    source = hit.document_name
    if hit.page_num is not None:
        source += f" p.{hit.page_num}"
    return f"来源：{source}#{hit.chunk_index}\n{hit.content}"


__all__ = ["create_knowledge_tools"]
