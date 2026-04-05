"""Module 9B — Summary evaluation dimensions.

Scores summaries using multiple independent dimensions rather than one metric:

  1. factual_coverage  — fraction of expected key facts found in the summary text
  2. grounding_score   — fraction of key points backed by evidence (from GroundingAudit)
  3. contradiction_count — count of key points flagged as ungrounded (possible contradiction)
  4. evidence_support   — fraction of evidence chunks actually cited
  5. actionability      — heuristic score for presence of concrete, actionable language

Each dimension is scored 0.0–1.0 (except contradiction_count which is an integer).
This design avoids the "one metric to rule them all" trap — reviewers and evaluation
dashboards can weight dimensions differently for different use cases.

Key facts matching uses fuzzy substring containment: an expected fact counts as
"covered" if its normalised tokens are a subset of the summary's normalised tokens.
This is intentionally lenient — it measures recall of information, not stylistic fidelity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Fuzzy matching helpers ───────────────────────────────────────────────

_WORD_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset({
    "a", "an", "the", "is", "was", "were", "are", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "can", "could", "of", "in", "to", "for",
    "with", "on", "at", "by", "from", "as", "into", "about", "and", "or",
    "but", "if", "then", "that", "this", "it", "its",
})

COVERAGE_THRESHOLD = 0.55


def _tokenise(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _fact_covered(fact_tokens: set[str], summary_tokens: set[str]) -> bool:
    """A fact is covered when ≥55% of its content tokens appear in the summary.

    The threshold is intentionally lenient — ground truth facts often contain
    very specific compound phrases ("lumbar disc herniation L4-L5 with L5
    nerve root compression") and the LLM may paraphrase or abbreviate while
    still conveying the same information.  55% catches meaningful overlap
    while filtering out truly absent facts.
    """
    if not fact_tokens:
        return True
    overlap = fact_tokens & summary_tokens
    return len(overlap) / len(fact_tokens) >= COVERAGE_THRESHOLD


# ── Actionability heuristic ──────────────────────────────────────────────

_ACTION_SIGNALS = [
    "recommend", "follow-up", "refer", "plan", "schedule", "continue",
    "request", "next step", "deadline", "within", "payment due",
    "action required", "pending", "should", "advised", "prescribe",
]


def _score_actionability(text: str) -> float:
    lower = text.lower()
    hits = sum(1 for s in _ACTION_SIGNALS if s in lower)
    return min(hits / 3.0, 1.0)


# ── Summary dimensions ───────────────────────────────────────────────────


@dataclass
class FactCoverageDetail:
    """Per-fact match status."""

    fact: str
    covered: bool


@dataclass
class SummaryDimensions:
    """Multi-dimensional summary evaluation result."""

    fixture: str

    factual_coverage: float = 0.0
    fact_details: list[FactCoverageDetail] = field(default_factory=list)

    grounding_score: float = 0.0
    contradiction_count: int = 0
    evidence_support: float = 0.0
    actionability: float = 0.0

    chunks_provided: int = 0
    chunks_cited: int = 0
    key_points_total: int = 0
    key_points_grounded: int = 0
    needs_review: bool = False

    summarisation_time_ms: int = 0


def score_summary(
    fixture: str,
    expected_key_facts: list[str],
    summary_text: str,
    grounding_audit: dict | None = None,
    summarisation_meta: dict | None = None,
    processing_time_ms: int = 0,
) -> SummaryDimensions:
    """Score a summary across all evaluation dimensions.

    Parameters
    ----------
    expected_key_facts : from ground_truth.json
    summary_text : the LLM-generated summary text
    grounding_audit : serialised GroundingAudit (from ExtractionResult)
    summarisation_meta : serialised SummarisationMeta
    processing_time_ms : end-to-end summarisation latency
    """
    dims = SummaryDimensions(fixture=fixture, summarisation_time_ms=processing_time_ms)

    # ── 1. Factual coverage ──────────────────────────────────────────
    summary_tokens = _tokenise(summary_text)
    covered = 0
    for fact in expected_key_facts:
        fact_tokens = _tokenise(fact)
        is_covered = _fact_covered(fact_tokens, summary_tokens)
        dims.fact_details.append(FactCoverageDetail(fact=fact, covered=is_covered))
        if is_covered:
            covered += 1

    dims.factual_coverage = covered / len(expected_key_facts) if expected_key_facts else 1.0

    # ── 2. Grounding score (from GroundingAudit) ─────────────────────
    if grounding_audit:
        dims.grounding_score = grounding_audit.get("grounding_score", 0.0)
        dims.contradiction_count = grounding_audit.get("key_points_ungrounded", 0)
        dims.chunks_provided = grounding_audit.get("chunks_provided", 0)
        dims.chunks_cited = grounding_audit.get("chunks_cited_valid", 0)
        dims.key_points_total = grounding_audit.get("key_points_total", 0)
        dims.key_points_grounded = grounding_audit.get("key_points_grounded", 0)
        dims.needs_review = grounding_audit.get("needs_review", False)

    # ── 3. Evidence support ──────────────────────────────────────────
    if summarisation_meta:
        dims.evidence_support = summarisation_meta.get("evidence_usage_ratio", 0.0)

    # ── 4. Actionability ─────────────────────────────────────────────
    dims.actionability = _score_actionability(summary_text)

    return dims
