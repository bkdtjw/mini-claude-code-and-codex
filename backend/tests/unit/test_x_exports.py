from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from backend.api import x_knowledge_bridge
from backend.api.x_knowledge_bridge import compose_markdown, export_filename, ingest_x_posts
from backend.config.settings import settings
from backend.core.s02_tools.builtin.x_client import XPost
from backend.core.s13_knowledge import IngestRequest, IngestResult


@pytest.fixture(autouse=True)
def bind_test_database() -> Generator[None, None, None]:
    # 纯逻辑测试（入库经 mock），跳过 PostgresContainer。
    yield


def _post(handle: str = "alice", text: str = "Claude Code is great") -> XPost:
    return XPost(
        author_name="Alice", author_handle=handle, text=text,
        likes=10, retweets=2, replies=1, views=500,
        created_at="Thu Jul 10 08:00:00 +0000 2026", url=f"https://x.com/{handle}/1",
    )


def test_export_filename_deterministic_and_distinct() -> None:
    assert export_filename("Claude Code") == export_filename("Claude Code")  # 幂等替换的前提
    assert export_filename("Claude Code") != export_filename("GPT")
    assert export_filename("Claude Code").endswith(".md")
    # 中文关键词可读 slug 保留
    assert "舆情" in export_filename("舆情 分析") or "x-sentiment-" in export_filename("舆情 分析")


def test_compose_markdown_contains_posts_and_sources() -> None:
    content = compose_markdown("Claude Code", 7, [_post(), _post(handle="bob", text="hooks are nice")])
    assert "X/Twitter 社区舆情快照：Claude Code" in content
    assert "最近 7 天" in content and "推文数量：2" in content
    assert "@alice" in content and "Claude Code is great" in content
    assert "https://x.com/bob/1" in content  # 带来源链接可溯源
    assert "赞 10" in content


@pytest.mark.asyncio
async def test_ingest_writes_file_and_calls_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "knowledge_upload_dir", str(tmp_path))
    captured: dict[str, IngestRequest] = {}

    class _FakeService:
        async def ingest_document(self, request: IngestRequest) -> IngestResult:
            captured["request"] = request
            return IngestResult(kb_id=request.kb_id, document_id="doc-1", status="ready", chunk_count=3)

    monkeypatch.setattr(x_knowledge_bridge, "KnowledgeService", _FakeService)

    result = await ingest_x_posts("kb-x", "Claude Code", 7, [_post()])

    assert result.status == "ready" and result.document_id == "doc-1"
    request = captured["request"]
    assert request.kb_id == "kb-x"
    assert request.original_name == export_filename("Claude Code")
    written = Path(request.file_path)
    assert written.exists() and "x_exports" in str(written)
    assert "Claude Code is great" in written.read_text(encoding="utf-8")
