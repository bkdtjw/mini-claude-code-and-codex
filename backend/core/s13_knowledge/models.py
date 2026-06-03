from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from backend.common.utils.id_generator import generate_id

DocumentStatus = Literal["processing", "ready", "partial", "failed", "empty"]


class KnowledgeBase(BaseModel):
    id: str = Field(default_factory=generate_id)
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class KnowledgeDocument(BaseModel):
    id: str = Field(default_factory=generate_id)
    kb_id: str
    filename: str
    file_type: str
    file_size: int = 0
    chunk_count: int = 0
    status: DocumentStatus = "processing"
    error: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class KnowledgeBaseStats(BaseModel):
    id: str
    name: str
    description: str = ""
    created_at: datetime
    document_count: int = 0
    chunk_count: int = 0
    latest_document_at: datetime | None = None


class KnowledgeChunk(BaseModel):
    id: str = Field(default_factory=generate_id)
    kb_id: str
    doc_id: str
    content: str
    embedding: list[float]
    source: str = ""
    page_num: int | None = None
    chunk_index: int = 0
    metadata: dict[str, object] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    file_path: Path
    kb_id: str
    original_name: str = ""


class IngestResult(BaseModel):
    kb_id: str
    document_id: str
    status: DocumentStatus
    chunk_count: int = 0
    total_chunks: int = 0
    error: str = ""


class SearchRequest(BaseModel):
    query: str
    kb_id: str
    top_k: int = 5


class SearchHit(BaseModel):
    content: str
    score: float
    document_name: str
    page_num: int | None = None
    chunk_index: int = 0


__all__ = [
    "DocumentStatus",
    "IngestRequest",
    "IngestResult",
    "KnowledgeBase",
    "KnowledgeBaseStats",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "SearchHit",
    "SearchRequest",
]
