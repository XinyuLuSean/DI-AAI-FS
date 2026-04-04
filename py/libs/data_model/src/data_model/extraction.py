"""Extraction and AI output models.

These schemas enforce structure on all AI-generated outputs.  Every summary or
extraction carries evidence references back to source chunks so the UI can
display provenance.

StructuredField is used by both deterministic extraction (regex/heuristic)
and LLM-based extraction.  The extraction_method field distinguishes them
so evaluation and HITL can treat them appropriately.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ExtractionMethod(StrEnum):
    """How a structured field was extracted — critical for evaluation."""

    REGEX = "regex"
    KEYWORD_WINDOW = "keyword_window"
    LLM = "llm"
    MANUAL = "manual"


class EvidenceReference(BaseModel):
    """Links an AI output back to the source chunk that supports it."""

    chunk_id: str
    chunk_text: str
    relevance_score: float = 0.0
    page_numbers: list[int] = Field(default_factory=list)


class StructuredField(BaseModel):
    """A single deterministic extracted field (date, name, amount, …)."""

    field_name: str
    field_value: str
    confidence: float = 0.0
    extraction_method: str = ""
    source_snippet: str = ""
    evidence: list[EvidenceReference] = Field(default_factory=list)


class SummaryResult(BaseModel):
    """An open-ended AI-generated summary with evidence backing."""

    summary_text: str
    key_points: list[str] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Complete output of one extraction/summarisation run."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    document_id: str
    model_used: str = ""
    structured_fields: list[StructuredField] = Field(default_factory=list)
    summary: SummaryResult | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processing_time_ms: int = 0
