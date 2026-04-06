"""Module 9C — retrieval-aware evaluation.

Evaluates retrieval separately from answer generation so we can answer:
  - did the retriever surface relevant chunks?
  - did better retrieval translate into better grounding?
  - what did it cost in latency and context budget?
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalMetrics:
    """Retrieval-aware metrics for one fixture/query pair."""

    fixture: str
    query: str

    strategy_count: int = 0
    head_avg_relevance: float = 0.0
    query_ranked_avg_relevance: float = 0.0
    relevance_lift: float = 0.0
    selected_overlap: float = 0.0

    retrieval_latency_ms: int = 0
    token_efficiency: float = 0.0
    evidence_usefulness: float = 0.0
    answer_grounding: float = 0.0

    recommendation: str = ""
    notes: list[str] = field(default_factory=list)


def score_retrieval(
    fixture: str,
    query: str,
    comparison_report: dict,
    summary_result: dict | None = None,
    retrieval_latency_ms: int = 0,
) -> RetrievalMetrics:
    """Score retrieval quality from the retrieval-compare output.

    `comparison_report` is the API response from `/retrieval-compare`.
    `summary_result` is optional; when present, its grounding metadata lets
    us connect retrieval quality to answer quality.
    """
    metrics = RetrievalMetrics(
        fixture=fixture,
        query=query,
        retrieval_latency_ms=retrieval_latency_ms,
    )

    strategies = comparison_report.get("strategies", [])
    metrics.strategy_count = len(strategies)
    if not strategies:
        metrics.notes.append("No retrieval strategies were available for scoring.")
        return metrics

    by_name = {strategy.get("strategy", ""): strategy for strategy in strategies}
    head = by_name.get("head", {})
    ranked = by_name.get("query_ranked", {})

    metrics.head_avg_relevance = _avg_relevance(head)
    metrics.query_ranked_avg_relevance = _avg_relevance(ranked)
    metrics.relevance_lift = round(
        metrics.query_ranked_avg_relevance - metrics.head_avg_relevance,
        4,
    )

    head_ids = set(head.get("chunk_ids", []))
    ranked_ids = set(ranked.get("chunk_ids", []))
    union = head_ids | ranked_ids
    metrics.selected_overlap = round(len(head_ids & ranked_ids) / len(union), 4) if union else 0.0

    max_chunks = comparison_report.get("max_chunks", 0)
    total_chunks = comparison_report.get("total_chunks_available", 0)
    metrics.token_efficiency = round(max_chunks / total_chunks, 4) if total_chunks else 0.0

    if summary_result:
        sm = summary_result.get("summarisation_meta", {}) or {}
        audit = summary_result.get("grounding_audit", {}) or {}
        metrics.evidence_usefulness = round(sm.get("evidence_usage_ratio", 0.0), 4)
        metrics.answer_grounding = round(audit.get("grounding_score", 0.0), 4)

    recommendation = comparison_report.get("recommendation", "")
    metrics.recommendation = recommendation
    if metrics.relevance_lift > 0:
        metrics.notes.append(
            f"query_ranked improved average relevance by {metrics.relevance_lift:.3f} over head."
        )
    else:
        metrics.notes.append("query_ranked did not improve over head for this query.")
    if recommendation:
        metrics.notes.append(recommendation)

    return metrics


def _avg_relevance(strategy_result: dict) -> float:
    chunks = strategy_result.get("chunks", [])
    if not chunks:
        return 0.0
    vals = [chunk.get("relevance_score", 0.0) for chunk in chunks]
    return round(sum(vals) / len(vals), 4)
