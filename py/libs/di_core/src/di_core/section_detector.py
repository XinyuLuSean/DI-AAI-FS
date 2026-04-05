"""Heuristic section detector for document structure awareness.

Detects structural sections by scanning page text for heading-like patterns:
  - ALL CAPS lines (common in legal/medical documents)
  - Numbered headings ("1. Introduction", "Section 2:")
  - Known domain section names ("DIAGNOSIS", "BILLING SUMMARY", etc.)

The detector is intentionally simple — it provides a lightweight structural
signal for retrieval and ranking without requiring ML.  Incorrect labels are
acceptable because they are always inspectable and never used as hard truth.

Future evolution:
  - ML-based section classifier trained on HITL corrections
  - Table-of-contents parsing for PDFs that have one
  - Font-size / bold detection via PyMuPDF layout analysis
"""

from __future__ import annotations

import re

from data_model import Document, SectionLabel

# Lines that are likely headings: ALL CAPS (≥3 words), or numbered patterns
_ALLCAPS_HEADING = re.compile(r"^[A-Z][A-Z\s,&/\-]{8,}$")
_NUMBERED_HEADING = re.compile(
    r"^(?:(?:Section|Part|Article|Chapter)\s+)?\d+[\.\)]\s+[A-Z]",
    re.IGNORECASE,
)
_ROMAN_HEADING = re.compile(
    r"^(?:(?:Section|Part)\s+)?(?:I{1,3}|IV|VI{0,3}|IX|X{1,3})[\.\):\s]+[A-Z]",
)

# Domain-specific section names commonly found in legal/medical/billing docs
_KNOWN_SECTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bdiagnosis\b", re.I), "Diagnosis"),
    (re.compile(r"\btreatment\s*plan\b", re.I), "Treatment Plan"),
    (re.compile(r"\bmedical\s*history\b", re.I), "Medical History"),
    (re.compile(r"\bprogress\s*note", re.I), "Progress Note"),
    (re.compile(r"\bvital\s*signs\b", re.I), "Vital Signs"),
    (re.compile(r"\bmedication", re.I), "Medications"),
    (re.compile(r"\bbilling\s*summary\b", re.I), "Billing Summary"),
    (re.compile(r"\bcharges?\b.*\btotal\b|\btotal\b.*\bcharges?\b", re.I), "Charges"),
    (re.compile(r"\bstatement\s*of\s*account\b", re.I), "Statement of Account"),
    (re.compile(r"\bconclusion", re.I), "Conclusion"),
    (re.compile(r"\bsummar(?:y|ies)\b", re.I), "Summary"),
    (re.compile(r"\bfindings?\b", re.I), "Findings"),
    (re.compile(r"\brecommendation", re.I), "Recommendations"),
    (re.compile(r"\bappendix\b", re.I), "Appendix"),
    (re.compile(r"\bexhibit\s+[A-Z0-9]", re.I), "Exhibit"),
    (re.compile(r"\bdeposition\b", re.I), "Deposition"),
    (re.compile(r"\btestimony\b", re.I), "Testimony"),
    (re.compile(r"\bdamage\s*assessment\b", re.I), "Damage Assessment"),
    (re.compile(r"\bestimate\b", re.I), "Estimate"),
    (re.compile(r"\bcorrespondence\b", re.I), "Correspondence"),
]

MIN_HEADING_LEN = 3
MAX_HEADING_LEN = 120


def detect_sections(doc: Document) -> list[SectionLabel]:
    """Scan document pages for heading-like patterns and return section labels.

    Each section spans from its detected heading to the start of the next
    section (or end of document).  Sections are returned in page order.
    """
    raw_hits: list[tuple[int, int, str, str, float]] = []

    char_offset = 0
    for page in doc.pages:
        lines = page.text.split("\n")
        page_char = char_offset
        for line in lines:
            stripped = line.strip()
            if len(stripped) < MIN_HEADING_LEN or len(stripped) > MAX_HEADING_LEN:
                page_char += len(line) + 1
                continue

            label, method, conf = _classify_line(stripped)
            if label:
                raw_hits.append((page.page_number, page_char, label, method, conf))

            page_char += len(line) + 1
        char_offset += len(page.text) + 2  # +2 for page join separator

    if not raw_hits:
        return []

    sections: list[SectionLabel] = []
    for i, (page_num, char_start, label, method, conf) in enumerate(raw_hits):
        if i + 1 < len(raw_hits):
            next_page, next_char = raw_hits[i + 1][0], raw_hits[i + 1][1]
            page_end = next_page
            char_end = next_char
        else:
            page_end = doc.pages[-1].page_number if doc.pages else page_num
            char_end = char_offset

        sections.append(SectionLabel(
            label=label,
            page_start=page_num,
            page_end=page_end,
            char_start=char_start,
            char_end=char_end,
            detection_method=method,
            confidence=conf,
        ))

    return _deduplicate_sections(sections)


def section_label_for_chunk(
    sections: list[SectionLabel],
    chunk_page_numbers: list[int],
    chunk_char_start: int,
) -> str:
    """Find the best section label for a given chunk.

    Returns the label of the section whose char range contains the chunk
    start, falling back to page overlap.  Returns "" if no section matches.
    """
    for section in reversed(sections):
        if section.char_start <= chunk_char_start < section.char_end:
            return section.label

    if not chunk_page_numbers:
        return ""

    chunk_first_page = chunk_page_numbers[0]
    for section in reversed(sections):
        if section.page_start <= chunk_first_page <= section.page_end:
            return section.label

    return ""


def _classify_line(line: str) -> tuple[str, str, float]:
    """Return (label, method, confidence) or ("", "", 0) if not a heading."""
    for pattern, label in _KNOWN_SECTIONS:
        if pattern.search(line) and len(line) < 80:
            return label, "domain_keyword", 0.7

    if _ALLCAPS_HEADING.match(line):
        label = line.strip().title()
        return label, "allcaps_heading", 0.6

    if _NUMBERED_HEADING.match(line):
        return line.strip()[:60], "numbered_heading", 0.5

    if _ROMAN_HEADING.match(line):
        return line.strip()[:60], "roman_heading", 0.5

    return "", "", 0.0


def _deduplicate_sections(sections: list[SectionLabel]) -> list[SectionLabel]:
    """Remove back-to-back duplicate labels (same label, adjacent pages)."""
    if not sections:
        return sections

    result: list[SectionLabel] = [sections[0]]
    for s in sections[1:]:
        prev = result[-1]
        if s.label == prev.label and s.page_start <= prev.page_end + 1:
            prev.page_end = max(prev.page_end, s.page_end)
            prev.char_end = max(prev.char_end, s.char_end)
        else:
            result.append(s)
    return result
