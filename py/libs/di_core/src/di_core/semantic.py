"""Phase 8 helpers — explainable classification and semantic matching.

Keeps Phase 8 intentionally small and inspectable:
  - Classification: document readiness / review-needed support
  - Semantic matching: align extracted structured facts back to chunks
  - Clustering thought path: lightweight grouping of matched chunks by section
"""

from __future__ import annotations

import re
import time
from collections import defaultdict

from data_model import (
    ClassificationResult,
    ClassificationSignal,
    Document,
    ExtractionResult,
    OutputType,
    SemanticMatch,
    SemanticMatchResult,
    StructuredField,
    TopicCluster,
)

from ai_core.embedding import EmbeddingAdapter, HashEmbeddingAdapter
from di_core.vector_index import _cosine_similarity

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SNIPPET_MAX = 160


def classify_document_readiness(
    doc: Document,
    extraction: ExtractionResult | None = None,
) -> ExtractionResult:
    """Classify whether a document is ready for higher-trust AI workflows.

    This is an explainable signal-combination classifier, not a generative task.
    It is useful operationally because it surfaces whether downstream AI output
    should be trusted, reviewed, or blocked before spending more time/cost.
    """
    start = time.perf_counter_ns()

    signals: list[ClassificationSignal] = []
    rationale: list[str] = []
    blockers = 0.0
    review = 0.0
    support = 0.0

    parse_quality = doc.parse_meta.quality.value if doc.parse_meta else "unknown"
    if parse_quality == "unusable":
        blockers += 1.0
        rationale.append("Parse quality is unusable, so downstream AI output would be unreliable.")
        signals.append(ClassificationSignal(
            name="parse_quality",
            value=parse_quality,
            weight=1.0,
            supports_label=True,
        ))
    elif parse_quality == "degraded":
        review += 0.7
        rationale.append("Parse quality is degraded, so reviewer verification is recommended.")
        signals.append(ClassificationSignal(
            name="parse_quality",
            value=parse_quality,
            weight=0.7,
            supports_label=True,
        ))
    else:
        support += 0.8
        signals.append(ClassificationSignal(
            name="parse_quality",
            value=parse_quality,
            weight=0.8,
            supports_label=True,
        ))

    likely_needs_ocr = bool(doc.parse_meta.likely_needs_ocr) if doc.parse_meta else False
    if likely_needs_ocr:
        review += 0.6
        rationale.append("The parser flagged likely OCR need, which raises evidence risk.")
        signals.append(ClassificationSignal(
            name="likely_needs_ocr",
            value="true",
            weight=0.6,
            supports_label=True,
        ))

    routing_conf = doc.routing.confidence if doc.routing else 0.0
    if doc.routing and routing_conf < 0.4:
        review += 0.4
        rationale.append("Document routing confidence is low, so task selection may be brittle.")
        signals.append(ClassificationSignal(
            name="routing_confidence",
            value=f"{routing_conf:.2f}",
            weight=0.4,
            supports_label=True,
        ))
    elif doc.routing:
        support += 0.3
        signals.append(ClassificationSignal(
            name="routing_confidence",
            value=f"{routing_conf:.2f}",
            weight=0.3,
            supports_label=True,
        ))

    chunk_count = len(doc.chunks)
    if chunk_count == 0:
        blockers += 1.0
        rationale.append("No chunks are available, so retrieval and grounding cannot run.")
        signals.append(ClassificationSignal(
            name="chunk_count",
            value="0",
            weight=1.0,
            supports_label=True,
        ))
    elif chunk_count < 3:
        review += 0.2
        rationale.append("Very few chunks are available, so coverage may be narrow.")
        signals.append(ClassificationSignal(
            name="chunk_count",
            value=str(chunk_count),
            weight=0.2,
            supports_label=True,
        ))
    else:
        support += 0.2
        signals.append(ClassificationSignal(
            name="chunk_count",
            value=str(chunk_count),
            weight=0.2,
            supports_label=True,
        ))

    field_count = len(extraction.structured_fields) if extraction else 0
    if extraction and field_count == 0:
        review += 0.5
        rationale.append("Deterministic extraction produced no fields, so semantic checks have weak anchors.")
        signals.append(ClassificationSignal(
            name="structured_field_count",
            value="0",
            weight=0.5,
            supports_label=True,
        ))
    elif extraction and field_count > 0:
        support += 0.4
        signals.append(ClassificationSignal(
            name="structured_field_count",
            value=str(field_count),
            weight=0.4,
            supports_label=True,
        ))

    if blockers >= 1.0:
        label = "blocked"
        confidence = min(0.7 + blockers * 0.15, 0.99)
    elif review >= support:
        label = "review_recommended"
        confidence = min(0.55 + (review / max(review + support, 1.0)) * 0.35, 0.95)
    else:
        label = "ready"
        confidence = min(0.6 + (support / max(review + support, 1.0)) * 0.35, 0.97)

    if not rationale:
        rationale.append("Document has good parse quality and enough structured evidence to proceed.")

    classification = ClassificationResult(
        task_name="document_readiness",
        label=label,
        confidence=round(confidence, 4),
        method="rule_based_signals_v1",
        rationale=rationale,
        signals=signals,
    )

    elapsed_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    return ExtractionResult(
        document_id=doc.id,
        output_type=OutputType.AI_CLASSIFICATION,
        model_used="rule_based_signals_v1",
        prompt_name="document_readiness",
        prompt_version="1.0",
        structured_fields=[
            StructuredField(
                field_name="document_readiness",
                field_value=label,
                confidence=round(confidence, 4),
                extraction_method="manual",
                source_snippet="Explainable classification derived from parse, routing, chunk, and extraction signals.",
            ),
        ],
        classification=classification,
        processing_time_ms=elapsed_ms,
    )


def align_extracted_fields_to_chunks(
    doc: Document,
    extraction: ExtractionResult,
    embedding_adapter: EmbeddingAdapter | None = None,
    top_k: int = 1,
    threshold: float = 0.35,
) -> ExtractionResult:
    """Align extracted fields back to the most relevant chunks.

    Combines lexical overlap with embedding cosine similarity so the output is:
      - explainable enough for review
      - compatible with future real embedding providers
      - still deterministic enough to test locally
    """
    start = time.perf_counter_ns()
    adapter = embedding_adapter or HashEmbeddingAdapter(dim=64)

    chunk_vectors = {
        chunk.chunk_id: adapter.embed_text(chunk.text)
        for chunk in doc.chunks
    }

    matches: list[SemanticMatch] = []
    matched_chunk_ids: list[str] = []

    for field in extraction.structured_fields:
        query = f"{field.field_name} {field.field_value}".strip()
        query_vector = adapter.embed_text(query)

        ranked = sorted(
            (
                _score_field_against_chunk(field, chunk, query_vector, chunk_vectors[chunk.chunk_id])
                for chunk in doc.chunks
            ),
            key=lambda item: item["combined_score"],
            reverse=True,
        )

        best = ranked[:max(top_k, 1)][0] if ranked else None
        grounded = bool(best and best["combined_score"] >= threshold)

        if grounded:
            matched_chunk_ids.append(best["chunk"].chunk_id)

        matches.append(SemanticMatch(
            field_name=field.field_name,
            field_value=field.field_value,
            matched_chunk_id=best["chunk"].chunk_id if grounded and best else "",
            grounded=grounded,
            combined_score=round(best["combined_score"], 4) if best else 0.0,
            lexical_score=round(best["lexical_score"], 4) if best else 0.0,
            vector_score=round(best["vector_score"], 4) if best else 0.0,
            page_numbers=best["chunk"].page_numbers if grounded and best else [],
            section_label=best["chunk"].section_label if grounded and best else "",
            snippet=_build_snippet(best["chunk"].text, field.field_value) if grounded and best else "",
        ))

    clusters = _build_topic_clusters(doc, matched_chunk_ids)
    matched_count = sum(1 for match in matches if match.grounded)
    unmatched_count = len(matches) - matched_count

    notes = [
        "Scores combine lexical overlap with embedding cosine similarity.",
        "This task is more inspectable than generation because every match points to a concrete chunk.",
    ]
    if unmatched_count > 0:
        notes.append(
            f"{unmatched_count} field(s) did not clear the grounding threshold of {threshold:.2f}."
        )

    semantic_match = SemanticMatchResult(
        task_name="field_to_evidence_alignment",
        method="lexical_plus_embedding_v1",
        threshold=threshold,
        matched_count=matched_count,
        unmatched_count=unmatched_count,
        matches=matches,
        clusters=clusters,
        notes=notes,
    )

    elapsed_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    return ExtractionResult(
        document_id=doc.id,
        output_type=OutputType.SEMANTIC_MATCH,
        model_used=adapter.model_name,
        prompt_name="field_to_evidence_alignment",
        prompt_version="1.0",
        semantic_match=semantic_match,
        processing_time_ms=elapsed_ms,
    )


def _score_field_against_chunk(
    field: StructuredField,
    chunk,
    query_vector: list[float],
    chunk_vector: list[float],
) -> dict[str, object]:
    lexical_score = _lexical_overlap(f"{field.field_name} {field.field_value}", chunk.text)
    vector_score = max(_cosine_similarity(query_vector, chunk_vector), 0.0)
    combined = (lexical_score * 0.8) + (vector_score * 0.2)
    return {
        "chunk": chunk,
        "lexical_score": lexical_score,
        "vector_score": vector_score,
        "combined_score": combined,
    }


def _lexical_overlap(query: str, text: str) -> float:
    q_tokens = set(_TOKEN_RE.findall(query.lower()))
    t_tokens = set(_TOKEN_RE.findall(text.lower()))
    if not q_tokens or not t_tokens:
        return 0.0
    overlap = q_tokens & t_tokens
    return len(overlap) / len(q_tokens)


def _build_snippet(text: str, needle: str) -> str:
    lower_text = text.lower()
    lower_needle = needle.lower().strip()
    if lower_needle:
        idx = lower_text.find(lower_needle)
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(text), idx + len(needle) + 60)
            snippet = text[start:end].strip()
            if start > 0:
                snippet = "…" + snippet
            if end < len(text):
                snippet = snippet + "…"
            return snippet
    snippet = text[:_SNIPPET_MAX].strip()
    if len(text) > _SNIPPET_MAX:
        snippet += "…"
    return snippet


def _build_topic_clusters(doc: Document, chunk_ids: list[str]) -> list[TopicCluster]:
    by_label: dict[str, list[tuple[str, list[int]]]] = defaultdict(list)
    for chunk in doc.chunks:
        if chunk.chunk_id not in chunk_ids:
            continue
        label = chunk.section_label or f"page_{chunk.page_numbers[0]}" if chunk.page_numbers else "unlabelled"
        by_label[label].append((chunk.chunk_id, chunk.page_numbers))

    clusters: list[TopicCluster] = []
    for label, members in by_label.items():
        page_numbers = sorted({page for _, pages in members for page in pages})
        clusters.append(TopicCluster(
            cluster_label=label,
            chunk_ids=[cid for cid, _ in members],
            page_numbers=page_numbers,
            member_count=len(members),
        ))

    clusters.sort(key=lambda cluster: cluster.member_count, reverse=True)
    return clusters
