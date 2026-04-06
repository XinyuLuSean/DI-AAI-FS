"""Human-in-the-loop review and correction models (Phase 11).

This module defines the complete HITL data contract for document intelligence:

Module 11A — Reviewable output design:
  - ReviewStatus: lifecycle of a reviewable output
  - ReviewDecision: a human reviewer's verdict on an extraction
  - ReviewableOutput: wraps an ExtractionResult with review state

Module 11B — Correction capture:
  - FieldCorrection: old → new value for a deterministic field
  - SummaryCorrection: free-text narrative fix
  - EvidenceMismatchReport: flagging wrong evidence for a field/claim
  - ParseQualityComplaint: signalling bad upstream parse quality
  - CorrectionRecord: all corrections for one extraction in one record

Design principles:
  - Corrections record *what changed* and *why*, not just the new value
  - Every correction is traceable to a reviewer and timestamp
  - Corrections preserve the original value for audit
  - The system never silently applies corrections to live outputs
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


# ── Module 11A: Review status and decisions ───────────────────────────────

class ReviewStatus(StrEnum):
    """Lifecycle of a reviewable output."""

    PENDING_REVIEW = "pending_review"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    AUTO_ACCEPTED = "auto_accepted"


class ReviewTriggerReason(StrEnum):
    """Why this output was flagged for review.

    Stored on the ReviewableOutput so the reviewer knows *why* they're
    seeing this item — not just that it needs review.
    """

    LOW_CONFIDENCE_FIELD = "low_confidence_field"
    NO_FIELDS_EXTRACTED = "no_fields_extracted"
    WEAK_GROUNDING = "weak_grounding"
    UNGROUNDED_KEY_POINTS = "ungrounded_key_points"
    HALLUCINATED_CHUNK_IDS = "hallucinated_chunk_ids"
    PARTIAL_COVERAGE = "partial_coverage"
    DEGRADED_PARSE_QUALITY = "degraded_parse_quality"
    LOW_ROUTING_CONFIDENCE = "low_routing_confidence"
    SAFE_FAILURE = "safe_failure"
    DETERMINISTIC_CONTRADICTION = "deterministic_contradiction"
    MANUAL_REQUEST = "manual_request"


class ReviewDecision(BaseModel):
    """A human reviewer's verdict on an extraction result.

    This is the core HITL action record.  It captures who reviewed,
    what they decided, and any notes explaining the decision.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    extraction_id: str
    document_id: str
    reviewer_id: str = ""
    status: ReviewStatus
    notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReviewableOutput(BaseModel):
    """Wraps an ExtractionResult with review lifecycle state.

    This is what the review queue operates on.  It carries:
      - the extraction_id to look up the actual result
      - the current review status
      - why it was flagged for review
      - any corrections that have been applied
      - the decision history
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    extraction_id: str
    document_id: str
    status: ReviewStatus = ReviewStatus.PENDING_REVIEW
    trigger_reasons: list[ReviewTriggerReason] = Field(default_factory=list)
    priority_score: float = 0.0
    decisions: list[ReviewDecision] = Field(default_factory=list)
    correction_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── Module 11B: Correction capture ───────────────────────────────────────

class FieldCorrection(BaseModel):
    """A human correction to one deterministic field.

    Preserves the original for audit and records the reason so the
    correction can feed back into heuristic/prompt improvements.
    """

    field_name: str
    original_value: str
    corrected_value: str
    original_confidence: float = 0.0
    reason: str = ""
    corrected_by: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SummaryCorrection(BaseModel):
    """A human correction to the AI-generated summary.

    The reviewer provides the corrected text and explains what was wrong.
    This is more expensive than field corrections — the design should
    minimize cases where full summary rewrites are needed.
    """

    original_summary_text: str
    corrected_summary_text: str
    reason: str = ""
    corrected_by: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceMismatchReport(BaseModel):
    """Flags when evidence doesn't actually support the claimed output.

    This is one of the most valuable HITL signals — it directly measures
    hallucination that automated grounding checks might miss.
    """

    field_name: str = ""
    key_point_text: str = ""
    chunk_id: str = ""
    mismatch_type: str = ""  # "irrelevant", "contradicts", "partial", "fabricated"
    explanation: str = ""
    reported_by: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ParseQualityComplaint(BaseModel):
    """A reviewer signals that the upstream parse quality was wrong.

    This feeds back into the parser's quality assessment calibration.
    Example: the parser said 'good quality' but the text was garbled.
    """

    reported_quality: str = ""
    actual_quality: str = ""
    affected_pages: list[int] = Field(default_factory=list)
    explanation: str = ""
    reported_by: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CorrectionRecord(BaseModel):
    """All corrections for one extraction in one record.

    This is the aggregate correction payload submitted by a reviewer.
    It may contain any combination of field corrections, summary fixes,
    evidence mismatches, and parse complaints.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    extraction_id: str
    document_id: str
    reviewer_id: str = ""
    field_corrections: list[FieldCorrection] = Field(default_factory=list)
    summary_correction: SummaryCorrection | None = None
    evidence_mismatches: list[EvidenceMismatchReport] = Field(default_factory=list)
    parse_complaints: list[ParseQualityComplaint] = Field(default_factory=list)
    notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_corrections(self) -> int:
        return (
            len(self.field_corrections)
            + (1 if self.summary_correction else 0)
            + len(self.evidence_mismatches)
            + len(self.parse_complaints)
        )


# ── Module 11D: Feedback signal ──────────────────────────────────────────

class FeedbackCategory(StrEnum):
    """What system component a correction should improve."""

    EXTRACTION_HEURISTIC = "extraction_heuristic"
    EXTRACTION_PROMPT = "extraction_prompt"
    SUMMARY_PROMPT = "summary_prompt"
    ROUTING_HEURISTIC = "routing_heuristic"
    PARSE_QUALITY_MODEL = "parse_quality_model"
    RETRIEVAL_RANKING = "retrieval_ranking"
    EVALUATION_FIXTURE = "evaluation_fixture"
    FINE_TUNING_DATA = "fine_tuning_data"


class FeedbackSignal(BaseModel):
    """Maps one correction to the system improvement it should drive.

    This is the bridge between HITL and learning loops.  Each correction
    is classified into what component should change and how.

    In the current MVP, these signals are stored but not automatically
    acted on — a human engineer reviews the accumulated signals to
    decide what to change.  Future: automated prompt tuning or
    heuristic recalibration.
    """

    correction_id: str
    document_id: str
    category: FeedbackCategory
    signal_description: str
    priority: str = "medium"  # "low", "medium", "high"
    actionable: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
