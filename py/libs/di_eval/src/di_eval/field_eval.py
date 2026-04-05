"""Module 9A — Deterministic field evaluation.

Scores extracted fields against ground truth using four comparison strategies:
  - exact_match:      raw string equality
  - normalized_match: case-insensitive, whitespace/punctuation-collapsed
  - numeric_close:    for amounts — strips formatting and compares numerically
  - date_close:       normalises dates to ISO-8601 before comparison

Then computes precision / recall / F1 over the full field set, counting only
fields flagged must_extract=true in the ground truth.

Design:
  - Pure functions, no I/O.
  - Accepts dicts that mirror ground_truth.json shape so the runner can feed
    them directly.
  - Returns structured results, not prints, so the report layer controls output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# ── Normalisation helpers ────────────────────────────────────────────────

_STRIP_RE = re.compile(r"[^a-z0-9]")


def _normalise_text(s: str) -> str:
    return _STRIP_RE.sub("", s.lower())


def _parse_amount(s: str) -> float | None:
    cleaned = s.replace(",", "").replace("$", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


_DATE_FORMATS = [
    "%B %d, %Y",       # January 15, 2024
    "%B %d %Y",        # January 15 2024
    "%m/%d/%Y",        # 01/15/2024
    "%m/%d/%y",        # 01/15/24
    "%Y-%m-%d",        # 2024-01-15
    "%b %d, %Y",       # Jan 15, 2024
    "%d %B %Y",        # 15 January 2024
]


def _parse_date(s: str) -> datetime | None:
    cleaned = s.strip().replace(",", ", ").replace("  ", " ")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


# ── Per-field scoring ────────────────────────────────────────────────────


@dataclass
class FieldMatchResult:
    """Scoring result for one field."""

    field_name: str
    expected_value: str | None
    actual_value: str | None
    must_extract: bool

    exact_match: bool = False
    normalized_match: bool = False
    numeric_close: bool | None = None
    date_close: bool | None = None

    @property
    def best_match(self) -> bool:
        """True if any comparison strategy succeeded."""
        if self.exact_match or self.normalized_match:
            return True
        if self.numeric_close is True:
            return True
        if self.date_close is True:
            return True
        return False


def score_field(
    field_name: str,
    expected: dict,
    actual_value: str | None,
) -> FieldMatchResult:
    """Score a single field against its ground truth entry.

    expected is one entry from ground_truth.json, e.g.:
      {"value": "2024-INS-00142", "must_extract": true, "normalized": "..."}
    """
    exp_value = expected.get("value")
    must_extract = expected.get("must_extract", False)

    result = FieldMatchResult(
        field_name=field_name,
        expected_value=exp_value,
        actual_value=actual_value,
        must_extract=must_extract,
    )

    if exp_value is None:
        result.exact_match = actual_value is None
        result.normalized_match = actual_value is None
        return result

    if actual_value is None:
        return result

    result.exact_match = exp_value == actual_value
    result.normalized_match = _normalise_text(exp_value) == _normalise_text(actual_value)

    exp_amt = _parse_amount(exp_value)
    act_amt = _parse_amount(actual_value)
    if exp_amt is not None and act_amt is not None:
        result.numeric_close = abs(exp_amt - act_amt) < 0.01

    normalized_date = expected.get("normalized")
    exp_date = _parse_date(exp_value)
    act_date = _parse_date(actual_value)
    if exp_date and act_date:
        result.date_close = exp_date.date() == act_date.date()
    elif normalized_date:
        norm_date = _parse_date(normalized_date)
        act_d = _parse_date(actual_value)
        if norm_date and act_d:
            result.date_close = norm_date.date() == act_d.date()

    return result


# ── Aggregate metrics over a field set ───────────────────────────────────


@dataclass
class FieldSetMetrics:
    """Precision / recall / F1 and per-field details for one fixture."""

    fixture: str
    field_results: list[FieldMatchResult] = field(default_factory=list)

    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0

    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0

    extraction_time_ms: int = 0


def score_field_set(
    fixture: str,
    expected_fields: dict[str, dict],
    actual_fields: dict[str, str | None],
    extraction_time_ms: int = 0,
) -> FieldSetMetrics:
    """Score all fields for one fixture and compute P/R/F1.

    expected_fields: from ground_truth.json — {field_name: {value, must_extract, ...}}
    actual_fields:   from extraction result — {field_name: field_value_or_None}
    """
    metrics = FieldSetMetrics(fixture=fixture, extraction_time_ms=extraction_time_ms)

    all_field_names = set(expected_fields.keys()) | set(actual_fields.keys())

    for fname in sorted(all_field_names):
        expected = expected_fields.get(fname, {"value": None, "must_extract": False})
        actual = actual_fields.get(fname)

        result = score_field(fname, expected, actual)
        metrics.field_results.append(result)

        must_extract = expected.get("must_extract", False)
        exp_value = expected.get("value")

        if must_extract and exp_value is not None:
            if result.best_match:
                metrics.true_positives += 1
            elif actual is not None:
                # Extracted but wrong value
                metrics.false_positives += 1
                metrics.false_negatives += 1
            else:
                metrics.false_negatives += 1
        elif not must_extract and exp_value is None:
            if actual is None:
                metrics.true_negatives += 1
            else:
                metrics.false_positives += 1

    tp = metrics.true_positives
    fp = metrics.false_positives
    fn = metrics.false_negatives

    metrics.precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    metrics.recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    metrics.f1 = (
        2 * metrics.precision * metrics.recall / (metrics.precision + metrics.recall)
        if (metrics.precision + metrics.recall) > 0
        else 0.0
    )

    return metrics
