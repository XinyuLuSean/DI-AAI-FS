"""Page-level text preprocessing — runs between parsing and chunking.

Transforms raw parsed text into cleaner input for downstream stages:
  - Unicode normalization (NFC)
  - Whitespace normalization (collapse runs, strip trailing per line)
  - Control character removal
  - Repeated header/footer detection and removal
  - Consecutive duplicate line suppression

Design principles:
  - Every transformation is recorded in PreprocessMeta
  - Original text is replaced in-place on DocumentPage (the parser already
    captured raw provenance via ParseMeta)
  - Preprocessing never invents content — it only removes noise
  - Each step is independently toggleable for debugging
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from pydantic import BaseModel, Field

from data_model import Document, DocumentPage

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TRAILING_WHITESPACE = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANK_LINE_RUNS = re.compile(r"\n{4,}")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")

MIN_PAGES_FOR_HEADER_DETECTION = 3
HEADER_FOOTER_LINES = 3
HEADER_FOOTER_FREQUENCY_THRESHOLD = 0.6


class PreprocessConfig(BaseModel):
    """Toggleable preprocessing steps."""

    unicode_normalize: bool = True
    strip_control_chars: bool = True
    normalize_whitespace: bool = True
    remove_repeated_headers: bool = True
    suppress_duplicate_lines: bool = True


class PreprocessMeta(BaseModel):
    """Records what the preprocessor changed for transparency and debugging."""

    applied: bool = False
    chars_before: int = 0
    chars_after: int = 0
    chars_removed: int = 0
    unicode_normalizations: int = 0
    control_chars_removed: int = 0
    whitespace_reductions: int = 0
    headers_removed: int = 0
    footers_removed: int = 0
    duplicate_lines_suppressed: int = 0
    detected_headers: list[str] = Field(default_factory=list)
    detected_footers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def preprocess_document(
    doc: Document,
    config: PreprocessConfig | None = None,
) -> tuple[Document, PreprocessMeta]:
    """Clean all page text and return updated document + meta.

    The function modifies doc.pages in place (replacing text and char_count)
    and returns a PreprocessMeta record that the API layer attaches to the
    document for observability.
    """
    cfg = config or PreprocessConfig()
    meta = PreprocessMeta(applied=True)

    if not doc.pages:
        meta.warnings.append("No pages to preprocess")
        return doc, meta

    meta.chars_before = sum(len(p.text) for p in doc.pages)

    headers, footers = _detect_repeated_headers_footers(doc.pages)
    meta.detected_headers = headers
    meta.detected_footers = footers

    for page in doc.pages:
        original = page.text

        if cfg.unicode_normalize:
            page.text, n = _normalize_unicode(page.text)
            meta.unicode_normalizations += n

        if cfg.strip_control_chars:
            page.text, n = _strip_control_chars(page.text)
            meta.control_chars_removed += n

        if cfg.normalize_whitespace:
            before_len = len(page.text)
            page.text = _normalize_whitespace(page.text)
            if len(page.text) < before_len:
                meta.whitespace_reductions += 1

        if cfg.remove_repeated_headers and headers:
            page.text, removed = _remove_lines(page.text, headers, position="top")
            meta.headers_removed += removed

        if cfg.remove_repeated_headers and footers:
            page.text, removed = _remove_lines(page.text, footers, position="bottom")
            meta.footers_removed += removed

        if cfg.suppress_duplicate_lines:
            page.text, n = _suppress_consecutive_duplicates(page.text)
            meta.duplicate_lines_suppressed += n

        page.char_count = len(page.text.strip())

    meta.chars_after = sum(len(p.text) for p in doc.pages)
    meta.chars_removed = meta.chars_before - meta.chars_after

    if meta.chars_removed > meta.chars_before * 0.5 and meta.chars_before > 100:
        meta.warnings.append(
            f"Preprocessing removed {meta.chars_removed}/{meta.chars_before} chars "
            f"({meta.chars_removed / meta.chars_before:.0%}) — inspect results carefully"
        )

    return doc, meta


def _normalize_unicode(text: str) -> tuple[str, int]:
    """NFC-normalize and count changed characters."""
    normalized = unicodedata.normalize("NFC", text)
    changes = sum(1 for a, b in zip(text, normalized) if a != b)
    return normalized, changes


def _strip_control_chars(text: str) -> tuple[str, int]:
    """Remove non-printable control characters (preserving newlines and tabs)."""
    cleaned = _CONTROL_CHARS.sub("", text)
    removed = len(text) - len(cleaned)
    return cleaned, removed


def _normalize_whitespace(text: str) -> str:
    """Collapse horizontal whitespace runs, strip trailing, limit blank lines."""
    text = _TRAILING_WHITESPACE.sub("", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _BLANK_LINE_RUNS.sub("\n\n\n", text)
    return text


def _detect_repeated_headers_footers(
    pages: list[DocumentPage],
) -> tuple[list[str], list[str]]:
    """Find lines that repeat across most pages at top/bottom positions.

    Only runs when there are enough pages to make frequency meaningful.
    Returns normalized line strings for matching.
    """
    if len(pages) < MIN_PAGES_FOR_HEADER_DETECTION:
        return [], []

    top_counter: Counter[str] = Counter()
    bottom_counter: Counter[str] = Counter()

    for page in pages:
        lines = [ln.strip() for ln in page.text.splitlines() if ln.strip()]
        if not lines:
            continue
        for ln in lines[:HEADER_FOOTER_LINES]:
            top_counter[ln] += 1
        for ln in lines[-HEADER_FOOTER_LINES:]:
            bottom_counter[ln] += 1

    threshold = len(pages) * HEADER_FOOTER_FREQUENCY_THRESHOLD

    headers = [
        ln for ln, count in top_counter.items()
        if count >= threshold and len(ln) < 200
    ]
    footers = [
        ln for ln, count in bottom_counter.items()
        if count >= threshold and len(ln) < 200
    ]

    return headers, footers


def _remove_lines(
    text: str,
    targets: list[str],
    position: str,
) -> tuple[str, int]:
    """Remove target lines from the top or bottom of the text."""
    lines = text.splitlines(keepends=True)
    removed = 0
    target_set = set(targets)

    if position == "top":
        while lines and lines[0].strip() in target_set:
            lines.pop(0)
            removed += 1
    elif position == "bottom":
        while lines and lines[-1].strip() in target_set:
            lines.pop()
            removed += 1

    return "".join(lines), removed


def _suppress_consecutive_duplicates(text: str) -> tuple[str, int]:
    """Remove consecutive duplicate non-blank lines."""
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    suppressed = 0
    prev_stripped = None

    for line in lines:
        stripped = line.strip()
        if stripped and stripped == prev_stripped:
            suppressed += 1
            continue
        result.append(line)
        prev_stripped = stripped

    return "".join(result), suppressed
