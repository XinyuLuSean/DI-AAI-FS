"""Module 9D — Slice-based evaluation.

Breaks evaluation results down by document attributes so failures can be
diagnosed per category rather than buried in averages.

Slices mirror the evaluation_slices section of ground_truth.json:
  - by_document_type  (legal / medical / billing / treatment / ...)
  - by_size_category  (small / medium / large)
  - by_file_format    (txt / md / pdf_target)

For each slice, computes aggregate precision/recall/F1 across all fixtures
in that slice, plus average summary coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from di_eval.field_eval import FieldSetMetrics
from di_eval.retrieval_eval import RetrievalMetrics
from di_eval.summary_eval import SummaryDimensions


@dataclass
class SliceStats:
    """Aggregate metrics for one evaluation slice."""

    slice_name: str
    slice_value: str
    fixture_count: int = 0

    avg_precision: float = 0.0
    avg_recall: float = 0.0
    avg_f1: float = 0.0
    avg_factual_coverage: float = 0.0
    avg_grounding_score: float = 0.0
    avg_retrieval_relevance: float = 0.0
    avg_retrieval_lift: float = 0.0
    avg_extraction_time_ms: float = 0.0
    avg_summarisation_time_ms: float = 0.0

    total_true_positives: int = 0
    total_false_positives: int = 0
    total_false_negatives: int = 0

    fixtures: list[str] = field(default_factory=list)


@dataclass
class SliceBreakdown:
    """All slice breakdowns for one evaluation run."""

    by_document_type: list[SliceStats] = field(default_factory=list)
    by_size_category: list[SliceStats] = field(default_factory=list)
    by_file_format: list[SliceStats] = field(default_factory=list)
    by_extraction_density: list[SliceStats] = field(default_factory=list)
    by_section_richness: list[SliceStats] = field(default_factory=list)
    by_content_style: list[SliceStats] = field(default_factory=list)
    by_parse_quality: list[SliceStats] = field(default_factory=list)
    by_page_count_bucket: list[SliceStats] = field(default_factory=list)
    by_text_cleanliness: list[SliceStats] = field(default_factory=list)
    by_task_type: list[SliceStats] = field(default_factory=list)
    by_model_prompt: list[SliceStats] = field(default_factory=list)
    other_slices: dict[str, list[SliceStats]] = field(default_factory=dict)


def compute_slice_breakdown(
    field_metrics: dict[str, FieldSetMetrics],
    summary_dims: dict[str, SummaryDimensions],
    retrieval_metrics: dict[str, RetrievalMetrics],
    evaluation_slices: dict[str, dict[str, list[str]]],
) -> SliceBreakdown:
    """Group fixture-level metrics into slice aggregates.

    Parameters
    ----------
    field_metrics : fixture_name → FieldSetMetrics
    summary_dims : fixture_name → SummaryDimensions
    evaluation_slices : from ground_truth.json["evaluation_slices"]
    """
    breakdown = SliceBreakdown()

    for slice_name, category_map in evaluation_slices.items():
        attr_name = _slice_attr(slice_name)
        if attr_name is None:
            continue

        stats_list: list[SliceStats] = []
        for category_value, fixture_list in category_map.items():
            stats = _aggregate_slice(
                slice_name, category_value, fixture_list,
                field_metrics, summary_dims, retrieval_metrics,
            )
            if stats.fixture_count > 0:
                stats_list.append(stats)

        if hasattr(breakdown, attr_name):
            setattr(breakdown, attr_name, stats_list)
        else:
            breakdown.other_slices[slice_name] = stats_list

    return breakdown


def _slice_attr(name: str) -> str | None:
    mapping = {
        "by_document_type": "by_document_type",
        "by_size_category": "by_size_category",
        "by_file_format": "by_file_format",
        "by_extraction_density": "by_extraction_density",
        "by_section_richness": "by_section_richness",
        "by_content_style": "by_content_style",
        "by_parse_quality": "by_parse_quality",
        "by_page_count_bucket": "by_page_count_bucket",
        "by_text_cleanliness": "by_text_cleanliness",
        "by_task_type": "by_task_type",
        "by_model_prompt": "by_model_prompt",
    }
    return mapping.get(name)


def _aggregate_slice(
    slice_name: str,
    category_value: str,
    fixture_list: list[str],
    field_metrics: dict[str, FieldSetMetrics],
    summary_dims: dict[str, SummaryDimensions],
    retrieval_metrics: dict[str, RetrievalMetrics],
) -> SliceStats:
    stats = SliceStats(slice_name=slice_name, slice_value=category_value)

    precisions: list[float] = []
    recalls: list[float] = []
    f1s: list[float] = []
    coverages: list[float] = []
    groundings: list[float] = []
    retrievals: list[float] = []
    retrieval_lifts: list[float] = []
    ext_times: list[float] = []
    sum_times: list[float] = []

    for fixture in fixture_list:
        fm = field_metrics.get(fixture)
        sd = summary_dims.get(fixture)
        rm = retrieval_metrics.get(fixture)

        if fm is None and sd is None and rm is None:
            continue

        stats.fixture_count += 1
        stats.fixtures.append(fixture)

        if fm:
            precisions.append(fm.precision)
            recalls.append(fm.recall)
            f1s.append(fm.f1)
            ext_times.append(fm.extraction_time_ms)
            stats.total_true_positives += fm.true_positives
            stats.total_false_positives += fm.false_positives
            stats.total_false_negatives += fm.false_negatives

        if sd:
            coverages.append(sd.factual_coverage)
            groundings.append(sd.grounding_score)
            sum_times.append(sd.summarisation_time_ms)
        if rm:
            retrievals.append(rm.query_ranked_avg_relevance)
            retrieval_lifts.append(rm.relevance_lift)

    if precisions:
        stats.avg_precision = _mean(precisions)
        stats.avg_recall = _mean(recalls)
        stats.avg_f1 = _mean(f1s)
    if coverages:
        stats.avg_factual_coverage = _mean(coverages)
    if groundings:
        stats.avg_grounding_score = _mean(groundings)
    if ext_times:
        stats.avg_extraction_time_ms = _mean(ext_times)
    if sum_times:
        stats.avg_summarisation_time_ms = _mean(sum_times)
    if retrievals:
        stats.avg_retrieval_relevance = _mean(retrievals)
    if retrieval_lifts:
        stats.avg_retrieval_lift = _mean(retrieval_lifts)

    return stats


def _mean(vals: list[float]) -> float:
    return round(sum(vals) / len(vals), 4) if vals else 0.0
