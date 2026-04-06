"""Phase 9C tests — retrieval-aware evaluation helpers."""

from __future__ import annotations

from di_eval.retrieval_eval import score_retrieval
from di_eval.slice_eval import compute_slice_breakdown

from di_eval.field_eval import FieldSetMetrics
from di_eval.summary_eval import SummaryDimensions


def test_score_retrieval_computes_relevance_lift() -> None:
    report = {
        "max_chunks": 3,
        "total_chunks_available": 12,
        "recommendation": "query_ranked selects significantly more relevant chunks than head.",
        "strategies": [
            {
                "strategy": "head",
                "chunk_ids": ["c1", "c2", "c3"],
                "chunks": [
                    {"relevance_score": 0.10},
                    {"relevance_score": 0.20},
                    {"relevance_score": 0.15},
                ],
            },
            {
                "strategy": "query_ranked",
                "chunk_ids": ["c5", "c6", "c7"],
                "chunks": [
                    {"relevance_score": 0.70},
                    {"relevance_score": 0.65},
                    {"relevance_score": 0.75},
                ],
            },
        ],
    }
    summary = {
        "grounding_audit": {"grounding_score": 0.8},
        "summarisation_meta": {"evidence_usage_ratio": 0.6},
    }

    rm = score_retrieval(
        fixture="sample.txt",
        query="diagnosis MRI findings",
        comparison_report=report,
        summary_result=summary,
        retrieval_latency_ms=42,
    )

    assert rm.relevance_lift > 0
    assert rm.query_ranked_avg_relevance > rm.head_avg_relevance
    assert rm.token_efficiency == 0.25
    assert rm.answer_grounding == 0.8
    assert rm.evidence_usefulness == 0.6


def test_slice_breakdown_supports_runtime_slices() -> None:
    fm = FieldSetMetrics(fixture="sample.txt", precision=0.9, recall=0.8, f1=0.85)
    sd = SummaryDimensions(fixture="sample.txt", factual_coverage=0.7, grounding_score=0.6)
    rm = score_retrieval(
        fixture="sample.txt",
        query="water damage claim",
        comparison_report={
            "max_chunks": 2,
            "total_chunks_available": 10,
            "strategies": [
                {"strategy": "head", "chunk_ids": ["c1"], "chunks": [{"relevance_score": 0.2}]},
                {"strategy": "query_ranked", "chunk_ids": ["c8"], "chunks": [{"relevance_score": 0.6}]},
            ],
        },
    )

    breakdown = compute_slice_breakdown(
        field_metrics={"sample.txt": fm},
        summary_dims={"sample.txt": sd},
        retrieval_metrics={"sample.txt": rm},
        evaluation_slices={
            "by_parse_quality": {"good": ["sample.txt"]},
            "by_task_type": {"deterministic_extraction": ["sample.txt"]},
        },
    )

    assert len(breakdown.by_parse_quality) == 1
    assert breakdown.by_parse_quality[0].avg_retrieval_relevance > 0
    assert len(breakdown.by_task_type) == 1
