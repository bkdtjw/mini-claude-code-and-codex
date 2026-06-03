from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.core.s13_knowledge import IngestRequest, KnowledgeService
from backend.core.task_queue import TaskPayload, TaskQueue


class LocalKnowledgeIngestResult(BaseModel):
    file_name: str
    status: str
    chunk_count: int = 0
    total_chunks: int = 0
    error: str = ""


async def execute_local_knowledge_ingest_task(payload: TaskPayload, queue: TaskQueue) -> None:
    try:
        result = await run_local_knowledge_ingest_payload(payload.input_data)
        await queue.complete(payload.task_id, result, worker_id=payload.worker_id)
    except Exception as exc:  # noqa: BLE001
        await queue.fail(payload.task_id, str(exc), worker_id=payload.worker_id)


async def run_local_knowledge_ingest_payload(input_data: dict[str, Any]) -> dict[str, Any]:
    try:
        kb_id = str(input_data.get("kb_id", ""))
        results: list[LocalKnowledgeIngestResult] = []
        service = KnowledgeService()
        for raw_file in input_data.get("files", []):
            file_data = dict(raw_file) if isinstance(raw_file, dict) else {}
            results.append(await _ingest_file(service, kb_id, file_data))
        return _summary(results)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"本地知识库入库失败：{exc}") from exc


async def _ingest_file(
    service: KnowledgeService,
    kb_id: str,
    file_data: dict[str, Any],
) -> LocalKnowledgeIngestResult:
    try:
        file_name = str(file_data.get("file_name", "uploaded_file"))
        result = await service.ingest_document(
            IngestRequest(
                file_path=Path(str(file_data.get("path", ""))),
                kb_id=kb_id,
                original_name=file_name,
            )
        )
        return LocalKnowledgeIngestResult(
            file_name=file_name,
            status=result.status,
            chunk_count=result.chunk_count,
            total_chunks=result.total_chunks,
            error=result.error,
        )
    except Exception as exc:  # noqa: BLE001
        return LocalKnowledgeIngestResult(
            file_name=str(file_data.get("file_name", "uploaded_file")),
            status="failed",
            error=str(exc),
        )


def _summary(results: list[LocalKnowledgeIngestResult]) -> dict[str, Any]:
    ok = sum(1 for item in results if item.status == "ready")
    failed = sum(1 for item in results if item.status in {"failed", "empty"})
    partial = sum(1 for item in results if item.status == "partial")
    chunks = sum(item.chunk_count for item in results)
    return {
        "ok": ok,
        "failed": failed,
        "partial": partial,
        "chunks": chunks,
        "files": [item.model_dump() for item in results],
    }


__all__ = ["execute_local_knowledge_ingest_task", "run_local_knowledge_ingest_payload"]
