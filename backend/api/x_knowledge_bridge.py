from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from backend.config.settings import settings
from backend.core.s02_tools.builtin.x_client import XPost
from backend.core.s13_knowledge import IngestRequest, IngestResult, KnowledgeService


class XExportError(Exception):
    """X 舆情导出知识库失败（写文件或入库异常）。"""


def export_filename(query: str) -> str:
    """确定性文件名：同一关键词重复导出 = 幂等替换旧快照（s13 同名 upsert），库不会越导越乱。"""
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:10]
    slug = re.sub(r"[^\w一-鿿]+", "-", query).strip("-")[:40] or "query"
    return f"x-sentiment-{slug}-{digest}.md"


def compose_markdown(query: str, days: int, posts: list[XPost]) -> str:
    """把推文拼成给 Agent 检索用的 Markdown 快照（含来源链接，可溯源）。"""
    exported_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# X/Twitter 社区舆情快照：{query}",
        "",
        f"- 采集时间：{exported_at}",
        f"- 时间窗口：最近 {days} 天",
        f"- 推文数量：{len(posts)}",
        "",
    ]
    for index, post in enumerate(posts, start=1):
        lines.extend(
            [
                f"## {index}. @{post.author_handle}（{post.author_name}）",
                "",
                post.text.strip(),
                "",
                (
                    f"- 互动：赞 {post.likes:,} / 转 {post.retweets:,} "
                    f"/ 回 {post.replies:,} / 浏览 {post.views:,}"
                ),
                f"- 时间：{post.created_at}",
                f"- 链接：{post.url}",
                "",
            ]
        )
    return "\n".join(lines)


async def ingest_x_posts(kb_id: str, query: str, days: int, posts: list[XPost]) -> IngestResult:
    """写导出文件并经 s13 正门（KnowledgeService.ingest_document）入库。

    文件落在 knowledge_upload_dir/x_exports/ 下；同名文件由 s13 幂等 upsert 替换旧文档与分块。
    """
    try:
        filename = export_filename(query)
        export_dir = Path(settings.knowledge_upload_dir) / "x_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        file_path = export_dir / filename
        file_path.write_text(compose_markdown(query, days, posts), encoding="utf-8")
        return await KnowledgeService().ingest_document(
            IngestRequest(file_path=file_path, kb_id=kb_id, original_name=filename)
        )
    except Exception as exc:
        raise XExportError(f"X 舆情导出失败：{exc}") from exc


__all__ = ["XExportError", "compose_markdown", "export_filename", "ingest_x_posts"]
