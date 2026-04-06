"""Phase 11 — uncertainty, hallucination control, and safe failure."""

from __future__ import annotations

import re

from data_model import (
    GroundedKeyPoint,
    StructuredField,
    SummaryResult,
    UncertaintyAssessment,
)


_INFERENCE_MARKERS = (
    "likely", "appears", "may", "might", "suggests", "possible", "possibly", "unclear",
)
_STRIP_RE = re.compile(r"[^a-z0-9]")


def build_uncertainty_assessment(
    *,
    parse_quality: str = "",
    likely_low_quality_source: bool = False,
    coverage_level: str = "unknown",
    grounding_score: float = 0.0,
    unsupported_claim_count: int = 0,
    contradiction_warnings: list[str] | None = None,
    validation_status: str = "valid",
    grounded_points: list[GroundedKeyPoint] | None = None,
) -> UncertaintyAssessment:
    """Build a conservative uncertainty record for one AI output."""
    contradiction_warnings = contradiction_warnings or []
    grounded_points = grounded_points or []

    assessment = UncertaintyAssessment(
        contradiction_warnings=list(contradiction_warnings),
        unsupported_claim_count=unsupported_claim_count,
        inferred_claim_count=sum(
            1 for point in grounded_points
            if any(marker in point.text.lower() for marker in _INFERENCE_MARKERS)
        ),
    )

    assessment.likely_low_quality_source = likely_low_quality_source or parse_quality in {"degraded", "unusable"}
    assessment.partial_coverage = coverage_level in {"partial", "minimal"}
    assessment.scope_limited = assessment.partial_coverage
    assessment.review_recommended = (
        assessment.likely_low_quality_source
        or assessment.partial_coverage
        or unsupported_claim_count > 0
        or bool(contradiction_warnings)
        or validation_status != "valid"
    )

    if grounding_score >= 0.8 and unsupported_claim_count == 0 and not contradiction_warnings:
        assessment.evidence_sufficiency = "sufficient"
    elif grounding_score >= 0.5:
        assessment.evidence_sufficiency = "partial"
    elif grounding_score > 0.0:
        assessment.evidence_sufficiency = "weak"
    else:
        assessment.evidence_sufficiency = "none"

    confidence = 0.88
    if assessment.partial_coverage:
        confidence -= 0.18
        assessment.risk_flags.append("partial_coverage")
    if assessment.likely_low_quality_source:
        confidence -= 0.2
        assessment.risk_flags.append("low_quality_source")
    if unsupported_claim_count > 0:
        confidence -= min(0.25, unsupported_claim_count * 0.08)
        assessment.risk_flags.append("unsupported_claims")
    if contradiction_warnings:
        confidence -= 0.18
        assessment.risk_flags.append("deterministic_contradiction")
    if validation_status != "valid":
        confidence -= 0.12
        assessment.risk_flags.append("validation_recovery")
    if assessment.inferred_claim_count > 0:
        assessment.risk_flags.append("inferred_language")

    assessment.overall_confidence = round(max(0.0, min(1.0, confidence)), 4)

    if (
        assessment.evidence_sufficiency == "none"
        or (assessment.likely_low_quality_source and grounding_score == 0.0)
        or (coverage_level == "minimal" and grounding_score < 0.5)
    ):
        assessment.abstained = True
        assessment.review_recommended = True
        assessment.scope_limited = True
        if assessment.evidence_sufficiency == "none":
            assessment.safe_failure_reason = "Insufficient grounded evidence for a reliable summary."
        elif assessment.likely_low_quality_source:
            assessment.safe_failure_reason = "Source quality is too weak for a reliable summary."
        else:
            assessment.safe_failure_reason = "Coverage is too limited for a reliable summary."

    return assessment


def detect_field_contradictions(
    llm_fields: list[StructuredField],
    grounding_fields: list[StructuredField] | None,
) -> list[str]:
    """Compare overlapping deterministic and LLM fields for contradictions."""
    if not grounding_fields or not llm_fields:
        return []

    expected = {field.field_name: field.field_value for field in grounding_fields}
    warnings: list[str] = []
    for field in llm_fields:
        exp = expected.get(field.field_name)
        if exp is None:
            continue
        if _normalise(exp) != _normalise(field.field_value):
            warnings.append(
                f"LLM field '{field.field_name}' conflicts with deterministic value "
                f"'{exp}' (got '{field.field_value}')"
            )
    return warnings


def apply_safe_summary_degradation(
    summary: SummaryResult,
    uncertainty: UncertaintyAssessment,
) -> SummaryResult:
    """Narrow or abstain when evidence is too weak.

    Safe degradation policy:
      - abstained: replace summary text with an honest abstention notice
      - unsupported claims present: keep only grounded key points
      - partial coverage: prefix the summary with a scope-limitation disclosure
    """
    if uncertainty.abstained:
        return SummaryResult(
            summary_text=(
                "Abstained: available evidence is insufficient for a reliable summary. "
                "Review recommended."
            ),
            key_points=[],
            grounded_key_points=[],
            evidence=summary.evidence,
            grounding_coverage=summary.grounding_coverage,
        )

    grounded_points = [point for point in summary.grounded_key_points if point.grounded]
    key_points = [point.text for point in grounded_points] if uncertainty.unsupported_claim_count > 0 else summary.key_points

    summary_text = summary.summary_text
    if uncertainty.scope_limited and not summary_text.lower().startswith("partial summary:"):
        summary_text = f"Partial summary: {summary_text}"

    return SummaryResult(
        summary_text=summary_text,
        key_points=key_points,
        grounded_key_points=grounded_points if uncertainty.unsupported_claim_count > 0 else summary.grounded_key_points,
        evidence=summary.evidence,
        grounding_coverage=summary.grounding_coverage,
    )


def _normalise(value: str) -> str:
    return _STRIP_RE.sub("", value.lower())
