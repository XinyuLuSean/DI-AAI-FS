"""Core document domain models.

These models represent the parsed/chunked document at every stage of the
pipeline.  They are intentionally kept as plain Pydantic models (not ORM
models) so the domain logic stays independent of the persistence layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    PARSED = "parsed"
    CHUNKED = "chunked"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentSource(BaseModel):
    """Where the raw file lives."""

    storage_backend: str = "local"
    path: str
    original_filename: str
    content_type: str
    size_bytes: int


class DocumentPage(BaseModel):
    """One logical page of a document."""

    page_number: int
    text: str
    char_count: int = 0


class DocumentChunk(BaseModel):
    """A retrieval-ready text chunk with provenance metadata."""

    chunk_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    document_id: str
    index: int
    text: str
    page_numbers: list[int] = Field(default_factory=list)
    char_start: int = 0
    char_end: int = 0
    token_estimate: int = 0


class Document(BaseModel):
    """Top-level document record."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    filename: str
    content_type: str = "application/pdf"
    status: DocumentStatus = DocumentStatus.PENDING
    source: DocumentSource | None = None
    pages: list[DocumentPage] = Field(default_factory=list)
    chunks: list[DocumentChunk] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error: str | None = None
