"""Deterministic field extractor — regex and keyword-window heuristics.

This module extracts exact structured fields from document pages without
using an LLM.  It is intentionally separate from the summarisation path:
deterministic fields are evaluated on precision/recall, not narrative quality.

Design principles:
  - Conservative: return "not found" rather than guess
  - Explainable: every field carries extraction_method + source_snippet
  - Evidence-backed: every field links to page numbers
  - Composable: field definitions are data, not hard-coded control flow

Phase 9 improvements (evaluation-driven):
  - Preprocessing: strip markdown formatting (bold, italic, headings, table
    pipes) so regexes work on content regardless of source format.
  - Extended total_amount patterns for demand letters, damage estimates, and
    markdown tables.
  - PDF line-break tolerance for split field values.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from data_model import (
    Document,
    EvidenceReference,
    ExtractionMethod,
    ExtractionResult,
    OutputType,
    StructuredField,
)


# ── Text preprocessing ───────────────────────────────────────────────────
# Strip formatting artefacts so field regexes match content regardless of
# whether the source was plain text, markdown, or PDF with line breaks.

_MD_BOLD_ITALIC = re.compile(r"\*{1,3}|_{1,3}")
_MD_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_TABLE_SEP = re.compile(r"\|")
_MD_TABLE_DASHES = re.compile(r"^[\s|:-]+$", re.MULTILINE)
_MULTI_SPACE = re.compile(r"  +")


def _preprocess_for_extraction(text: str) -> str:
    """Normalise page text before regex extraction.

    Strips markdown bold/italic markers, heading prefixes, and table pipe
    delimiters so that ``**Patient Name:** Robert Thompson`` becomes
    ``Patient Name: Robert Thompson`` — matchable by the same regexes that
    work on plain text.
    """
    text = _MD_BOLD_ITALIC.sub("", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_TABLE_SEP.sub(" ", text)
    text = _MD_TABLE_DASHES.sub("", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text


@dataclass
class _FieldDef:
    """One field to attempt extraction for."""

    name: str
    patterns: list[re.Pattern[str]]
    method: ExtractionMethod
    group: int = 1


# ── Field definitions ────────────────────────────────────────────────────
# Each pattern is tried against every page.  First match wins per field.
# Group 1 is the extracted value unless group is overridden.

_FIELD_DEFS: list[_FieldDef] = [
    _FieldDef(
        name="claim_number",
        patterns=[
            re.compile(r"(?:case|claim)\s*(?:number|no\.?|#)\s*[:\s]*([A-Z0-9][\w-]{3,})", re.I),
        ],
        method=ExtractionMethod.REGEX,
    ),
    _FieldDef(
        name="policy_number",
        patterns=[
            re.compile(r"policy\s*(?:number|no\.?|#)\s*[:\s]*([A-Z0-9][\w-]{3,})", re.I),
        ],
        method=ExtractionMethod.REGEX,
    ),
    _FieldDef(
        name="invoice_number",
        patterns=[
            re.compile(r"invoice\s*(?:number|no\.?|#)\s*[:\s]*([A-Z0-9][\w-]{3,})", re.I),
        ],
        method=ExtractionMethod.REGEX,
    ),
    _FieldDef(
        name="total_amount",
        patterns=[
            re.compile(
                r"(?:total\s*(?:due|estimated\s*(?:cost|damages)|demand|charges|amount))"
                r"\s*[:\s]*\$?\s*([\d,]+\.?\d*)",
                re.I,
            ),
            re.compile(r"(?:net\s*payment)\s*[:\s]*\$\s*([\d,]+\.?\d*)", re.I),
            re.compile(r"total\s*[:\s]+\$\s*([\d,]+\.?\d*)", re.I),
        ],
        method=ExtractionMethod.REGEX,
    ),
    _FieldDef(
        name="service_date",
        patterns=[
            re.compile(
                r"(?:date\s*(?:of\s*(?:loss|service|injury))|invoice\s*date|service\s*date)"
                r"\s*[:\s]*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})",
                re.I,
            ),
        ],
        method=ExtractionMethod.REGEX,
    ),
    _FieldDef(
        name="patient_name",
        patterns=[
            re.compile(r"(?:patient\s*name|claimant)\s*[:\s]*([A-Z][a-z]+\s+[A-Z][a-z]+)", re.I),
        ],
        method=ExtractionMethod.KEYWORD_WINDOW,
    ),
    _FieldDef(
        name="provider_name",
        patterns=[
            re.compile(
                r"(?i:adjuster|attending\s*physician|physician|provider)"
                r"\s*:\s*(?:Dr\.?\s*)?([A-Z][a-z]+\s+[A-Z][a-z]+)",
            ),
        ],
        method=ExtractionMethod.KEYWORD_WINDOW,
    ),
    _FieldDef(
        name="account_number",
        patterns=[
            re.compile(r"account\s*(?:number|no\.?|#)\s*[:\s]*([A-Z0-9][\w-]{3,})", re.I),
        ],
        method=ExtractionMethod.REGEX,
    ),
    _FieldDef(
        name="mrn",
        patterns=[
            re.compile(r"(?:MRN|medical\s*record\s*(?:number|no\.?|#))\s*[:\s]*([A-Z0-9][\w-]{3,})", re.I),
        ],
        method=ExtractionMethod.REGEX,
    ),
]

SNIPPET_CONTEXT = 60


def extract_fields(doc: Document) -> ExtractionResult:
    """Run deterministic extraction over all pages of a document.

    Returns an ExtractionResult with structured_fields populated and
    summary=None (deterministic extraction is not summarisation).
    """
    start = time.perf_counter_ns()
    fields: list[StructuredField] = []

    for fdef in _FIELD_DEFS:
        field = _try_extract(doc, fdef)
        if field is not None:
            fields.append(field)

    elapsed_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    return ExtractionResult(
        document_id=doc.id,
        output_type=OutputType.DETERMINISTIC,
        model_used="deterministic",
        structured_fields=fields,
        summary=None,
        processing_time_ms=elapsed_ms,
    )


def _try_extract(doc: Document, fdef: _FieldDef) -> StructuredField | None:
    """Try each pattern against each page; return first match or None.

    Runs regex against preprocessed text (markdown/table formatting stripped)
    so patterns work uniformly across plain text, markdown, and PDF sources.
    Snippets are captured from the original text for display fidelity.
    """
    for page in doc.pages:
        cleaned = _preprocess_for_extraction(page.text)
        for pattern in fdef.patterns:
            m = pattern.search(cleaned)
            if m:
                value = m.group(fdef.group).strip()
                snippet = _extract_snippet(cleaned, m.start(), m.end())
                confidence = _score_confidence(value, fdef)
                return StructuredField(
                    field_name=fdef.name,
                    field_value=value,
                    confidence=confidence,
                    extraction_method=fdef.method.value,
                    source_snippet=snippet,
                    evidence=[
                        EvidenceReference(
                            chunk_id=f"page:{page.page_number}",
                            chunk_text=snippet,
                            relevance_score=confidence,
                            page_numbers=[page.page_number],
                        )
                    ],
                )
    return None


def _extract_snippet(text: str, match_start: int, match_end: int) -> str:
    """Return the matched text plus surrounding context."""
    ctx_start = max(0, match_start - SNIPPET_CONTEXT)
    ctx_end = min(len(text), match_end + SNIPPET_CONTEXT)
    snippet = text[ctx_start:ctx_end].strip()
    if ctx_start > 0:
        snippet = "…" + snippet
    if ctx_end < len(text):
        snippet = snippet + "…"
    return snippet


def _score_confidence(value: str, fdef: _FieldDef) -> float:
    """Conservative confidence based on value quality."""
    if not value:
        return 0.0
    if fdef.name == "total_amount":
        try:
            amt = float(value.replace(",", ""))
            return 0.9 if amt > 0 else 0.3
        except ValueError:
            return 0.3
    if fdef.name in ("claim_number", "policy_number", "invoice_number", "account_number", "mrn"):
        return 0.9 if len(value) >= 4 else 0.5
    if fdef.name in ("patient_name", "provider_name"):
        parts = value.split()
        return 0.8 if len(parts) >= 2 else 0.4
    if fdef.name == "service_date":
        return 0.85
    return 0.6
