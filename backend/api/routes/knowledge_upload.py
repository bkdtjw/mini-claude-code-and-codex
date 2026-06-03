from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel

from backend.config.settings import settings
from backend.core.s13_knowledge.parser import ALLOWED_EXTENSIONS, MAX_FILE_BYTES

MAX_BATCH_FILES = 50
MAX_BATCH_BYTES = 500 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024


class SavedKnowledgeUpload(BaseModel):
    file_name: str
    path: str
    file_size: int


async def save_upload_batch(
    kb_id: str,
    task_id: str,
    files: list[UploadFile],
) -> list[SavedKnowledgeUpload]:
    try:
        if not files:
            raise HTTPException(status_code=400, detail={"message": "请选择要上传的文件"})
        if len(files) > MAX_BATCH_FILES:
            raise HTTPException(status_code=413, detail={"message": "单批最多上传 50 个文件"})
        target_dir = Path(settings.knowledge_upload_dir) / "frontend" / task_id
        target_dir.mkdir(parents=True, exist_ok=True)
        saved: list[SavedKnowledgeUpload] = []
        total_size = 0
        used_names: set[str] = set()
        for index, file in enumerate(files, start=1):
            item = await _save_file(file, target_dir, index, used_names)
            total_size += item.file_size
            if total_size > MAX_BATCH_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail={"message": "单批文件总量不能超过 500MB"},
                )
            saved.append(item)
        return saved
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"message": f"上传失败：{exc}"}) from exc


async def _save_file(
    file: UploadFile,
    target_dir: Path,
    index: int,
    used_names: set[str],
) -> SavedKnowledgeUpload:
    try:
        file_name = _unique_name(_safe_name(file.filename or f"file-{index}"), used_names)
        if Path(file_name).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail={"message": "暂不支持该文件格式"})
        dest = target_dir / file_name
        size = 0
        with dest.open("wb") as handle:
            while chunk := await file.read(CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail={"message": "单文件不能超过 20MB"})
                handle.write(chunk)
        return SavedKnowledgeUpload(file_name=file_name, path=str(dest), file_size=size)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"message": f"保存文件失败：{exc}"}) from exc
    finally:
        await file.close()


def _safe_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name).strip("._")
    return safe or "uploaded_file.txt"


def _unique_name(name: str, used_names: set[str]) -> str:
    if name not in used_names:
        used_names.add(name)
        return name
    path = Path(name)
    for index in range(2, MAX_BATCH_FILES + 2):
        candidate = f"{path.stem}-{index}{path.suffix}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
    return name


__all__ = ["SavedKnowledgeUpload", "save_upload_batch"]
