"""Coverage-aware AI input preparation (Phase 7B).

Tracks what the LLM actually sees vs what exists in the document,
generating both a structured report and a plain-text disclosure
that can be injected into the LLM prompt.

The LLM should never be surprised that it's working with partial data.
When it knows coverage is limited, it can:
  - hedge appropriately
  - avoid false-confidence in its completeness
  - note which sections it hasn't seen
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from data_model import Document, DocumentChunk, SummarisationMeta


class CoverageReport(BaseModel):
    """Detailed analysis of what the selected chunks cover."""

    total_chunks: int = 0
    selected_chunks: int = 0
    chunk_coverage_ratio: float = 0.0

    total_pages: int = 0
    pages_covered: list[int] = Field(default_factory=list)
    pages_missing: list[int] = Field(default_factory=list)
    page_coverage_ratio: float = 0.0

    total_sections: int = 0
    sections_covered: list[str] = Field(default_factory=list)
    sections_missing: list[str] = Field(default_factory=list)
    section_coverage_ratio: float = 0.0

    is_comprehensive: bool = False
    coverage_level: str = "unknown"
    disclosure_text: str = ""


COVERAGE_THRESHOLDS = {
    "comprehensive": 0.80,
    "good": 0.50,
    "partial": 0.25,
    "minimal": 0.0,
}


def build_coverage_report(
    doc: Document,
    selected: list[DocumentChunk],
) -> CoverageReport:
    """Analyse coverage of selected chunks against the full document."""
    total_chunks = len(doc.chunks)
    total_pages = doc.parse_meta.page_count if doc.parse_meta else len(doc.pages)
    all_pages = set(range(1, total_pages + 1))
    all_sections = {s.label for s in doc.sections} if doc.sections else set()

    if not all_sections:
        all_sections = {c.section_label for c in doc.chunks if c.section_label}

    pages_covered = sorted({p for c in selected for p in c.page_numbers})
    pages_missing = sorted(all_pages - set(pages_covered))
    sections_covered = sorted({c.section_label for c in selected if c.section_label})
    sections_missing = sorted(all_sections - set(sections_covered))

    chunk_ratio = len(selected) / total_chunks if total_chunks > 0 else 1.0
    page_ratio = len(pages_covered) / total_pages if total_pages > 0 else 1.0
    section_ratio = (
        len(sections_covered) / len(all_sections)
        if all_sections else 1.0
    )

    avg_ratio = (chunk_ratio + page_ratio + section_ratio) / 3.0

    if avg_ratio >= COVERAGE_THRESHOLDS["comprehensive"]:
        level = "comprehensive"
    elif avg_ratio >= COVERAGE_THRESHOLDS["good"]:
        level = "good"
    elif avg_ratio >= COVERAGE_THRESHOLDS["partial"]:
        level = "partial"
    else:
        level = "minimal"

    is_comprehensive = level == "comprehensive"

    disclosure = _build_disclosure_text(
        total_chunks=total_chunks,
        selected_count=len(selected),
        chunk_ratio=chunk_ratio,
        total_pages=total_pages,
        pages_covered=pages_covered,
        pages_missing=pages_missing,
        sections_covered=sections_covered,
        sections_missing=sections_missing,
        level=level,
    )

    return CoverageReport(
        total_chunks=total_chunks,
        selected_chunks=len(selected),
        chunk_coverage_ratio=round(chunk_ratio, 4),
        total_pages=total_pages,
        pages_covered=pages_covered,
        pages_missing=pages_missing,
        page_coverage_ratio=round(page_ratio, 4),
        total_sections=len(all_sections),
        sections_covered=sections_covered,
        sections_missing=sections_missing,
        section_coverage_ratio=round(section_ratio, 4),
        is_comprehensive=is_comprehensive,
        coverage_level=level,
        disclosure_text=disclosure,
    )


def _build_disclosure_text(
    *,
    total_chunks: int,
    selected_count: int,
    chunk_ratio: float,
    total_pages: int,
    pages_covered: list[int],
    pages_missing: list[int],
    sections_covered: list[str],
    sections_missing: list[str],
    level: str,
) -> str:
    """Generate a plain-text coverage disclosure for the LLM prompt."""
    lines: list[str] = [
        "=== COVERAGE DISCLOSURE ===",
        f"You are seeing {selected_count} of {total_chunks} chunks "
        f"({chunk_ratio:.0%} of document content).",
    ]

    if total_pages > 0:
        lines.append(
            f"Pages covered: {_summarise_range(pages_covered)} "
            f"({len(pages_covered)}/{total_pages} pages)."
        )
        if pages_missing and len(pages_missing) <= 10:
            lines.append(f"Pages NOT covered: {_summarise_range(pages_missing)}.")
        elif pages_missing:
            lines.append(f"{len(pages_missing)} pages are not included in your context.")

    if sections_covered:
        lines.append(f"Sections covered: {', '.join(sections_covered)}.")
    if sections_missing:
        lines.append(f"Sections NOT covered: {', '.join(sections_missing)}.")

    if level == "minimal":
        lines.append(
            "WARNING: You have very limited visibility into this document. "
            "State clearly that your analysis is based on a small subset."
        )
    elif level == "partial":
        lines.append(
            "IMPORTANT: Your context covers only part of the document. "
            "Note any areas where missing pages or sections could affect your analysis."
        )
    elif level == "good":
        lines.append(
            "You have reasonable coverage but some sections/pages are missing. "
            "Flag if a finding seems incomplete due to missing context."
        )

    lines.append("=== END COVERAGE DISCLOSURE ===")
    return "\n".join(lines)


def _summarise_range(nums: list[int]) -> str:
    """Collapse a sorted list of ints into a human-readable range string."""
    if not nums:
        return "(none)"
    if len(nums) <= 5:
        return ", ".join(str(n) for n in nums)

    ranges: list[str] = []
    start = nums[0]
    end = nums[0]
    for n in nums[1:]:
        if n == end + 1:
            end = n
        else:
            ranges.append(f"{start}-{end}" if start != end else str(start))
            start = end = n
    ranges.append(f"{start}-{end}" if start != end else str(start))
    return ", ".join(ranges)
