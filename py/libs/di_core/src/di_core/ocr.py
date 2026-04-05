"""OCR adapter interface and implementations.

This module defines the OCR boundary for the document intelligence pipeline.
OCR is treated as an optional capability behind a clean interface so:
  - The parser can request OCR without knowing the provider
  - New backends (Tesseract, Textract, Google Vision) are swappable
  - The system degrades honestly when no OCR backend is available

Current state:
  - TesseractAdapter: stub that checks for local tesseract binary
  - TextractAdapter: stub placeholder for future AWS integration
  - NoOpAdapter: always returns unavailable (used as default fallback)
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OCRPageResult:
    """OCR output for a single page."""

    page_number: int
    text: str
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class OCRResult:
    """Complete OCR output for a document."""

    pages: list[OCRPageResult]
    backend: str
    available: bool = True
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


class OCRAdapter(ABC):
    """Abstract OCR adapter — all backends implement this interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name for logging and diagnostics."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether this OCR backend is currently usable."""

    @abstractmethod
    def extract_text(self, file_path: Path) -> OCRResult:
        """Run OCR on the file and return structured results.

        Implementations should never raise — return OCRResult with
        available=False and an error message instead.
        """


class TesseractAdapter(OCRAdapter):
    """Local Tesseract OCR adapter.

    Checks for the tesseract binary at instantiation time.
    Actual OCR execution is stubbed — this phase establishes the interface
    and availability detection only.
    """

    @property
    def name(self) -> str:
        return "tesseract"

    def is_available(self) -> bool:
        return shutil.which("tesseract") is not None

    def extract_text(self, file_path: Path) -> OCRResult:
        if not self.is_available():
            return OCRResult(
                pages=[],
                backend=self.name,
                available=False,
                error="tesseract binary not found on PATH",
                warnings=["Install tesseract: brew install tesseract (macOS) or apt-get install tesseract-ocr (Linux)"],
            )

        # Stub: real implementation would use pytesseract or subprocess
        return OCRResult(
            pages=[],
            backend=self.name,
            available=True,
            error="Tesseract OCR execution not yet implemented",
            warnings=["OCR adapter is available but extraction is stubbed for Phase 5"],
        )


class TextractAdapter(OCRAdapter):
    """AWS Textract OCR adapter (future).

    Placeholder for cloud-based OCR.  Will require:
      - boto3 / AWS credentials
      - async execution pattern (Textract is inherently async for large docs)
      - cost awareness (per-page pricing)
    """

    @property
    def name(self) -> str:
        return "textract"

    def is_available(self) -> bool:
        return False

    def extract_text(self, file_path: Path) -> OCRResult:
        return OCRResult(
            pages=[],
            backend=self.name,
            available=False,
            error="AWS Textract adapter not yet implemented",
            warnings=["Textract requires AWS credentials and boto3"],
        )


class NoOpAdapter(OCRAdapter):
    """No-op adapter used when OCR is disabled or unavailable."""

    @property
    def name(self) -> str:
        return "none"

    def is_available(self) -> bool:
        return False

    def extract_text(self, file_path: Path) -> OCRResult:
        return OCRResult(
            pages=[],
            backend=self.name,
            available=False,
            error="No OCR backend configured",
        )


def get_default_ocr_adapter() -> OCRAdapter:
    """Return the best available OCR adapter, falling back to NoOp.

    Priority: Tesseract (local) → NoOp.
    Future: Textract would be checked if AWS credentials are present.
    """
    tesseract = TesseractAdapter()
    if tesseract.is_available():
        return tesseract
    return NoOpAdapter()
