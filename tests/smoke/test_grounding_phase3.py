"""Phase 3 grounding tests — evidence enrichment, safeguards, gap analysis.

Tests:
  - GroundedKeyPoint enrichment with page refs + snippets (3A)
  - Unsupported-claim safeguards (3B)
  - EvidenceGapAnalysis consolidation (3C)
  - Edge cases: zero claims, all grounded, all ungrounded, hallucinated IDs
"""

import pytest

from data_model import DocumentChunk, GroundedKeyPoint

from ai_core.grounding import (
    ClaimEvidence,
    EvidenceGapAnalysis,
    _extract_best_snippet,
    apply_grounding_safeguards,
    audit_grounding,
    build_evidence_gap_analysis,
)


# ── Test fixtures ────────────────────────────────────────────────────────

def _make_chunk(chunk_id: str, text: str, pages: list[int]) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        document_id="doc1",
        index=0,
        text=text,
        page_numbers=pages,
    )


CHUNKS = {
    "c1": _make_chunk("c1", "Patient John Smith was admitted on 2024-08-15 for treatment of a fractured left tibia.", [1]),
    "c2": _make_chunk("c2", "X-ray confirmed a displaced fracture of the proximal tibia. Surgery was scheduled for August 16.", [1, 2]),
    "c3": _make_chunk("c3", "The total billed amount for the procedure was $12,450.00, covered under insurance policy #INS-9982.", [3]),
}
PROVIDED_IDS = set(CHUNKS.keys())


# ── Module 3A: Per-claim enrichment ──────────────────────────────────────


class TestGroundedKeyPointEnrichment:
    def test_grounded_point_has_page_numbers(self):
        raw_kps = [
            {"point": "Patient admitted on 2024-08-15.", "chunk_ids": ["c1"]},
        ]
        points, _ = audit_grounding(raw_kps, ["c1"], PROVIDED_IDS, CHUNKS)
        assert points[0].page_numbers == [1]

    def test_grounded_point_has_evidence_snippet(self):
        raw_kps = [
            {"point": "Surgery scheduled.", "chunk_ids": ["c2"]},
        ]
        points, _ = audit_grounding(raw_kps, ["c2"], PROVIDED_IDS, CHUNKS)
        assert len(points[0].evidence_snippets) == 1
        assert "X-ray confirmed" in points[0].evidence_snippets[0]

    def test_multi_chunk_point_merges_pages(self):
        raw_kps = [
            {"point": "Claim spanning two chunks.", "chunk_ids": ["c1", "c2"]},
        ]
        points, _ = audit_grounding(raw_kps, ["c1", "c2"], PROVIDED_IDS, CHUNKS)
        assert points[0].page_numbers == [1, 2]
        assert len(points[0].evidence_snippets) == 2

    def test_ungrounded_point_has_empty_pages_and_snippets(self):
        raw_kps = [
            {"point": "Unsupported claim.", "chunk_ids": []},
        ]
        points, _ = audit_grounding(raw_kps, [], PROVIDED_IDS, CHUNKS)
        assert points[0].page_numbers == []
        assert points[0].evidence_snippets == []
        assert not points[0].grounded

    def test_snippet_targets_relevant_region(self):
        """Snippet should find the region matching the claim, not just the head."""
        long_chunk = _make_chunk(
            "long1",
            (
                "This is a long preamble with irrelevant boilerplate text. "
                "Section 1: Administrative details and contact information. "
                "Section 2: Background narrative about the case history. "
                "Section 3: The patient was diagnosed with Type 2 Diabetes "
                "on 2024-03-15 and prescribed Metformin 500mg twice daily. "
                "Section 4: Follow-up appointments and discharge notes. "
                "Section 5: Billing information and insurance codes."
            ),
            [1, 2],
        )
        chunk_map = {"long1": long_chunk}
        raw_kps = [
            {"point": "Patient diagnosed with Type 2 Diabetes, prescribed Metformin.", "chunk_ids": ["long1"]},
        ]
        points, _ = audit_grounding(raw_kps, ["long1"], {"long1"}, chunk_map)
        snippet = points[0].evidence_snippets[0]
        assert "Diabetes" in snippet or "diabetes" in snippet
        assert "Metformin" in snippet or "metformin" in snippet

    def test_short_chunk_returns_full_text(self):
        short_chunk = _make_chunk("s1", "Short chunk text.", [1])
        raw_kps = [{"point": "Claim.", "chunk_ids": ["s1"]}]
        points, _ = audit_grounding(raw_kps, ["s1"], {"s1"}, {"s1": short_chunk})
        assert points[0].evidence_snippets[0] == "Short chunk text."

    def test_hallucinated_chunk_id_excluded_from_enrichment(self):
        raw_kps = [
            {"point": "Claim with fake ID.", "chunk_ids": ["c1", "fake_99"]},
        ]
        points, audit = audit_grounding(raw_kps, ["c1", "fake_99"], PROVIDED_IDS, CHUNKS)
        assert points[0].grounded
        assert points[0].chunk_ids == ["c1"]
        assert len(points[0].evidence_snippets) == 1
        assert audit.chunks_cited_invalid == 1


# ── Module 3B: Unsupported-claim safeguards ──────────────────────────────


class TestGroundingSafeguards:
    def test_all_grounded_no_change(self):
        raw_kps = [
            {"point": "Claim 1.", "chunk_ids": ["c1"]},
            {"point": "Claim 2.", "chunk_ids": ["c2"]},
        ]
        points, audit = audit_grounding(raw_kps, ["c1", "c2"], PROVIDED_IDS, CHUNKS)
        points, audit = apply_grounding_safeguards(points, audit)
        assert not audit.needs_review
        assert audit.grounding_score == 1.0

    def test_zero_grounded_triggers_mandatory_review(self):
        raw_kps = [
            {"point": "Claim 1.", "chunk_ids": []},
            {"point": "Claim 2.", "chunk_ids": []},
        ]
        points, audit = audit_grounding(raw_kps, [], PROVIDED_IDS, CHUNKS)
        points, audit = apply_grounding_safeguards(points, audit)
        assert audit.needs_review
        assert any("zero" in w.lower() or "Zero" in w for w in audit.warnings)

    def test_hallucinated_ids_trigger_review(self):
        raw_kps = [
            {"point": "Claim.", "chunk_ids": ["fake_1"]},
        ]
        points, audit = audit_grounding(raw_kps, ["fake_1"], PROVIDED_IDS, CHUNKS)
        points, audit = apply_grounding_safeguards(points, audit)
        assert audit.needs_review

    def test_partial_grounding_below_threshold(self):
        raw_kps = [
            {"point": "Grounded claim.", "chunk_ids": ["c1"]},
            {"point": "Ungrounded 1.", "chunk_ids": []},
            {"point": "Ungrounded 2.", "chunk_ids": []},
            {"point": "Ungrounded 3.", "chunk_ids": []},
        ]
        points, audit = audit_grounding(raw_kps, ["c1"], PROVIDED_IDS, CHUNKS)
        points, audit = apply_grounding_safeguards(points, audit)
        assert audit.needs_review
        assert audit.grounding_score == 0.25


# ── Module 3C: Evidence gap analysis ─────────────────────────────────────


class TestEvidenceGapAnalysis:
    def test_fully_grounded_analysis(self):
        raw_kps = [
            {"point": "Claim 1.", "chunk_ids": ["c1", "c2"]},
            {"point": "Claim 2.", "chunk_ids": ["c3"]},
        ]
        points, _ = audit_grounding(raw_kps, ["c1", "c2", "c3"], PROVIDED_IDS, CHUNKS)
        gap = build_evidence_gap_analysis(points, PROVIDED_IDS, ["c1", "c2", "c3"], CHUNKS, total_pages=3)

        assert gap.total_claims == 2
        assert gap.grounded_claims == 2
        assert gap.ungrounded_claims == 0
        assert gap.strong_evidence_claims == 1
        assert gap.weak_evidence_claims == 1
        assert gap.overall_strength == "strong"
        assert gap.chunks_cited == 3
        assert gap.chunks_unused == 0
        assert 1 in gap.pages_with_evidence
        assert 3 in gap.pages_with_evidence

    def test_partial_grounding_analysis(self):
        raw_kps = [
            {"point": "Supported claim.", "chunk_ids": ["c1"]},
            {"point": "Unsupported claim.", "chunk_ids": []},
        ]
        points, _ = audit_grounding(raw_kps, ["c1"], PROVIDED_IDS, CHUNKS)
        gap = build_evidence_gap_analysis(points, PROVIDED_IDS, ["c1"], CHUNKS, total_pages=3)

        assert gap.total_claims == 2
        assert gap.grounded_claims == 1
        assert gap.ungrounded_claims == 1
        assert gap.overall_strength == "weak"
        assert gap.chunks_unused == 2

    def test_zero_claims_analysis(self):
        gap = build_evidence_gap_analysis([], PROVIDED_IDS, [], CHUNKS, total_pages=3)
        assert gap.total_claims == 0
        assert gap.overall_strength == "none"

    def test_all_ungrounded_analysis(self):
        raw_kps = [
            {"point": "Claim 1.", "chunk_ids": []},
            {"point": "Claim 2.", "chunk_ids": []},
        ]
        points, _ = audit_grounding(raw_kps, [], PROVIDED_IDS, CHUNKS)
        gap = build_evidence_gap_analysis(points, PROVIDED_IDS, [], CHUNKS, total_pages=3)

        assert gap.ungrounded_claims == 2
        assert gap.overall_strength == "none"
        assert gap.no_evidence_claims == 2
        assert gap.pages_with_evidence == []
        assert len(gap.pages_without_evidence) == 3

    def test_gap_analysis_pages_coverage(self):
        raw_kps = [
            {"point": "Claim on page 1.", "chunk_ids": ["c1"]},
        ]
        points, _ = audit_grounding(raw_kps, ["c1"], PROVIDED_IDS, CHUNKS)
        gap = build_evidence_gap_analysis(points, PROVIDED_IDS, ["c1"], CHUNKS, total_pages=3)

        assert gap.pages_with_evidence == [1]
        assert 2 in gap.pages_without_evidence
        assert 3 in gap.pages_without_evidence

    def test_claims_list_in_gap(self):
        raw_kps = [
            {"point": "Strong claim.", "chunk_ids": ["c1", "c2"]},
            {"point": "Weak claim.", "chunk_ids": ["c3"]},
            {"point": "No evidence.", "chunk_ids": []},
        ]
        points, _ = audit_grounding(raw_kps, ["c1", "c2", "c3"], PROVIDED_IDS, CHUNKS)
        gap = build_evidence_gap_analysis(points, PROVIDED_IDS, ["c1", "c2", "c3"], CHUNKS, total_pages=3)

        assert len(gap.claims) == 3
        assert gap.claims[0].evidence_strength == "strong"
        assert gap.claims[1].evidence_strength == "weak"
        assert gap.claims[2].evidence_strength == "none"

    def test_summary_string(self):
        raw_kps = [
            {"point": "Claim 1.", "chunk_ids": ["c1", "c2"]},
            {"point": "Claim 2.", "chunk_ids": []},
        ]
        points, _ = audit_grounding(raw_kps, ["c1", "c2"], PROVIDED_IDS, CHUNKS)
        gap = build_evidence_gap_analysis(points, PROVIDED_IDS, ["c1", "c2"], CHUNKS, total_pages=3)

        assert "1/2 claims grounded" in gap.summary
        assert "1 unsupported" in gap.summary
