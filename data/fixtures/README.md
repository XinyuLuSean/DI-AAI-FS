# Fixture Layout

`data/fixtures/` is organized so the top level stays focused on the primary
document-intelligence evaluation corpus.

Top level:
- Category A DI fixtures used by the main pipeline and Phase 9 evaluation
- `ground_truth.json` for expected routing, extraction, and summary slices

Subdirectories:
- `reference/` non-DI study/reference material that should not be included in
  DI evaluation runs
- `scanned/` OCR-awareness and unsupported image fixtures
- `edge_cases/` explicit failure-path fixtures such as empty or unsupported files
- `pdf-ready/` source artifacts associated with PDF-derived evaluation content

When building evaluation harnesses, prefer globbing the top level for the main
evaluation set and opt into `scanned/` or `edge_cases/` only when those slices
are being measured explicitly.
