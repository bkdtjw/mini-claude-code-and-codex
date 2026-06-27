from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.config.settings import settings
from backend.core.s02_tools.builtin.feishu_client import FeishuClient
from backend.core.s13_knowledge.models import IngestRequest
from backend.core.s13_knowledge.service import KnowledgeService
from backend.core.task_queue import TaskPayload, TaskQueue


class KnowledgeIngestTaskResult(BaseModel):
    file_name: str
    status: str
    chunk_count: int = 0
    total_chunks: int = 0
    error: str = ""
    message: str = ""


async def execute_knowledge_ingest_task(payload: TaskPayload, queue: TaskQueue) -> None:
    try:
        result = await run_knowledge_ingest_payload(payload.input_data)
        await queue.complete(payload.task_id, {"result": result}, worker_id=payload.worker_id)
    except Exception as exc:  # noqa: BLE001
        await queue.fail(payload.task_id, str(exc), worker_id=payload.worker_id)


async def run_knowledge_ingest_payload(input_data: dict[str, Any]) -> str:
    result = await run_knowledge_ingest_file(input_data, notify=True)
    return result.message


async def execute_knowledge_ingest_batch_task(payload: TaskPayload, queue: TaskQueue) -> None:
    try:
        result = await run_knowledge_ingest_batch_payload(payload.input_data)
        await queue.complete(payload.task_id, {"result": result}, worker_id=payload.worker_id)
    except Exception as exc:  # noqa: BLE001
        await queue.fail(payload.task_id, str(exc), worker_id=payload.worker_id)


async def run_knowledge_ingest_batch_payload(input_data: dict[str, Any]) -> str:
    client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
    chat_id = str(input_data.get("chat_id", ""))
    kb_name = str(input_data.get("kb_name", ""))
    results: list[KnowledgeIngestTaskResult] = []
    for raw_file in input_data.get("files", []):
        file_data = dict(raw_file) if isinstance(raw_file, dict) else {}
        file_data.setdefault("chat_id", chat_id)
        file_data.setdefault("kb_id", str(input_data.get("kb_id", "")))
        file_data.setdefault("kb_name", kb_name)
        results.append(await run_knowledge_ingest_file(file_data, notify=False, client=client))
    message = _batch_result_message(kb_name, results)
    await _notify(client, chat_id, message)
    return message


async def run_knowledge_ingest_file(
    input_data: dict[str, Any],
    notify: bool = True,
    client: FeishuClient | None = None,
) -> KnowledgeIngestTaskResult:
    client = client or FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
    chat_id = str(input_data.get("chat_id", ""))
    kb_name = str(input_data.get("kb_name", ""))
    file_name = str(input_data.get("file_name", "uploaded_file"))
    try:
        path = await _download(client, input_data)
        if path is None:
            message = "入库失败：文件下载失败"
            if notify:
                await _notify(client, chat_id, message)
            return KnowledgeIngestTaskResult(
                file_name=file_name,
                status="failed",
                error="文件下载失败",
                message=message,
            )
        result = await KnowledgeService().ingest_document(
            IngestRequest(
                file_path=path,
                kb_id=str(input_data.get("kb_id", "")),
                original_name=str(input_data.get("file_name", "")),
            )
        )
        message = _result_message(
            kb_name,
            result.status,
            result.chunk_count,
            result.total_chunks,
            result.error,
        )
        if notify:
            await _notify(client, chat_id, message)
        return KnowledgeIngestTaskResult(
            file_name=file_name,
            status=result.status,
            chunk_count=result.chunk_count,
            total_chunks=result.total_chunks,
            error=result.error,
            message=message,
        )
    except Exception as exc:  # noqa: BLE001
        message = f"入库失败：{exc}"
        if notify:
            await _notify(client, chat_id, message)
        return KnowledgeIngestTaskResult(
            file_name=file_name,
            status="failed",
            error=str(exc),
            message=message,
        )


async def _download(client: FeishuClient, input_data: dict[str, Any]) -> Path | None:
    task_id = str(input_data.get("task_id", "knowledge"))
    file_name = _safe_name(str(input_data.get("file_name", "uploaded_file")))
    dest = Path(settings.knowledge_upload_dir) / task_id / file_name
    return await client.download_message_resource(
        str(input_data.get("message_id", "")),
        str(input_data.get("file_key", "")),
        dest,
    )


async def _notify(client: FeishuClient, chat_id: str, text: str) -> None:
    if not chat_id:
        return
    await client.send_message(chat_id, json.dumps({"text": text}, ensure_ascii=False))


def _result_message(
    kb_name: str,
    status: str,
    chunk_count: int,
    total_chunks: int,
    error: str,
) -> str:
    if status == "ready":
        return f"已入库到 {kb_name}，共 {chunk_count} 段"
    if status == "partial":
        return f"部分入库成功（{chunk_count}/{total_chunks} 段），失败：{error}"
    if status == "empty":
        return "文件中未提取到文本内容"
    if status == "failed":
        return f"文件无法解析：{error}"
    return f"入库失败：{error or status}"


def _batch_result_message(kb_name: str, results: list[KnowledgeIngestTaskResult]) -> str:
    ready = sum(1 for result in results if result.status == "ready")
    partial = sum(1 for result in results if result.status == "partial")
    failed = len(results) - ready - partial
    chunks = sum(result.chunk_count for result in results)
    if partial:
        header = (
            f"本次入库部分完成：成功 {ready} 个，"
            f"部分成功 {partial} 个，失败 {failed} 个，共 {chunks} 段"
        )
    elif failed:
        header = f"本次入库部分完成：成功 {ready} 个，失败 {failed} 个，共 {chunks} 段"
    else:
        header = f"本次入库完成：成功 {ready} 个，失败 0 个，共 {chunks} 段"
    lines = [header, f"知识库：{kb_name}"]
    problems = [result for result in results if result.status != "ready"]
    if problems:
        lines.append("失败明细：")
        for result in problems[:5]:
            lines.append(f"- {result.file_name}：{_problem_reason(result)}")
        if len(problems) > 5:
            lines.append(f"- 等 {len(problems) - 5} 个文件")
    return "\n".join(lines)


def _problem_reason(result: KnowledgeIngestTaskResult) -> str:
    if result.status == "partial":
        return f"部分成功（{result.chunk_count}/{result.total_chunks} 段），失败：{result.error}"
    if result.status == "empty":
        return "文件中未提取到文本内容"
    if result.status == "failed":
        return result.error or "文件无法解析"
    return result.message or result.error or result.status


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name).strip("._") or "uploaded_file"

__all__ = [
    "KnowledgeIngestTaskResult",
    "execute_knowledge_ingest_batch_task",
    "execute_knowledge_ingest_task",
    "run_knowledge_ingest_batch_payload",
    "run_knowledge_ingest_file",
    "run_knowledge_ingest_payload",
]
