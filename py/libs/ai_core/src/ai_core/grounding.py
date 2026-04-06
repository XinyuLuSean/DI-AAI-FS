"""Post-LLM grounding validation and evidence gap analysis.

After the LLM returns a summary, this module:
  1. Audits grounding quality (did LLM cite real chunks? do claims have evidence?)
  2. Enriches per-claim evidence with page refs and snippets (Phase 3A)
  3. Applies unsupported-claim safeguards (Phase 3B)
  4. Produces a consolidated EvidenceGapAnalysis (Phase 3C)

The audit produces a GroundingAudit record that is attached to the
ExtractionResult alongside the summary.  When evidence is weak, the
system lowers grounding confidence and flags for review — it does not
silently pass through poorly grounded output.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from data_model import (
    DocumentChunk,
    EvidenceReference,
    GroundedKeyPoint,
    GroundingAudit,
    SummarisationMeta,
)

REVIEW_THRESHOLD = 0.5
EVIDENCE_SNIPPET_MAX = 200
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "of", "in", "to",
    "for", "with", "on", "at", "by", "from", "as", "into", "through",
    "and", "or", "but", "not", "no", "it", "its", "this", "that", "these",
    "those", "he", "she", "they", "we", "i", "you", "his", "her", "their",
})


# ── Evidence gap analysis (Phase 3C) ─────────────────────────────────────


class ClaimEvidence(BaseModel):
    """Evidence status for a single claim / key point."""
    claim_text: str
    claim_index: int
    grounded: bool
    chunk_ids: list[str] = Field(default_factory=list)
    page_numbers: list[int] = Field(default_factory=list)
    evidence_strength: str = "none"  # "strong", "weak", "none"


class EvidenceGapAnalysis(BaseModel):
    """Consolidated grounding completeness report (Phase 3C).

    One object that answers: what's well-supported, what's weak, what's missing?
    Designed for reviewer dashboards, evaluation, and auditability.
    """
    total_claims: int = 0
    grounded_claims: int = 0
    ungrounded_claims: int = 0
    strong_evidence_claims: int = 0
    weak_evidence_claims: int = 0
    no_evidence_claims: int = 0

    chunks_provided: int = 0
    chunks_cited: int = 0
    chunks_unused: int = 0

    pages_with_evidence: list[int] = Field(default_factory=list)
    pages_without_evidence: list[int] = Field(default_factory=list)

    claims: list[ClaimEvidence] = Field(default_factory=list)
    overall_strength: str = "none"  # "strong", "moderate", "weak", "none"
    summary: str = ""


# ── Keyword-window snippet extraction ────────────────────────────────────


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful lowercase tokens from text."""
    tokens = re.findall(r"[a-zA-Z0-9$.,/-]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def _extract_best_snippet(
    chunk_text: str,
    claim_text: str,
    max_chars: int = EVIDENCE_SNIPPET_MAX,
) -> str:
    """Find the window in chunk_text most relevant to claim_text.

    Slides a window of max_chars across the chunk and picks the position
    with the highest keyword overlap with the claim.  Falls back to the
    head of the chunk if no keywords match.
    """
    if len(chunk_text) <= max_chars:
        return chunk_text

    keywords = set(_extract_keywords(claim_text))
    if not keywords:
        return chunk_text[:max_chars] + "..."

    chunk_lower = chunk_text.lower()
    best_score = -1
    best_start = 0

    step = max(1, max_chars // 4)
    for start in range(0, len(chunk_text) - max_chars + 1, step):
        window = chunk_lower[start : start + max_chars]
        score = sum(1 for kw in keywords if kw in window)
        if score > best_score:
            best_score = score
            best_start = start

    if best_score <= 0:
        return chunk_text[:max_chars] + "..."

    snippet = chunk_text[best_start : best_start + max_chars]

    if best_start > 0:
        space = snippet.find(" ")
        if 0 < space < 30:
            snippet = "..." + snippet[space + 1 :]
        else:
            snippet = "..." + snippet

    if best_start + max_chars < len(chunk_text):
        space = snippet.rfind(" ")
        if space > len(snippet) - 30 and space > 0:
            snippet = snippet[:space] + "..."
        else:
            snippet = snippet + "..."

    return snippet


# ── Core grounding audit ─────────────────────────────────────────────────


def audit_grounding(
    raw_key_points: list[dict],
    used_ids: list[str],
    provided_chunk_ids: set[str],
    chunk_map: dict[str, DocumentChunk],
) -> tuple[list[GroundedKeyPoint], GroundingAudit]:
    """Validate LLM output grounding and build per-point evidence records.

    Phase 3A enrichment: each GroundedKeyPoint now carries page_numbers and
    evidence_snippets from its cited chunks, so the UI can display per-claim
    evidence inline without needing a separate lookup.

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

        page_numbers: list[int] = []
        evidence_snippets: list[str] = []
        for cid in valid_point_ids:
            chunk = chunk_map.get(cid)
            if chunk:
                page_numbers.extend(chunk.page_numbers)
                snippet = _extract_best_snippet(
                    chunk.text, text, max_chars=EVIDENCE_SNIPPET_MAX,
                )
                evidence_snippets.append(snippet)

        page_numbers = sorted(set(page_numbers))

        if is_grounded:
            grounded_count += 1
        else:
            ungrounded_count += 1

        grounded_points.append(GroundedKeyPoint(
            text=text,
            chunk_ids=valid_point_ids,
            grounded=is_grounded,
            page_numbers=page_numbers,
            evidence_snippets=evidence_snippets,
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


# ── Unsupported-claim safeguards (Phase 3B) ──────────────────────────────


def apply_grounding_safeguards(
    grounded_points: list[GroundedKeyPoint],
    audit: GroundingAudit,
) -> tuple[list[GroundedKeyPoint], GroundingAudit]:
    """Apply safeguards for poorly grounded output.

    Rules:
      - If ≥50% of claims are grounded → proceed normally
      - If <50% but >0 claims grounded → keep all but add strong warning
      - If 0 claims grounded → flag entire output for mandatory review
      - If hallucinated chunk IDs were found → flag for review

    This function does NOT silently remove claims — that would hide
    information.  Instead it marks severity and ensures the review system
    is triggered.
    """
    if audit.key_points_total == 0:
        return grounded_points, audit

    # Already handled by audit_grounding — reinforce here
    if audit.grounding_score == 0.0 and audit.key_points_total > 0:
        if not audit.needs_review:
            audit.needs_review = True
        if not any("zero grounded" in w.lower() for w in audit.warnings):
            audit.warnings.append(
                "Zero key points are grounded — summary may not reflect "
                "the document content. Mandatory review recommended."
            )

    if audit.chunks_cited_invalid > 0:
        audit.needs_review = True

    return grounded_points, audit


# ── Evidence gap analysis (Phase 3C) ─────────────────────────────────────


def build_evidence_gap_analysis(
    grounded_points: list[GroundedKeyPoint],
    provided_chunk_ids: set[str],
    used_ids: list[str],
    chunk_map: dict[str, DocumentChunk],
    total_pages: int = 0,
) -> EvidenceGapAnalysis:
    """Build a consolidated report of evidence coverage and gaps.

    Answers: what's well-supported, what's weak, what's completely missing?
    """
    claims: list[ClaimEvidence] = []
    strong = 0
    weak = 0
    none_count = 0

    for i, gkp in enumerate(grounded_points):
        if not gkp.grounded:
            strength = "none"
            none_count += 1
        elif len(gkp.chunk_ids) >= 2:
            strength = "strong"
            strong += 1
        else:
            strength = "weak"
            weak += 1

        claims.append(ClaimEvidence(
            claim_text=gkp.text,
            claim_index=i,
            grounded=gkp.grounded,
            chunk_ids=gkp.chunk_ids,
            page_numbers=gkp.page_numbers,
            evidence_strength=strength,
        ))

    cited_set = {cid for cid in used_ids if cid in provided_chunk_ids}
    unused_count = len(provided_chunk_ids) - len(cited_set)

    all_evidence_pages = sorted({
        p for gkp in grounded_points for p in gkp.page_numbers
    })
    all_pages = set(range(1, total_pages + 1)) if total_pages > 0 else set()
    pages_without = sorted(all_pages - set(all_evidence_pages)) if all_pages else []

    total_claims = len(claims)
    grounded_claims = sum(1 for c in claims if c.grounded)

    if total_claims == 0:
        overall = "none"
    elif strong > 0 and none_count == 0:
        overall = "strong"
    elif grounded_claims > total_claims / 2:
        overall = "moderate"
    elif grounded_claims > 0:
        overall = "weak"
    else:
        overall = "none"

    parts: list[str] = []
    parts.append(f"{grounded_claims}/{total_claims} claims grounded")
    if strong > 0:
        parts.append(f"{strong} strongly supported")
    if weak > 0:
        parts.append(f"{weak} weakly supported (single source)")
    if none_count > 0:
        parts.append(f"{none_count} unsupported")
    if unused_count > 0:
        parts.append(f"{unused_count} provided chunks were not cited")

    return EvidenceGapAnalysis(
        total_claims=total_claims,
        grounded_claims=grounded_claims,
        ungrounded_claims=none_count,
        strong_evidence_claims=strong,
        weak_evidence_claims=weak,
        no_evidence_claims=none_count,
        chunks_provided=len(provided_chunk_ids),
        chunks_cited=len(cited_set),
        chunks_unused=unused_count,
        pages_with_evidence=all_evidence_pages,
        pages_without_evidence=pages_without,
        claims=claims,
        overall_strength=overall,
        summary="; ".join(parts),
    )


def enrich_summarisation_meta(
    meta: SummarisationMeta,
    used_ids: list[str],
    chunk_map: dict[str, DocumentChunk],
) -> SummarisationMeta:
    """Add evidence-cited metrics to the SummarisationMeta."""
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
