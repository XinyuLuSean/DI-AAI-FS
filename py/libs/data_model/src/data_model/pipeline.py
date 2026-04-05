"""Pipeline failure and retry semantics (Phase 10C).

Defines a clear taxonomy for every pipeline stage outcome:
  - HARD: unrecoverable, reject immediately (missing file, unsupported type)
  - SOFT: degraded but usable, continue with warnings (low text density)
  - RETRYABLE: transient failure, safe to retry (timeout, rate limit)
  - REVIEW_NEEDED: uncertain output, route to human (low confidence, grounding gap)

Each StageOutcome carries enough context for:
  - API error responses
  - Retry logic (future worker queues)
  - Monitoring dashboards
  - HITL triage
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class PipelineStage(StrEnum):
    """Named pipeline stages for tracing and failure classification."""

    UPLOAD = "upload"
    PARSE = "parse"
    PREPROCESS = "preprocess"
    ROUTE = "route"
    CHUNK = "chunk"
    SIZE_CLASSIFY = "size_classify"
    ENRICH = "enrich"
    EXTRACT = "extract"
    SUMMARISE = "summarise"
    POSTPROCESS = "postprocess"


class FailureKind(StrEnum):
    """How severe and recoverable a failure is."""

    NONE = "none"
    HARD = "hard"
    SOFT = "soft"
    RETRYABLE = "retryable"
    REVIEW_NEEDED = "review_needed"


class StageOutcome(BaseModel):
    """Outcome of one pipeline stage execution.

    Designed to be collected into a PipelineTrace (Module 10D) for
    full pipeline observability.
    """

    stage: PipelineStage
    success: bool = True
    failure_kind: FailureKind = FailureKind.NONE
    is_retryable: bool = False
    message: str = ""
    detail: str = ""
    elapsed_ms: int = 0


class PipelineTrace(BaseModel):
    """Complete trace of one document processing run.

    Attached to the Document or returned alongside the API response
    so operators, reviewers, and the UI have full visibility into
    what happened, how long it took, and where problems occurred.
    """

    stages: list[StageOutcome] = Field(default_factory=list)
    total_elapsed_ms: int = 0
    has_hard_failure: bool = False
    has_soft_warnings: bool = False
    has_retryable: bool = False
    needs_review: bool = False
    warnings: list[str] = Field(default_factory=list)

    def add(self, outcome: StageOutcome) -> None:
        """Append a stage outcome and update aggregate flags."""
        self.stages.append(outcome)
        self.total_elapsed_ms += outcome.elapsed_ms

        if outcome.failure_kind == FailureKind.HARD:
            self.has_hard_failure = True
        elif outcome.failure_kind == FailureKind.SOFT:
            self.has_soft_warnings = True
        elif outcome.failure_kind == FailureKind.RETRYABLE:
            self.has_retryable = True
        elif outcome.failure_kind == FailureKind.REVIEW_NEEDED:
            self.needs_review = True

        if outcome.message and not outcome.success:
            self.warnings.append(f"[{outcome.stage.value}] {outcome.message}")


# ── Classification helpers ────────────────────────────────────────────────
# These translate existing failure signals into the StageOutcome taxonomy.

def classify_parse_outcome(
    failure_reason: str,
    quality: str,
    elapsed_ms: int = 0,
) -> StageOutcome:
    """Map parser failure_reason + quality to a StageOutcome."""
    from data_model.document import ParseFailureReason, ParseQuality

    reason = ParseFailureReason(failure_reason) if failure_reason else ParseFailureReason.NONE
    qual = ParseQuality(quality) if quality else ParseQuality.GOOD

    if reason in (
        ParseFailureReason.FILE_NOT_FOUND,
        ParseFailureReason.UNSUPPORTED_FILE_TYPE,
        ParseFailureReason.UNREADABLE_PDF,
        ParseFailureReason.EMPTY_EXTRACTION,
    ):
        return StageOutcome(
            stage=PipelineStage.PARSE,
            success=False,
            failure_kind=FailureKind.HARD,
            message=f"Hard parse failure: {reason.value}",
            elapsed_ms=elapsed_ms,
        )

    if reason == ParseFailureReason.ZERO_TEXT_PDF:
        return StageOutcome(
            stage=PipelineStage.PARSE,
            success=False,
            failure_kind=FailureKind.SOFT,
            message="Zero-text PDF — likely scanned, OCR may recover content",
            elapsed_ms=elapsed_ms,
        )

    if qual == ParseQuality.UNUSABLE:
        return StageOutcome(
            stage=PipelineStage.PARSE,
            success=False,
            failure_kind=FailureKind.HARD,
            message="Parse quality unusable — document cannot be processed reliably",
            elapsed_ms=elapsed_ms,
        )

    if qual == ParseQuality.DEGRADED:
        return StageOutcome(
            stage=PipelineStage.PARSE,
            success=True,
            failure_kind=FailureKind.SOFT,
            message="Parse quality degraded — downstream accuracy may be affected",
            elapsed_ms=elapsed_ms,
        )

    return StageOutcome(
        stage=PipelineStage.PARSE,
        success=True,
        failure_kind=FailureKind.NONE,
        elapsed_ms=elapsed_ms,
    )


def classify_extraction_outcome(
    fields_found: int,
    total_fields_attempted: int,
    min_confidence: float,
    elapsed_ms: int = 0,
) -> StageOutcome:
    """Classify extraction quality for triage."""
    if fields_found == 0:
        return StageOutcome(
            stage=PipelineStage.EXTRACT,
            success=True,
            failure_kind=FailureKind.REVIEW_NEEDED,
            message="No fields extracted — document may need manual review",
            elapsed_ms=elapsed_ms,
        )

    if min_confidence < 0.5:
        return StageOutcome(
            stage=PipelineStage.EXTRACT,
            success=True,
            failure_kind=FailureKind.REVIEW_NEEDED,
            message=f"Low-confidence field detected (min={min_confidence:.2f})",
            elapsed_ms=elapsed_ms,
        )

    return StageOutcome(
        stage=PipelineStage.EXTRACT,
        success=True,
        failure_kind=FailureKind.NONE,
        elapsed_ms=elapsed_ms,
    )


def classify_summary_outcome(
    grounding_score: float,
    needs_review: bool,
    elapsed_ms: int = 0,
) -> StageOutcome:
    """Classify summary quality from grounding audit results."""
    if needs_review:
        return StageOutcome(
            stage=PipelineStage.SUMMARISE,
            success=True,
            failure_kind=FailureKind.REVIEW_NEEDED,
            message=f"Summary grounding below threshold (score={grounding_score:.2f})",
            elapsed_ms=elapsed_ms,
        )

    if grounding_score < 0.7:
        return StageOutcome(
            stage=PipelineStage.SUMMARISE,
            success=True,
            failure_kind=FailureKind.SOFT,
            message=f"Summary grounding acceptable but not strong ({grounding_score:.2f})",
            elapsed_ms=elapsed_ms,
        )

    return StageOutcome(
        stage=PipelineStage.SUMMARISE,
        success=True,
        failure_kind=FailureKind.NONE,
        elapsed_ms=elapsed_ms,
    )
