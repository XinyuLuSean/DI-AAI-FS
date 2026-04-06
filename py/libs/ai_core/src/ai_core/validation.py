"""LLM output validation — strict schema enforcement with failure classification.

The LLM returns raw JSON.  This module validates it against the expected
schema, classifies failures, and attempts controlled recovery when possible.

Failure taxonomy:
  VALID             — output conforms fully
  PARTIAL_RECOVERY  — some fields were missing/malformed but recovered with defaults
  MISSING_REQUIRED  — critical fields are absent or empty, output is unreliable
  WRONG_STRUCTURE   — JSON parsed but top-level shape is wrong (array, string, etc.)
  INVALID_JSON      — LLM returned non-JSON content (caught earlier by adapter)

The validate_summarisation_output function returns a ValidationResult that
carries the cleaned output, a list of issues found, and the overall status.
The summariser uses this to decide whether to proceed, warn, or fail.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


# ── Failure taxonomy ─────────────────────────────────────────────────────


class ValidationStatus(StrEnum):
    VALID = "valid"
    PARTIAL_RECOVERY = "partial_recovery"
    MISSING_REQUIRED = "missing_required"
    WRONG_STRUCTURE = "wrong_structure"


class ValidationIssue(BaseModel):
    """A single problem found during validation."""
    field: str
    issue: str
    severity: str = "warning"  # "warning" or "error"
    recovered: bool = False
    recovery_note: str = ""


class ValidationResult(BaseModel):
    """Outcome of validating one LLM output."""
    status: ValidationStatus
    issues: list[ValidationIssue] = Field(default_factory=list)
    output: LLMSummarisationOutput | None = None

    @property
    def ok(self) -> bool:
        return self.status in (ValidationStatus.VALID, ValidationStatus.PARTIAL_RECOVERY)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


# ── Expected LLM output schema (Pydantic model) ─────────────────────────


class LLMKeyPoint(BaseModel):
    """A single key point as the LLM should return it."""
    point: str = ""
    chunk_ids: list[str] = Field(default_factory=list)

    @field_validator("point", mode="before")
    @classmethod
    def coerce_point(cls, v: object) -> str:
        if isinstance(v, str):
            return v
        return str(v) if v is not None else ""

    @field_validator("chunk_ids", mode="before")
    @classmethod
    def coerce_chunk_ids(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v]
        return []


class LLMStructuredField(BaseModel):
    """A single structured field as the LLM should return it."""
    field_name: str = ""
    field_value: str = ""
    confidence: float = 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v: object) -> float:
        try:
            return float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0


class LLMSummarisationOutput(BaseModel):
    """The full JSON structure we expect from the summarisation LLM call.

    This is the strict contract.  Fields here mirror what the system prompt
    requests.  Validation happens against this model, not via ad hoc .get().
    """
    summary_text: str = ""
    key_points: list[LLMKeyPoint] = Field(default_factory=list)
    structured_fields: list[LLMStructuredField] = Field(default_factory=list)
    chunk_ids_used: list[str] = Field(default_factory=list)

    @field_validator("key_points", mode="before")
    @classmethod
    def coerce_key_points(cls, v: object) -> list[dict]:
        if not isinstance(v, list):
            return []
        result = []
        for item in v:
            if isinstance(item, dict):
                result.append(item)
            elif isinstance(item, str):
                result.append({"point": item, "chunk_ids": []})
            else:
                result.append({"point": str(item), "chunk_ids": []})
        return result

    @field_validator("structured_fields", mode="before")
    @classmethod
    def coerce_structured_fields(cls, v: object) -> list[dict]:
        if not isinstance(v, list):
            return []
        return [item for item in v if isinstance(item, dict)]

    @field_validator("chunk_ids_used", mode="before")
    @classmethod
    def coerce_chunk_ids_used(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v]
        return []


# ── Validation logic ─────────────────────────────────────────────────────


def validate_summarisation_output(raw: dict) -> ValidationResult:
    """Validate raw LLM JSON against the summarisation schema.

    Attempts controlled recovery for minor issues.  Returns a
    ValidationResult with the cleaned output (if recoverable) and a
    list of every issue found.
    """
    issues: list[ValidationIssue] = []

    if not isinstance(raw, dict):
        return ValidationResult(
            status=ValidationStatus.WRONG_STRUCTURE,
            issues=[ValidationIssue(
                field="<root>",
                issue=f"Expected a JSON object, got {type(raw).__name__}",
                severity="error",
            )],
        )

    try:
        output = LLMSummarisationOutput.model_validate(raw)
    except Exception as exc:
        return ValidationResult(
            status=ValidationStatus.WRONG_STRUCTURE,
            issues=[ValidationIssue(
                field="<root>",
                issue=f"Pydantic validation failed: {exc}",
                severity="error",
            )],
        )

    has_error = False

    # ── summary_text ─────────────────────────────────────────────────
    if not output.summary_text.strip():
        issues.append(ValidationIssue(
            field="summary_text",
            issue="Empty or missing — this is the primary output",
            severity="error",
        ))
        has_error = True

    # ── key_points ───────────────────────────────────────────────────
    if len(output.key_points) == 0:
        issues.append(ValidationIssue(
            field="key_points",
            issue="No key points generated",
            severity="warning",
            recovered=True,
            recovery_note="Proceeding with empty key_points list",
        ))

    empty_points = [kp for kp in output.key_points if not kp.point.strip()]
    if empty_points:
        output.key_points = [kp for kp in output.key_points if kp.point.strip()]
        issues.append(ValidationIssue(
            field="key_points",
            issue=f"{len(empty_points)} key point(s) had empty text — removed",
            severity="warning",
            recovered=True,
            recovery_note="Filtered out empty key points",
        ))

    uncited_points = [kp for kp in output.key_points if len(kp.chunk_ids) == 0]
    if uncited_points:
        issues.append(ValidationIssue(
            field="key_points",
            issue=f"{len(uncited_points)}/{len(output.key_points)} key point(s) have no chunk_ids",
            severity="warning",
        ))

    # ── chunk_ids_used ───────────────────────────────────────────────
    if len(output.chunk_ids_used) == 0 and len(output.key_points) > 0:
        all_cited = []
        for kp in output.key_points:
            all_cited.extend(kp.chunk_ids)
        if all_cited:
            output.chunk_ids_used = list(dict.fromkeys(all_cited))
            issues.append(ValidationIssue(
                field="chunk_ids_used",
                issue="Missing — reconstructed from key_points chunk_ids",
                severity="warning",
                recovered=True,
                recovery_note=f"Rebuilt from {len(output.chunk_ids_used)} unique chunk IDs in key_points",
            ))
        else:
            issues.append(ValidationIssue(
                field="chunk_ids_used",
                issue="Empty and no chunk_ids in key_points — no evidence trail",
                severity="warning",
            ))

    # ── structured_fields confidence range ───────────────────────────
    for sf in output.structured_fields:
        if sf.confidence < 0.0 or sf.confidence > 1.0:
            sf.confidence = max(0.0, min(1.0, sf.confidence))
            issues.append(ValidationIssue(
                field=f"structured_fields.{sf.field_name}.confidence",
                issue=f"Confidence out of [0, 1] range — clamped to {sf.confidence}",
                severity="warning",
                recovered=True,
                recovery_note="Clamped to valid range",
            ))

    # ── Determine overall status ─────────────────────────────────────
    if has_error:
        status = ValidationStatus.MISSING_REQUIRED
    elif len(issues) > 0:
        status = ValidationStatus.PARTIAL_RECOVERY
    else:
        status = ValidationStatus.VALID

    return ValidationResult(
        status=status,
        issues=issues,
        output=output,
    )
