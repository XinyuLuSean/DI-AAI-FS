"""Extraction and AI output models.

These schemas enforce structure on all AI-generated outputs.  Every summary or
extraction carries evidence references back to source chunks so the UI can
display provenance.

StructuredField is used by both deterministic extraction (regex/heuristic)
and LLM-based extraction.  The extraction_method field distinguishes them
so evaluation and HITL can treat them appropriately.

Phase 8 additions:
  - GroundedKeyPoint: per-claim evidence binding (8A)
  - OutputType: distinguishes deterministic from AI results (8B)
  - GroundingAudit: post-LLM validation of evidence quality (8C)
  - SummarisationMeta enhanced with evidence-cited metrics (8D)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ExtractionMethod(StrEnum):
    """How a structured field was extracted — critical for evaluation."""

    REGEX = "regex"
    KEYWORD_WINDOW = "keyword_window"
    LLM = "llm"
    MANUAL = "manual"


class OutputType(StrEnum):
    """Distinguishes deterministic extraction from AI-generated results.

    This is a first-class distinction so evaluation, HITL, and the UI
    can treat them with appropriate trust levels.
    """

    DETERMINISTIC = "deterministic"
    AI_SUMMARY = "ai_summary"


class ChunkSelectionStrategy(StrEnum):
    """How chunks are selected for LLM context budget."""

    HEAD = "head"
    TAIL = "tail"
    HEAD_TAIL = "head_tail"
    SAMPLED = "sampled"
    ROUTING_AWARE = "routing_aware"


class EvidenceReference(BaseModel):
    """Links an AI output back to the source chunk that supports it.

    Core fields (chunk_id, chunk_text, relevance_score, page_numbers)
    are always populated.  Citation metadata (source_filename through
    section_label) is populated when the chunk has been enriched for
    retrieval (Phase 7), enabling the UI to display richer citations.
    """

    chunk_id: str
    chunk_text: str
    relevance_score: float = 0.0
    page_numbers: list[int] = Field(default_factory=list)

    # ── Citation metadata (Phase 7) ──────────────────────────────────
    source_filename: str = ""
    doc_type: str = ""
    section_label: str = ""
    parse_quality: str = ""
    char_start: int = 0
    char_end: int = 0


class StructuredField(BaseModel):
    """A single deterministic extracted field (date, name, amount, …)."""

    field_name: str
    field_value: str
    confidence: float = 0.0
    extraction_method: str = ""
    source_snippet: str = ""
    evidence: list[EvidenceReference] = Field(default_factory=list)


class GroundedKeyPoint(BaseModel):
    """A key point with per-claim evidence binding (Phase 8A).

    Each key_point now traces back to the specific chunks that support it,
    enabling reviewers to verify individual claims instead of trusting the
    summary as a monolith.
    """

    text: str
    chunk_ids: list[str] = Field(default_factory=list)
    grounded: bool = True


class SummaryResult(BaseModel):
    """An open-ended AI-generated summary with evidence backing."""

    summary_text: str
    key_points: list[str] = Field(default_factory=list)
    grounded_key_points: list[GroundedKeyPoint] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    grounding_coverage: float = 0.0


class GroundingAudit(BaseModel):
    """Post-LLM validation of how well the summary is grounded (Phase 8C).

    This audit runs *after* the LLM returns — it checks whether the LLM
    cited real chunks, whether all key points have evidence, and whether
    the overall grounding quality warrants reviewer attention.
    """

    chunks_provided: int = 0
    chunks_cited_by_llm: int = 0
    chunks_cited_valid: int = 0
    chunks_cited_invalid: int = 0
    key_points_total: int = 0
    key_points_grounded: int = 0
    key_points_ungrounded: int = 0
    grounding_score: float = 0.0
    needs_review: bool = False
    warnings: list[str] = Field(default_factory=list)


class SummarisationMeta(BaseModel):
    """Tracks what the LLM actually saw vs what was available.

    This is the key transparency record for large-document handling —
    when the summary only covers 5% of a 2 000-page PDF, the user and
    reviewer should know.
    """

    total_chunks_available: int = 0
    total_pages_available: int = 0
    chunks_sent_to_llm: int = 0
    chunks_cited_by_llm: int = 0
    pages_covered_by_selection: list[int] = Field(default_factory=list)
    pages_covered_by_evidence: list[int] = Field(default_factory=list)
    coverage_ratio: float = 0.0
    evidence_usage_ratio: float = 0.0
    selection_strategy: ChunkSelectionStrategy = ChunkSelectionStrategy.HEAD
    is_partial: bool = False
    warnings: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Complete output of one extraction/summarisation run.

    Field classes (conceptual separation for evaluation and HITL):

      Identity / provenance:
        id, document_id, output_type, model_used, prompt_name, prompt_version

      Deterministic fields:
        structured_fields — regex/heuristic or LLM-extracted key-value pairs
        Each carries its own confidence and extraction_method.

      Open-ended narrative:
        summary — free-text summary, key points, grounding coverage
        This is the part most prone to hallucination and needs evidence backing.

      Evidence metadata:
        summary.evidence, summary.grounded_key_points, grounding_audit,
        summarisation_meta — everything that traces output back to source chunks.

      Warning / review status:
        validation_status — how clean the LLM output was (valid, partial, failed)
        validation_warnings — specific issues found during schema validation
        grounding_audit.needs_review — grounding-level review flag
    """

    # ── Identity / provenance ────────────────────────────────────────
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    document_id: str
    output_type: OutputType = OutputType.DETERMINISTIC
    model_used: str = ""
    prompt_name: str = ""
    prompt_version: str = ""

    # ── Deterministic fields ─────────────────────────────────────────
    structured_fields: list[StructuredField] = Field(default_factory=list)

    # ── Open-ended narrative ─────────────────────────────────────────
    summary: SummaryResult | None = None

    # ── Evidence metadata ────────────────────────────────────────────
    grounding_audit: GroundingAudit | None = None
    summarisation_meta: SummarisationMeta | None = None

    # ── Warning / review status ──────────────────────────────────────
    validation_status: str = "valid"
    validation_warnings: list[str] = Field(default_factory=list)

    # ── Timing ───────────────────────────────────────────────────────
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processing_time_ms: int = 0
