"""Heuristic document type router.

Classifies a parsed document into a DocumentType using two signal sources:
  1. Filename pattern matching
  2. Content keyword scanning (first N pages)

No ML is used.  Every prediction is explainable through the list of matched
rules stored in RoutingResult.  This is intentional: for an MVP, explainable
heuristics are more debuggable and trustworthy than an opaque classifier.

Future evolution:
  - ML classifier trained on labelled corrections from HITL
  - Ensemble of heuristics + ML with calibrated confidence
"""

from __future__ import annotations

import re
from collections import Counter

from data_model import Document, DocumentType, RoutingResult, RoutingRule

MAX_SCAN_PAGES = 5

# ── Filename heuristics ──────────────────────────────────────────────────

_FILENAME_RULES: list[tuple[re.Pattern[str], DocumentType, float]] = [
    (re.compile(r"invoice|bill|statement|receipt", re.I), DocumentType.BILLING, 1.0),
    (re.compile(r"medical|diagnosis|clinical|patient|hospital|lab.?report", re.I), DocumentType.MEDICAL, 1.0),
    (re.compile(r"legal|contract|agreement|court|deposition|subpoena|judgment", re.I), DocumentType.LEGAL, 1.0),
    (re.compile(r"treatment|therapy|rehab|session.?note", re.I), DocumentType.TREATMENT, 1.0),
    (re.compile(r"letter|memo|correspondence|notice|fax", re.I), DocumentType.CORRESPONDENCE, 0.8),
    (re.compile(r"claim|adjuster|insurance|policy", re.I), DocumentType.LEGAL, 0.6),
]

# ── Content keyword heuristics ───────────────────────────────────────────

_CONTENT_RULES: list[tuple[list[str], DocumentType, float]] = [
    (
        ["invoice", "amount due", "total due", "billing", "payment due",
         "balance", "account number", "remit"],
        DocumentType.BILLING, 1.0,
    ),
    (
        ["patient", "diagnosis", "physician", "medical record", "clinical",
         "hospital", "lab result", "vital signs", "medication", "prognosis"],
        DocumentType.MEDICAL, 1.0,
    ),
    (
        ["court", "plaintiff", "defendant", "attorney", "counsel",
         "statute", "judgment", "verdict", "deposition", "sworn"],
        DocumentType.LEGAL, 1.0,
    ),
    (
        ["treatment plan", "therapy", "rehabilitation", "session note",
         "provider", "treatment goal", "functional status"],
        DocumentType.TREATMENT, 1.0,
    ),
    (
        ["dear", "sincerely", "regarding", "re:", "attention",
         "enclosed", "please find"],
        DocumentType.CORRESPONDENCE, 0.7,
    ),
    (
        ["claimant", "adjuster", "coverage", "policy number", "claim number",
         "insured", "deductible", "loss date", "date of loss"],
        DocumentType.LEGAL, 0.8,
    ),
    (
        ["repair estimate", "restoration", "damage assessment",
         "estimated cost", "emergency extraction"],
        DocumentType.BILLING, 0.6,
    ),
]


def route_document(doc: Document) -> RoutingResult:
    """Classify a parsed document using heuristic rules.

    Returns a RoutingResult with the predicted type, confidence, and the list
    of matched rules that explain the decision.
    """
    matched: list[RoutingRule] = []

    matched.extend(_match_filename(doc.filename))

    text_sample = _get_text_sample(doc)
    if text_sample:
        matched.extend(_match_content(text_sample))

    if not matched:
        return RoutingResult(
            predicted_type=DocumentType.UNKNOWN,
            confidence=0.0,
            is_fallback=True,
            warnings=["No heuristic rules matched — defaulting to unknown"],
        )

    scores: Counter[DocumentType] = Counter()
    for rule in matched:
        scores[rule.matched_type] += rule.weight

    best_type, best_score = scores.most_common(1)[0]
    total_weight = sum(scores.values())
    confidence = min(best_score / max(total_weight, 1.0), 1.0)

    runner_up_score = 0.0
    if len(scores) > 1:
        runner_up_score = scores.most_common(2)[1][1]

    warnings: list[str] = []
    if confidence < 0.4:
        warnings.append(
            f"Low confidence ({confidence:.2f}) — consider manual review"
        )
    if runner_up_score > 0 and (best_score - runner_up_score) / max(best_score, 1) < 0.3:
        runner_up_type = scores.most_common(2)[1][0]
        warnings.append(
            f"Close runner-up: {runner_up_type.value} "
            f"(score {runner_up_score:.1f} vs {best_score:.1f})"
        )

    return RoutingResult(
        predicted_type=best_type,
        confidence=round(confidence, 3),
        matched_rules=matched,
        is_fallback=False,
        warnings=warnings,
    )


def _match_filename(filename: str) -> list[RoutingRule]:
    rules: list[RoutingRule] = []
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    for pattern, doc_type, weight in _FILENAME_RULES:
        if pattern.search(stem):
            rules.append(RoutingRule(
                source="filename",
                pattern=pattern.pattern,
                matched_type=doc_type,
                weight=weight,
            ))
    return rules


def _match_content(text: str) -> list[RoutingRule]:
    rules: list[RoutingRule] = []
    text_lower = text.lower()
    for keywords, doc_type, weight in _CONTENT_RULES:
        hits = [kw for kw in keywords if kw in text_lower]
        if len(hits) >= 2:
            rules.append(RoutingRule(
                source="content",
                pattern=f"keywords: {', '.join(hits[:5])}",
                matched_type=doc_type,
                weight=weight * min(len(hits) / 3, 1.5),
            ))
    return rules


def _get_text_sample(doc: Document) -> str:
    """Concatenate the first N pages of text for keyword scanning."""
    pages = doc.pages[:MAX_SCAN_PAGES]
    return "\n".join(p.text for p in pages)
