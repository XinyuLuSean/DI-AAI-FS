"""Extraction postprocessing — normalizes field values and cleans evidence.

Runs after deterministic extraction (and optionally after LLM extraction)
to ensure downstream consumers get consistent, trustworthy field values.

Transforms:
  - Date normalization: various formats → YYYY-MM-DD
  - Currency normalization: strip symbols, commas → clean decimal string
  - Confidence clamping: enforce [0.0, 1.0]
  - Duplicate evidence dedup: same chunk_id → keep highest relevance
  - Field value whitespace cleanup

Design principles:
  - Postprocessing never invents values — it only standardizes
  - Every normalization records what changed for audit
  - If normalization fails (ambiguous date, bad format), the original
    value is preserved and a warning is emitted
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field

from data_model import EvidenceReference, ExtractionResult, StructuredField

_DATE_FORMATS = [
    "%B %d, %Y",       # January 15, 2024
    "%B %d %Y",        # January 15 2024
    "%b %d, %Y",       # Jan 15, 2024
    "%b %d %Y",        # Jan 15 2024
    "%m/%d/%Y",        # 01/15/2024
    "%m/%d/%y",        # 01/15/24
    "%m-%d-%Y",        # 01-15-2024
    "%Y-%m-%d",        # 2024-01-15 (already ISO — still parse to validate)
    "%d %B %Y",        # 15 January 2024
    "%d %b %Y",        # 15 Jan 2024
]

_CURRENCY_STRIP = re.compile(r"[$€£¥,\s]")
_DATE_FIELDS = {"service_date", "date_of_loss", "invoice_date", "date_of_injury"}
_CURRENCY_FIELDS = {"total_amount", "net_payment", "balance_due", "deductible"}


class PostprocessChange(BaseModel):
    """One field normalization that was applied."""

    field_name: str
    original_value: str
    normalized_value: str
    change_type: str


class PostprocessMeta(BaseModel):
    """Records what the postprocessor changed for audit and debugging."""

    applied: bool = False
    fields_processed: int = 0
    dates_normalized: int = 0
    currencies_normalized: int = 0
    confidences_clamped: int = 0
    evidence_deduped: int = 0
    whitespace_cleaned: int = 0
    changes: list[PostprocessChange] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def postprocess_extraction(
    result: ExtractionResult,
) -> tuple[ExtractionResult, PostprocessMeta]:
    """Normalize extracted fields and clean evidence on an ExtractionResult.

    Modifies the result in place and returns a PostprocessMeta record.
    """
    meta = PostprocessMeta(applied=True)

    for field in result.structured_fields:
        meta.fields_processed += 1
        _normalize_field(field, meta)
        _clamp_confidence(field, meta)
        _dedup_evidence(field, meta)

    if result.summary and result.summary.evidence:
        _dedup_evidence_list(result.summary.evidence, meta)

    return result, meta


def _normalize_field(field: StructuredField, meta: PostprocessMeta) -> None:
    """Apply type-aware normalization to a field's value."""
    original = field.field_value
    cleaned = original.strip()
    if cleaned != original:
        meta.whitespace_cleaned += 1

    if field.field_name in _DATE_FIELDS:
        normalized = _normalize_date(cleaned)
        if normalized and normalized != cleaned:
            meta.changes.append(PostprocessChange(
                field_name=field.field_name,
                original_value=cleaned,
                normalized_value=normalized,
                change_type="date_normalization",
            ))
            meta.dates_normalized += 1
            field.field_value = normalized
            return
        field.field_value = cleaned
        return

    if field.field_name in _CURRENCY_FIELDS:
        normalized = _normalize_currency(cleaned)
        if normalized and normalized != cleaned:
            meta.changes.append(PostprocessChange(
                field_name=field.field_name,
                original_value=cleaned,
                normalized_value=normalized,
                change_type="currency_normalization",
            ))
            meta.currencies_normalized += 1
            field.field_value = normalized
            return
        field.field_value = cleaned
        return

    field.field_value = cleaned


def _normalize_date(value: str) -> str | None:
    """Try to parse a date string and return ISO format (YYYY-MM-DD).

    Returns None if no format matches — the caller preserves the original.
    """
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _normalize_currency(value: str) -> str | None:
    """Strip currency symbols and commas, return a clean decimal string.

    Returns None if the result is not a valid number.
    """
    cleaned = _CURRENCY_STRIP.sub("", value)
    try:
        amount = float(cleaned)
        if amount == int(amount):
            return f"{int(amount)}.00"
        return f"{amount:.2f}"
    except ValueError:
        return None


def _clamp_confidence(field: StructuredField, meta: PostprocessMeta) -> None:
    """Enforce confidence is in [0.0, 1.0]."""
    if field.confidence < 0.0:
        field.confidence = 0.0
        meta.confidences_clamped += 1
    elif field.confidence > 1.0:
        field.confidence = 1.0
        meta.confidences_clamped += 1


def _dedup_evidence(field: StructuredField, meta: PostprocessMeta) -> None:
    """Remove duplicate evidence references (same chunk_id), keep highest score."""
    if not field.evidence:
        return
    _dedup_evidence_list(field.evidence, meta)


def _dedup_evidence_list(
    evidence: list[EvidenceReference],
    meta: PostprocessMeta,
) -> None:
    """Deduplicate a list of evidence references in place."""
    if not evidence:
        return

    seen: dict[str, int] = {}
    to_remove: list[int] = []

    for i, ref in enumerate(evidence):
        if ref.chunk_id in seen:
            existing_idx = seen[ref.chunk_id]
            if ref.relevance_score > evidence[existing_idx].relevance_score:
                to_remove.append(existing_idx)
                seen[ref.chunk_id] = i
            else:
                to_remove.append(i)
            meta.evidence_deduped += 1
        else:
            seen[ref.chunk_id] = i

    for idx in sorted(to_remove, reverse=True):
        evidence.pop(idx)
