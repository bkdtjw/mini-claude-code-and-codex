from __future__ import annotations

from backend.api.routes.feishu_knowledge_tasks import (
    KnowledgeIngestTaskResult,
    _batch_result_message,
    _result_message,
)


def test_ingest_result_messages_cover_four_states() -> None:
    assert _result_message("项目文档", "ready", 3, 3, "") == "已入库到 项目文档，共 3 段"
    assert "部分入库成功（1/2 段）" in _result_message("项目文档", "partial", 1, 2, "bad")
    assert _result_message("项目文档", "failed", 0, 0, "encrypted") == "文件无法解析：encrypted"
    assert _result_message("项目文档", "empty", 0, 0, "") == "文件中未提取到文本内容"


def test_batch_result_message_summarizes_success_partial_and_failure() -> None:
    message = _batch_result_message(
        "数字信号处理",
        [
            KnowledgeIngestTaskResult(
                file_name="fft.pdf",
                status="ready",
                chunk_count=34,
                total_chunks=34,
            ),
            KnowledgeIngestTaskResult(
                file_name="fir.pdf",
                status="partial",
                chunk_count=8,
                total_chunks=10,
                error="embedding failed",
            ),
            KnowledgeIngestTaskResult(
                file_name="bad.pdf",
                status="failed",
                error="文件损坏",
            ),
        ],
    )

    assert "本次入库部分完成：成功 1 个，部分成功 1 个，失败 1 个，共 42 段" in message
    assert "知识库：数字信号处理" in message
    assert "fir.pdf：部分成功（8/10 段），失败：embedding failed" in message
    assert "bad.pdf：文件损坏" in message
