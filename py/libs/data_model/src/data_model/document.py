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


class ParseFailureReason(StrEnum):
    """Classifiable failure categories for parser triage and monitoring."""

    NONE = "none"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    FILE_NOT_FOUND = "file_not_found"
    EMPTY_EXTRACTION = "empty_extraction"
    UNREADABLE_PDF = "unreadable_pdf"
    ZERO_TEXT_PDF = "zero_text_pdf"


class ParseQuality(StrEnum):
    """Overall parse quality assessment."""

    GOOD = "good"
    DEGRADED = "degraded"
    UNUSABLE = "unusable"


class ParseMeta(BaseModel):
    """Observability metadata produced by the parser.

    Carried on the Document so downstream stages (chunker, summariser,
    evaluation) can make quality-aware decisions without re-inspecting
    raw pages.
    """

    parse_strategy: str = ""
    file_suffix: str = ""
    page_count: int = 0
    empty_page_count: int = 0
    total_chars: int = 0
    text_density: float = 0.0
    failure_reason: ParseFailureReason = ParseFailureReason.NONE

    native_text_extracted: bool = False
    likely_scanned: bool = False
    likely_needs_ocr: bool = False
    ocr_applied: bool = False
    quality: ParseQuality = ParseQuality.GOOD
    downstream_limitations: list[str] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)


class DocumentType(StrEnum):
    """High-level document category for routing downstream strategies."""

    UNKNOWN = "unknown"
    LEGAL = "legal"
    MEDICAL = "medical"
    BILLING = "billing"
    TREATMENT = "treatment"
    CORRESPONDENCE = "correspondence"


class RoutingRule(BaseModel):
    """One heuristic that contributed to a routing decision."""

    source: str
    pattern: str
    matched_type: DocumentType
    weight: float = 1.0


class RoutingResult(BaseModel):
    """Explainable routing prediction for a document.

    Every routing decision records *why* a type was chosen so that debugging,
    evaluation, and HITL review can inspect and override the prediction.
    """

    predicted_type: DocumentType = DocumentType.UNKNOWN
    confidence: float = 0.0
    matched_rules: list[RoutingRule] = Field(default_factory=list)
    is_fallback: bool = True
    warnings: list[str] = Field(default_factory=list)


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


class ChunkStrategy(StrEnum):
    """Available chunking strategies."""

    FIXED_SIZE = "fixed_size"
    PARAGRAPH = "paragraph"
    PAGE_BOUNDED = "page_bounded"


class ChunkMeta(BaseModel):
    """Observability metadata for one chunking run.

    Carried on the Document so downstream stages (summariser, evaluation,
    debug tooling) can inspect chunking behaviour without re-running.
    """

    strategy: ChunkStrategy = ChunkStrategy.FIXED_SIZE
    chunk_size: int = 0
    overlap: int = 0
    chunk_count: int = 0
    avg_chunk_chars: float = 0.0
    total_chars_chunked: int = 0
    max_chunks_limit: int | None = None
    is_truncated: bool = False
    page_coverage: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DocumentChunk(BaseModel):
    """A retrieval-ready text chunk with provenance metadata."""

    chunk_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    document_id: str
    index: int
    text: str
    strategy: str = ""
    page_numbers: list[int] = Field(default_factory=list)
    char_start: int = 0
    char_end: int = 0
    token_estimate: int = 0
    is_truncated: bool = False


class Document(BaseModel):
    """Top-level document record."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    filename: str
    content_type: str = "application/pdf"
    status: DocumentStatus = DocumentStatus.PENDING
    source: DocumentSource | None = None
    parse_meta: ParseMeta | None = None
    routing: RoutingResult | None = None
    chunk_meta: ChunkMeta | None = None
    pages: list[DocumentPage] = Field(default_factory=list)
    chunks: list[DocumentChunk] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error: str | None = None
