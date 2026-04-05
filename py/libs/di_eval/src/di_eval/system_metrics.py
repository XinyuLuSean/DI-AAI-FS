"""Module 9D — DI system metrics.

Collects operational quality metrics across a full evaluation run:
  - parse / chunk / extraction / summarisation latency
  - extraction failure rate
  - evidence attachment rate
  - routing accuracy

These metrics answer "is the system healthy?" rather than "are the outputs
correct?" — they complement the field and summary evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FixtureTimings:
    """Raw timing data for one fixture."""

    fixture: str
    upload_time_ms: int = 0
    extraction_time_ms: int = 0
    summarisation_time_ms: int = 0


@dataclass
class PipelineMetrics:
    """Aggregate system-level metrics from an evaluation run."""

    total_fixtures: int = 0
    fixtures_processed: int = 0
    fixtures_failed: int = 0

    # Latency
    avg_upload_ms: float = 0.0
    avg_extraction_ms: float = 0.0
    avg_summarisation_ms: float = 0.0
    max_upload_ms: int = 0
    max_extraction_ms: int = 0
    max_summarisation_ms: int = 0

    # Routing
    routing_correct: int = 0
    routing_incorrect: int = 0
    routing_accuracy: float = 0.0

    # Extraction
    extraction_failure_count: int = 0
    extraction_failure_rate: float = 0.0
    total_fields_extracted: int = 0
    total_fields_with_evidence: int = 0
    evidence_attachment_rate: float = 0.0

    fixture_timings: list[FixtureTimings] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def collect_pipeline_metrics(
    timings: list[FixtureTimings],
    routing_results: dict[str, dict],
    expected_routings: dict[str, dict],
    extraction_results: dict[str, dict],
    failures: list[str],
) -> PipelineMetrics:
    """Build aggregate system metrics from raw evaluation data.

    Parameters
    ----------
    timings : per-fixture timing data
    routing_results : fixture_name → {predicted_type, confidence, ...}
    expected_routings : fixture_name → {type, confidence_min, accept_types?, ...}
    extraction_results : fixture_name → serialised ExtractionResult
    failures : list of fixture names that failed to process
    """
    m = PipelineMetrics(
        total_fixtures=len(timings) + len(failures),
        fixtures_processed=len(timings),
        fixtures_failed=len(failures),
        failures=failures,
        fixture_timings=timings,
    )

    # ── Latency ──────────────────────────────────────────────────────
    if timings:
        upload_ms = [t.upload_time_ms for t in timings]
        ext_ms = [t.extraction_time_ms for t in timings]
        sum_ms = [t.summarisation_time_ms for t in timings if t.summarisation_time_ms > 0]

        m.avg_upload_ms = _mean(upload_ms)
        m.max_upload_ms = max(upload_ms) if upload_ms else 0
        m.avg_extraction_ms = _mean(ext_ms)
        m.max_extraction_ms = max(ext_ms) if ext_ms else 0
        if sum_ms:
            m.avg_summarisation_ms = _mean(sum_ms)
            m.max_summarisation_ms = max(sum_ms)

    # ── Routing accuracy ─────────────────────────────────────────────
    for fixture, actual in routing_results.items():
        expected = expected_routings.get(fixture)
        if expected is None:
            continue
        actual_type = actual.get("predicted_type", "unknown")
        expected_type = expected.get("type", "unknown")
        accept_types = expected.get("accept_types", [expected_type])

        if actual_type == expected_type or actual_type in accept_types:
            m.routing_correct += 1
        else:
            m.routing_incorrect += 1

    total_routing = m.routing_correct + m.routing_incorrect
    m.routing_accuracy = m.routing_correct / total_routing if total_routing > 0 else 0.0

    # ── Extraction quality ───────────────────────────────────────────
    m.extraction_failure_count = len(failures)
    m.extraction_failure_rate = (
        len(failures) / m.total_fixtures if m.total_fixtures > 0 else 0.0
    )

    for ext in extraction_results.values():
        fields = ext.get("structured_fields", [])
        m.total_fields_extracted += len(fields)
        m.total_fields_with_evidence += sum(
            1 for f in fields if f.get("evidence") and len(f["evidence"]) > 0
        )

    m.evidence_attachment_rate = (
        m.total_fields_with_evidence / m.total_fields_extracted
        if m.total_fields_extracted > 0 else 0.0
    )

    return m


def _mean(vals: list[int | float]) -> float:
    return round(sum(vals) / len(vals), 2) if vals else 0.0
