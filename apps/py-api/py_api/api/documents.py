"""Document API — upload, status, extraction.

MVP endpoints:
  POST /documents/upload   — accept a file, parse, chunk, store
  GET  /documents/{id}     — retrieve document metadata + chunks
  POST /documents/{id}/summarise — run AI summarisation, return structured result
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, UploadFile

from data_model import Document, DocumentSource, DocumentStatus, ExtractionResult
from di_core import chunk_text, parse_document
from storage import LocalStorage

from py_api.core.config import get_settings

logger = structlog.get_logger()
router = APIRouter()

_documents: dict[str, Document] = {}
_extractions: dict[str, ExtractionResult] = {}


def _get_storage() -> LocalStorage:
    settings = get_settings()
    return LocalStorage(base_dir=settings.storage_local_path)


@router.post("/upload")
async def upload_document(file: UploadFile) -> Document:
    """Accept a file upload, parse it, chunk it, and return the document record."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    storage = _get_storage()
    content = await file.read()
    stored_path = storage.save_bytes(file.filename, content)

    doc = Document(
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        status=DocumentStatus.PENDING,
        source=DocumentSource(
            storage_backend="local",
            path=stored_path,
            original_filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            size_bytes=len(content),
        ),
    )

    logger.info("document.upload", doc_id=doc.id, filename=file.filename, size=len(content))

    doc = parse_document(doc, stored_path)
    if doc.status == DocumentStatus.FAILED:
        _documents[doc.id] = doc
        raise HTTPException(status_code=422, detail=doc.error or "Parsing failed")

    doc = chunk_text(doc)
    logger.info(
        "document.chunked",
        doc_id=doc.id,
        pages=len(doc.pages),
        chunks=len(doc.chunks),
    )

    _documents[doc.id] = doc
    return doc


@router.get("/{document_id}")
async def get_document(document_id: str) -> Document:
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/{document_id}/summarise")
async def summarise(document_id: str) -> ExtractionResult:
    """Run AI summarisation on a previously uploaded document."""
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.chunks:
        raise HTTPException(status_code=422, detail="Document has no chunks")

    from ai_core import summarise_document

    result = summarise_document(doc)
    _extractions[result.id] = result

    logger.info(
        "document.summarised",
        doc_id=document_id,
        model=result.model_used,
        time_ms=result.processing_time_ms,
    )
    return result


@router.get("/{document_id}/extractions/{extraction_id}")
async def get_extraction(document_id: str, extraction_id: str) -> ExtractionResult:
    result = _extractions.get(extraction_id)
    if result is None or result.document_id != document_id:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return result
