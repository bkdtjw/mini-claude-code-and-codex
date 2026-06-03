from __future__ import annotations

from pathlib import Path

from backend.core.s13_knowledge.errors import KnowledgeError

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}
MAX_FILE_BYTES = 20 * 1024 * 1024


def validate_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise KnowledgeError("KNOWLEDGE_FILE_TYPE_UNSUPPORTED", "暂不支持该文件格式")
    if not path.exists() or not path.is_file():
        raise KnowledgeError("KNOWLEDGE_FILE_NOT_FOUND", f"File not found: {path}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise KnowledgeError("KNOWLEDGE_FILE_TOO_LARGE", "单文件不能超过 20MB")
    return suffix.lstrip(".")


def parse_document(path: Path) -> str:
    file_type = validate_file(path)
    try:
        if file_type in {"md", "txt"}:
            return path.read_text(encoding="utf-8", errors="ignore")
        if file_type == "pdf":
            return _parse_pdf(path)
        if file_type == "docx":
            return _parse_docx(path)
        raise KnowledgeError("KNOWLEDGE_FILE_TYPE_UNSUPPORTED", "暂不支持该文件格式")
    except KnowledgeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise KnowledgeError("KNOWLEDGE_PARSE_FAILED", str(exc)) from exc


def _parse_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise KnowledgeError("KNOWLEDGE_PYPDF_MISSING", "pypdf is required") from exc
    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _parse_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise KnowledgeError("KNOWLEDGE_DOCX_MISSING", "python-docx is required") from exc
    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


__all__ = ["ALLOWED_EXTENSIONS", "MAX_FILE_BYTES", "parse_document", "validate_file"]
