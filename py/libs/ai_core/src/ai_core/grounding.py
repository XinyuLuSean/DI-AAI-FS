"""Post-LLM grounding validation (Phase 8C).

After the LLM returns a summary, this module audits the grounding quality:
  - Did the LLM cite chunk IDs that were actually provided?
  - Do all key points have evidence?
  - What fraction of the provided chunks were cited?
  - Should a human reviewer be flagged?

The audit produces a GroundingAudit record that is attached to the
ExtractionResult alongside the summary.  It does NOT modify the summary —
it adds transparency metadata that the UI and evaluation can use.
"""

from __future__ import annotations

from data_model import (
    DocumentChunk,
    EvidenceReference,
    GroundedKeyPoint,
    GroundingAudit,
    SummarisationMeta,
)

REVIEW_THRESHOLD = 0.5


def audit_grounding(
    raw_key_points: list[dict],
    used_ids: list[str],
    provided_chunk_ids: set[str],
    chunk_map: dict[str, DocumentChunk],
) -> tuple[list[GroundedKeyPoint], GroundingAudit]:
    """Validate LLM output grounding and build per-point evidence records.

    Returns (grounded_key_points, audit).
    """
    valid_ids = {cid for cid in used_ids if cid in provided_chunk_ids}
    invalid_ids = {cid for cid in used_ids if cid not in provided_chunk_ids}

    grounded_points: list[GroundedKeyPoint] = []
    grounded_count = 0
    ungrounded_count = 0

    for kp in raw_key_points:
        if isinstance(kp, dict):
            text = kp.get("point", "")
            point_chunk_ids = kp.get("chunk_ids", [])
        else:
            text = str(kp)
            point_chunk_ids = []

        valid_point_ids = [cid for cid in point_chunk_ids if cid in provided_chunk_ids]
        is_grounded = len(valid_point_ids) > 0

        if is_grounded:
            grounded_count += 1
        else:
            ungrounded_count += 1

        grounded_points.append(GroundedKeyPoint(
            text=text,
            chunk_ids=valid_point_ids,
            grounded=is_grounded,
        ))

    total_points = len(grounded_points)
    grounding_score = grounded_count / total_points if total_points > 0 else 0.0

    warnings: list[str] = []
    needs_review = False

    if invalid_ids:
        warnings.append(
            f"LLM cited {len(invalid_ids)} chunk ID(s) not in provided context — "
            "possible hallucination"
        )
        needs_review = True

    if ungrounded_count > 0:
        warnings.append(
            f"{ungrounded_count}/{total_points} key point(s) have no evidence — "
            "claims may be unsupported"
        )
        if grounding_score < REVIEW_THRESHOLD:
            needs_review = True

    if total_points == 0:
        warnings.append("No key points were generated")

    audit = GroundingAudit(
        chunks_provided=len(provided_chunk_ids),
        chunks_cited_by_llm=len(used_ids),
        chunks_cited_valid=len(valid_ids),
        chunks_cited_invalid=len(invalid_ids),
        key_points_total=total_points,
        key_points_grounded=grounded_count,
        key_points_ungrounded=ungrounded_count,
        grounding_score=round(grounding_score, 4),
        needs_review=needs_review,
        warnings=warnings,
    )

    return grounded_points, audit


def enrich_summarisation_meta(
    meta: SummarisationMeta,
    used_ids: list[str],
    chunk_map: dict[str, DocumentChunk],
) -> SummarisationMeta:
    """Add evidence-cited metrics to the SummarisationMeta (Phase 8D)."""
    valid_cited = [cid for cid in used_ids if cid in chunk_map]
    cited_chunks = [chunk_map[cid] for cid in valid_cited]
    pages_by_evidence = sorted({p for c in cited_chunks for p in c.page_numbers})

    meta.chunks_cited_by_llm = len(valid_cited)
    meta.pages_covered_by_evidence = pages_by_evidence
    meta.evidence_usage_ratio = (
        len(valid_cited) / meta.chunks_sent_to_llm
        if meta.chunks_sent_to_llm > 0 else 0.0
    )
    meta.evidence_usage_ratio = round(meta.evidence_usage_ratio, 4)

    if meta.chunks_sent_to_llm > 0 and len(valid_cited) == 0:
        meta.warnings.append(
            "LLM did not cite any of the provided chunks — "
            "summary may not be grounded in the document"
        )

    return meta
