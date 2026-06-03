from __future__ import annotations

from backend.core.s13_knowledge import SearchHit


def append_knowledge_footer(answer: str, kb_name: str, hits: list[SearchHit]) -> str:
    content = answer.strip()
    footer = build_knowledge_footer(kb_name, hits)
    return f"{content}\n\n---\n{footer}" if content else footer


def build_empty_knowledge_reply(kb_name: str) -> str:
    return (
        f"当前知识库 {kb_name} 未找到相关内容\n\n"
        f"{build_knowledge_footer(kb_name, [])}"
    )


def build_knowledge_footer(kb_name: str, hits: list[SearchHit]) -> str:
    sources = unique_document_names(hits, 3)
    lines = [f"当前知识库：{kb_name}"]
    if sources:
        lines.append(f"来源：{'、'.join(sources)}")
    lines.append("操作：点击菜单「切换知识库」可更换")
    return "\n".join(lines)


def unique_document_names(hits: list[SearchHit], limit: int) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for hit in hits:
        name = hit.document_name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= limit:
            break
    return names


__all__ = [
    "append_knowledge_footer",
    "build_empty_knowledge_reply",
    "build_knowledge_footer",
    "unique_document_names",
]
