"""Review queue logic — priority scoring, auto-accept, trigger classification (Phase 11C+11D).

This module answers four questions:
  1. What gets reviewed first?       → compute_review_priority()
  2. What triggers review?           → classify_review_triggers()
  3. What can be auto-accepted?      → should_auto_accept()
  4. How do corrections feed back?   → generate_feedback_signals()

Design principles:
  - Priority is a single float (0.0–1.0) for queue ordering
  - Triggers are explicit and inspectable — no hidden logic
  - Auto-accept has conservative thresholds — better to over-review
  - Feedback signals are suggestions, not automatic actions
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from data_model import (
    DocumentType,
    ExtractionResult,
    ParseQuality,
)
from data_model.review import (
    CorrectionRecord,
    FeedbackCategory,
    FeedbackFailureSource,
    FeedbackSignal,
    ReviewableOutput,
    ReviewStatus,
    ReviewTriggerReason,
)

# ── Thresholds ────────────────────────────────────────────────────────────
# These are intentionally conservative — over-reviewing is better than
# shipping unreviewed high-stakes outputs.

AUTO_ACCEPT_MIN_CONFIDENCE = 0.85
AUTO_ACCEPT_MIN_GROUNDING = 0.8
AUTO_ACCEPT_MIN_FIELDS = 2
LOW_CONFIDENCE_THRESHOLD = 0.6
WEAK_GROUNDING_THRESHOLD = 0.5
PARTIAL_COVERAGE_THRESHOLD = 0.5
HIGH_AMOUNT_THRESHOLD = 1_000_000.0
VERY_OLD_YEAR = 1900
FUTURE_DATE_TOLERANCE_DAYS = 365 * 2

_CRITICAL_DOCUMENT_TYPES = {
    DocumentType.LEGAL,
    DocumentType.MEDICAL,
}
_AMOUNT_RE = re.compile(r"-?\$?\s*([\d,]+(?:\.\d+)?)")
_ID_CLEAN_RE = re.compile(r"[^A-Za-z0-9]")
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
)


def _append_trigger_once(
    triggers: list[ReviewTriggerReason],
    trigger: ReviewTriggerReason,
) -> None:
    if trigger not in triggers:
        triggers.append(trigger)


def _is_critical_document_type(document_type: DocumentType | None) -> bool:
    return document_type in _CRITICAL_DOCUMENT_TYPES


def _parse_amount(value: str) -> float | None:
    match = _AMOUNT_RE.search(value)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_date_value(value: str) -> date | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(cleaned).date()
    except ValueError:
        return None


def _find_unusual_value_hints(result: ExtractionResult) -> list[str]:
    hints: list[str] = []
    for field in result.structured_fields:
        name = field.field_name.lower()
        value = field.field_value.strip()
        if not value:
            continue

        if name in {"total_amount", "balance_due", "net_payment", "deductible"}:
            amount = _parse_amount(value)
            if amount is not None and amount <= 0:
                hints.append(f"{field.field_name} is non-positive: {field.field_value}")
            elif amount is not None and amount > HIGH_AMOUNT_THRESHOLD:
                hints.append(f"{field.field_name} is unusually large: {field.field_value}")

        if "date" in name:
            parsed = _parse_date_value(value)
            if parsed is None:
                continue
            if parsed.year < VERY_OLD_YEAR:
                hints.append(f"{field.field_name} is implausibly old: {field.field_value}")
            elif parsed > date.today() + timedelta(days=FUTURE_DATE_TOLERANCE_DAYS):
                hints.append(f"{field.field_name} is far in the future: {field.field_value}")

        if name in {"patient_name", "provider_name"} and any(ch.isdigit() for ch in value):
            hints.append(f"{field.field_name} contains digits: {field.field_value}")

        if name.endswith("_number"):
            cleaned = _ID_CLEAN_RE.sub("", value)
            if 0 < len(cleaned) < 4:
                hints.append(f"{field.field_name} is unusually short: {field.field_value}")

    return hints


def _build_review_hints(
    result: ExtractionResult,
    document_type: DocumentType | None,
) -> list[str]:
    hints: list[str] = []
    if _is_critical_document_type(document_type):
        hints.append(f"High-stakes document type: {document_type.value}")
    hints.extend(_find_unusual_value_hints(result))

    uncertainty = result.uncertainty_assessment
    if uncertainty and uncertainty.safe_failure_reason:
        hints.append(uncertainty.safe_failure_reason)

    return hints[:6]


def classify_review_triggers(
    result: ExtractionResult,
    parse_quality: ParseQuality | None = None,
    routing_confidence: float | None = None,
    document_type: DocumentType | None = None,
) -> list[ReviewTriggerReason]:
    """Determine why an extraction result should be reviewed.

    Returns an empty list if no triggers fire — meaning the output
    is a candidate for auto-accept.
    """
    triggers: list[ReviewTriggerReason] = []

    if result.structured_fields:
        min_conf = min(f.confidence for f in result.structured_fields)
        if min_conf < LOW_CONFIDENCE_THRESHOLD:
            _append_trigger_once(triggers, ReviewTriggerReason.LOW_CONFIDENCE_FIELD)
    else:
        if result.output_type == "deterministic":
            _append_trigger_once(triggers, ReviewTriggerReason.NO_FIELDS_EXTRACTED)

    audit = result.grounding_audit
    if audit:
        if audit.grounding_score < WEAK_GROUNDING_THRESHOLD:
            _append_trigger_once(triggers, ReviewTriggerReason.WEAK_GROUNDING)
        if audit.key_points_ungrounded > 0:
            _append_trigger_once(triggers, ReviewTriggerReason.UNGROUNDED_KEY_POINTS)
        if audit.chunks_cited_invalid > 0:
            _append_trigger_once(triggers, ReviewTriggerReason.HALLUCINATED_CHUNK_IDS)

    sm = result.summarisation_meta
    if sm and sm.is_partial and sm.coverage_ratio < PARTIAL_COVERAGE_THRESHOLD:
        _append_trigger_once(triggers, ReviewTriggerReason.PARTIAL_COVERAGE)

    uncertainty = result.uncertainty_assessment
    if uncertainty:
        if uncertainty.abstained:
            _append_trigger_once(triggers, ReviewTriggerReason.SAFE_FAILURE)
        if uncertainty.contradiction_warnings:
            _append_trigger_once(triggers, ReviewTriggerReason.DETERMINISTIC_CONTRADICTION)
        if uncertainty.partial_coverage and ReviewTriggerReason.PARTIAL_COVERAGE not in triggers:
            _append_trigger_once(triggers, ReviewTriggerReason.PARTIAL_COVERAGE)

    if parse_quality == ParseQuality.DEGRADED:
        _append_trigger_once(triggers, ReviewTriggerReason.DEGRADED_PARSE_QUALITY)

    if routing_confidence is not None and routing_confidence < 0.4:
        _append_trigger_once(triggers, ReviewTriggerReason.LOW_ROUTING_CONFIDENCE)

    if _is_critical_document_type(document_type):
        _append_trigger_once(triggers, ReviewTriggerReason.CRITICAL_DOCUMENT_TYPE)

    if _find_unusual_value_hints(result):
        _append_trigger_once(triggers, ReviewTriggerReason.UNUSUAL_EXTRACTED_VALUE)

    return triggers


def compute_review_priority(
    triggers: list[ReviewTriggerReason],
    result: ExtractionResult,
) -> float:
    """Compute a 0.0–1.0 priority score for review queue ordering.

    Higher = review sooner.  The score combines trigger severity with
    output confidence signals.
    """
    if not triggers:
        return 0.0

    severity_weights: dict[ReviewTriggerReason, float] = {
        ReviewTriggerReason.HALLUCINATED_CHUNK_IDS: 0.95,
        ReviewTriggerReason.NO_FIELDS_EXTRACTED: 0.85,
        ReviewTriggerReason.WEAK_GROUNDING: 0.80,
        ReviewTriggerReason.UNGROUNDED_KEY_POINTS: 0.70,
        ReviewTriggerReason.LOW_CONFIDENCE_FIELD: 0.60,
        ReviewTriggerReason.PARTIAL_COVERAGE: 0.50,
        ReviewTriggerReason.DEGRADED_PARSE_QUALITY: 0.45,
        ReviewTriggerReason.LOW_ROUTING_CONFIDENCE: 0.35,
        ReviewTriggerReason.SAFE_FAILURE: 0.92,
        ReviewTriggerReason.DETERMINISTIC_CONTRADICTION: 0.88,
        ReviewTriggerReason.CRITICAL_DOCUMENT_TYPE: 0.65,
        ReviewTriggerReason.UNUSUAL_EXTRACTED_VALUE: 0.72,
        ReviewTriggerReason.MANUAL_REQUEST: 0.90,
    }

    max_severity = max(severity_weights.get(t, 0.5) for t in triggers)

    trigger_count_boost = min(len(triggers) * 0.05, 0.15)

    confidence_penalty = 0.0
    if result.structured_fields:
        min_conf = min(f.confidence for f in result.structured_fields)
        confidence_penalty = max(0.0, (0.5 - min_conf) * 0.2)

    priority = min(max_severity + trigger_count_boost + confidence_penalty, 1.0)
    return round(priority, 3)


def should_auto_accept(
    result: ExtractionResult,
    triggers: list[ReviewTriggerReason],
    parse_quality: ParseQuality | None = None,
) -> bool:
    """Determine if an extraction result can skip human review.

    Auto-accept only when ALL conditions are met:
      - No review triggers fired
      - All field confidences above threshold
      - Grounding score above threshold (if applicable)
      - Parse quality was good
      - At least some fields were extracted
    """
    if triggers:
        return False

    if parse_quality and parse_quality != ParseQuality.GOOD:
        return False

    fields = result.structured_fields
    if not fields:
        return False

    if len(fields) < AUTO_ACCEPT_MIN_FIELDS:
        return False

    min_conf = min(f.confidence for f in fields)
    if min_conf < AUTO_ACCEPT_MIN_CONFIDENCE:
        return False

    audit = result.grounding_audit
    if audit and audit.grounding_score < AUTO_ACCEPT_MIN_GROUNDING:
        return False

    return True


def create_reviewable_output(
    result: ExtractionResult,
    parse_quality: ParseQuality | None = None,
    routing_confidence: float | None = None,
    document_type: DocumentType | None = None,
) -> ReviewableOutput:
    """Build a ReviewableOutput from an ExtractionResult.

    This is the entry point for putting an extraction into the review
    pipeline.  It classifies triggers, computes priority, and decides
    the initial status (auto-accept or pending review).
    """
    triggers = classify_review_triggers(
        result,
        parse_quality=parse_quality,
        routing_confidence=routing_confidence,
        document_type=document_type,
    )

    priority = compute_review_priority(triggers, result)

    auto = should_auto_accept(result, triggers, parse_quality)
    status = ReviewStatus.AUTO_ACCEPTED if auto else ReviewStatus.PENDING_REVIEW

    return ReviewableOutput(
        extraction_id=result.id,
        document_id=result.document_id,
        document_type=document_type.value if document_type else "",
        output_type=result.output_type.value if hasattr(result.output_type, "value") else str(result.output_type),
        status=status,
        trigger_reasons=triggers,
        review_hints=_build_review_hints(result, document_type),
        priority_score=priority,
    )


# ── Module 11D: Feedback loop ────────────────────────────────────────────

def generate_feedback_signals(
    correction: CorrectionRecord,
) -> list[FeedbackSignal]:
    """Map corrections to actionable system improvement signals.

    Each correction type generates specific feedback that an engineer
    (or future automated system) can act on.
    """
    signals: list[FeedbackSignal] = []

    for fc in correction.field_corrections:
        signals.append(FeedbackSignal(
            correction_id=correction.id,
            document_id=correction.document_id,
            category=FeedbackCategory.EXTRACTION_HEURISTIC,
            signal_description=(
                f"Field '{fc.field_name}' was corrected from "
                f"'{fc.original_value}' to '{fc.corrected_value}'"
                f"{f' — reason: {fc.reason}' if fc.reason else ''}"
                f"{f' — source: {fc.failure_source}' if fc.failure_source else ''}"
                f"{f' — suggested chunk: {fc.suggested_chunk_id}' if fc.suggested_chunk_id else ''}"
            ),
            priority="high" if fc.original_confidence >= 0.8 else "medium",
        ))

        if fc.failure_source == FeedbackFailureSource.RETRIEVAL:
            signals.append(FeedbackSignal(
                correction_id=correction.id,
                document_id=correction.document_id,
                category=FeedbackCategory.RETRIEVAL_RANKING,
                signal_description=(
                    f"Field '{fc.field_name}' correction was attributed to retrieval."
                ),
                priority="high",
            ))

        signals.append(FeedbackSignal(
            correction_id=correction.id,
            document_id=correction.document_id,
            category=FeedbackCategory.EVALUATION_FIXTURE,
            signal_description=(
                f"Add ground truth for field '{fc.field_name}' = "
                f"'{fc.corrected_value}' to evaluation fixtures"
            ),
            priority="medium",
        ))

    if correction.summary_correction:
        signals.append(FeedbackSignal(
            correction_id=correction.id,
            document_id=correction.document_id,
            category=FeedbackCategory.SUMMARY_PROMPT,
            signal_description=(
                f"Summary was rewritten — reason: "
                f"{correction.summary_correction.reason or 'not specified'}"
                f" — source: {correction.summary_correction.failure_source}"
            ),
            priority="high",
        ))

        signals.append(FeedbackSignal(
            correction_id=correction.id,
            document_id=correction.document_id,
            category=FeedbackCategory.FINE_TUNING_DATA,
            signal_description="Corrected summary available as fine-tuning example",
            priority="low",
        ))

    for em in correction.evidence_mismatches:
        signals.append(FeedbackSignal(
            correction_id=correction.id,
            document_id=correction.document_id,
            category=FeedbackCategory.RETRIEVAL_RANKING,
            signal_description=(
                f"Evidence mismatch: chunk '{em.chunk_id}' was "
                f"'{em.mismatch_type}' for "
                f"{f'field {em.field_name}' if em.field_name else f'claim: {em.key_point_text[:60]}'}"
                f"{f' — suggested chunk: {em.suggested_chunk_id}' if em.suggested_chunk_id else ''}"
            ),
            priority="high",
        ))

        if em.failure_source == FeedbackFailureSource.PROMPT:
            signals.append(FeedbackSignal(
                correction_id=correction.id,
                document_id=correction.document_id,
                category=FeedbackCategory.SUMMARY_PROMPT,
                signal_description=(
                    f"Evidence issue was attributed to prompt behavior for "
                    f"{em.field_name or em.key_point_text[:40]}"
                ),
                priority="medium",
            ))

    for pc in correction.parse_complaints:
        signals.append(FeedbackSignal(
            correction_id=correction.id,
            document_id=correction.document_id,
            category=FeedbackCategory.PARSE_QUALITY_MODEL,
            signal_description=(
                f"Parse quality reported as '{pc.reported_quality}' "
                f"but reviewer says '{pc.actual_quality}'"
                f"{f' — pages: {pc.affected_pages}' if pc.affected_pages else ''}"
            ),
            priority="medium",
        ))

    return signals
