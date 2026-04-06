# Document Intelligence Phases

This file maps the Document Intelligence curriculum in `docs/document-intelligence/DocumentIntelligence.md` to the current codebase.

The framing here is intentionally code-first:

- "Goal" and "Why Matters" are adapted from the phase intent.
- "Implementations at codebase" points to where the repo currently realizes that phase.
- "How to Evaluate" focuses on practical verification in this repo.

Use this together with `docs/architecture/DI_AAI_Map.md` for the repo-wide systems view and `docs/interview-reference/DI_Scale.md` for the production-scale thought exercise.

## Phase 0 - Baseline Walkthrough And System Trace

### Goal

Understand the full DI path from upload to parsed document, chunked context, extraction or AI result, and UI rendering.

### Why Matters

This is the foundation for every later phase. In interviews, being able to trace the live system quickly is often more important than adding new features.

### Implementations at codebase

- `apps/py-api/py_api/api/documents.py` orchestrates upload, parse, preprocess, route, chunk, enrich, extract, summarise, search, and review.
- `py/libs/di_core/src/di_core/parser.py` creates `DocumentPage` records and `ParseMeta`.
- `py/libs/di_core/src/di_core/chunker.py` creates `DocumentChunk` records and `ChunkMeta`.
- `py/libs/ai_core/src/ai_core/summariser.py` runs the first AI task on selected chunks and packages evidence-backed output.
- `apps/web/app/page.tsx` is the main end-user workflow for upload, inspection, extraction, and AI outputs.
- `apps/web/components/document-viewer.tsx` and `apps/web/components/extraction-result.tsx` expose the parse, routing, chunk, and evidence details.

### How to Evaluate

- Run `pnpm run check`.
- Run the backend and frontend locally, upload `data/fixtures/sample.txt`, and follow upload -> extract -> summarise.
- Inspect `GET /documents/{id}` to confirm page and chunk provenance.
- Relevant tests: `tests/smoke/test_health.py`, `tests/smoke/test_upload.py`.

### Exit Criteria

- You can explain where bytes enter the system, where files are stored, where pages and chunks are created, and where evidence is attached.
- You can name the synchronous boundaries and the in-memory state boundaries.

### Interview Reflections

- Why is a synchronous, local-first MVP still a valid first slice?
- Why is provenance worth preserving before any ML sophistication exists?
- Which stage would you move to a worker first, and why?

## Phase 1 - Parser Deep Dive: File Types, Failure Modes, Provenance

### Goal

Turn parsing into an explicit, quality-aware stage that reports what happened and fails honestly.

### Why Matters

Document Intelligence quality starts with input quality. Most downstream AI problems are really parse-quality or unsupported-format problems wearing a different label.

### Implementations at codebase

- `py/libs/di_core/src/di_core/parser.py` supports PDF native text plus `.txt`, `.md`, `.text`.
- `py/libs/data_model/src/data_model/document.py` defines `ParseMeta`, `ParseFailureReason`, and `ParseQuality`.
- `parser.py` classifies unsupported file type, file missing, empty extraction, unreadable PDF, and zero-text PDF.
- `parser.py` also tracks parse strategy, file suffix, page count, empty page count, total chars, text density, OCR flags, and downstream limitations.
- `apps/py-api/py_api/api/documents.py` logs parse details and returns `422` for hard failures.

### How to Evaluate

- Upload valid text, valid PDF, empty fixture, and unsupported fixture from `data/fixtures/edge_cases`.
- Inspect `document.parse_meta` in the upload response.
- Relevant tests: `tests/smoke/test_upload.py`, `tests/smoke/test_ocr_awareness.py`.

### Exit Criteria

- Parse failures are classifiable rather than generic.
- Parse metadata is visible to downstream stages and the UI.
- Unsupported or unreadable documents fail loudly instead of silently degrading.

### Interview Reflections

- Why separate "degraded but usable" from "hard failure"?
- Why is zero-text PDF not always the same as unreadable PDF?
- How does parse metadata improve debugging speed later in the pipeline?

## Phase 2 - Chunking Deep Dive: Deterministic Baseline And Better Strategies

### Goal

Build deterministic chunking that preserves provenance and exposes its own behavior clearly.

### Why Matters

Chunking is the bridge between raw document structure and every downstream retrieval or AI task. Weak chunking silently poisons both extraction and summarisation.

### Implementations at codebase

- `py/libs/di_core/src/di_core/chunker.py` implements `fixed_size`, `paragraph`, and `page_bounded`.
- `py/libs/data_model/src/data_model/document.py` defines `ChunkStrategy`, `DocumentChunk`, and `ChunkMeta`.
- `chunker.py` preserves `page_numbers`, `char_start`, `char_end`, token estimates, and truncation flags.
- `apps/py-api/py_api/api/documents.py` accepts chunking params at upload time and logs chunking metadata.
- `apps/web/components/document-viewer.tsx` exposes chunk strategy, chunk count, coverage, truncation, and chunk previews.

### How to Evaluate

- Upload the same fixture using different chunk strategies.
- Inspect `/documents/{id}/chunks/debug`.
- Relevant tests: `tests/smoke/test_chunking.py`.

### Exit Criteria

- Multiple chunking strategies exist and are selectable.
- Every chunk carries enough provenance for citation and debugging.
- Chunking behavior is inspectable via metadata rather than opaque.

### Interview Reflections

- Why keep a deterministic baseline even if later AI stages are probabilistic?
- When would page-bounded chunking beat fixed-size chunking?
- Why is chunk provenance critical for trust?

## Phase 3 - Document Typing And Routing

### Goal

Add explainable document-type routing so later stages can adapt behavior by document class.

### Why Matters

Different document types have different useful signals. Routing is the first step toward adaptive processing without prematurely introducing ML.

### Implementations at codebase

- `py/libs/di_core/src/di_core/router.py` performs filename and content-based heuristic routing.
- `py/libs/data_model/src/data_model/document.py` defines `DocumentType`, `RoutingRule`, and `RoutingResult`.
- `apps/py-api/py_api/api/documents.py` runs routing after preprocessing and logs confidence, matched rules, and fallback state.
- `apps/web/components/document-viewer.tsx` shows routed type, confidence, matched rules, and routing warnings.
- Routing also feeds later retrieval behavior through `chunk_selector.py`.

### How to Evaluate

- Upload fixtures with different naming and content styles from `data/fixtures`.
- Check `document.routing` in API responses and UI.
- Relevant tests: `tests/smoke/test_routing.py`.

### Exit Criteria

- Routing is explainable, inspectable, and stored with the document.
- Later stages can consume routing output without rereading the raw document.

### Interview Reflections

- Why is heuristic routing a strong MVP choice?
- What business value comes from early document typing?
- What would make you replace or augment routing with ML later?

## Phase 4 - Deterministic Extraction Track

### Goal

Separate exact field extraction from open-ended AI generation.

### Why Matters

Interviews often probe whether you can distinguish high-precision extraction work from generative summarisation. This repo does that cleanly.

### Implementations at codebase

- `py/libs/di_core/src/di_core/extractor.py` extracts fields via regex and keyword-window heuristics.
- `py/libs/data_model/src/data_model/extraction.py` defines `StructuredField`, `ExtractionMethod`, and `ExtractionResult`.
- `apps/py-api/py_api/api/documents.py -> extract()` exposes deterministic extraction as its own endpoint.
- `py/libs/di_core/src/di_core/postprocessor.py` normalizes extracted values and deduplicates evidence.
- `apps/web/components/extraction-result.tsx` renders deterministic fields separately from AI outputs.

### How to Evaluate

- Run deterministic extraction on billing, legal, and medical fixtures.
- Inspect field names, confidence, evidence, and normalized values.
- Relevant tests: `tests/smoke/test_extraction.py`.

### Exit Criteria

- Deterministic extraction is a first-class path with its own output type.
- Each extracted field carries source snippet and evidence.
- Extraction can be evaluated independently of narrative quality.

### Interview Reflections

- Why should deterministic extraction and AI summarisation not share one metric?
- Why is conservative "not found" behavior often better than guessing?
- Which fields are best kept deterministic longest?

## Phase 5 - OCR-Ready Design Without Full OCR Explosion

### Goal

Make the system OCR-aware without prematurely building a full OCR stack.

### Why Matters

Real document systems always hit scanned or image-heavy inputs. The key question is whether the system degrades honestly and keeps a clean OCR boundary.

### Implementations at codebase

- `py/libs/di_core/src/di_core/ocr.py` defines the OCR adapter interface plus `TesseractAdapter`, `TextractAdapter`, and `NoOpAdapter`.
- `py/libs/di_core/src/di_core/parser.py` detects low-density and scanned PDFs, attempts OCR fallback through the adapter, and records OCR metadata.
- `py/libs/data_model/src/data_model/document.py` stores OCR-applied and likely-needs-OCR flags in `ParseMeta`.
- `apps/web/components/document-viewer.tsx` surfaces likely-scanned, OCR-needed, and OCR-applied badges.

### How to Evaluate

- Use fixtures under `data/fixtures/scanned`.
- Verify that zero-text PDFs are labeled honestly and not silently treated as successful text parses.
- Relevant tests: `tests/smoke/test_ocr_awareness.py`.

### Exit Criteria

- OCR is behind an interface rather than embedded in parser control flow.
- The repo can signal OCR need even when no real OCR backend is active.

### Interview Reflections

- Why is an OCR boundary valuable before production OCR exists?
- What are the risks of pretending scanned PDFs parsed well?
- How would you roll out OCR safely in production?

## Phase 6 - Large Document Handling

### Goal

Recognize and adapt to document size so the system stays honest about partial processing.

### Why Matters

Large documents are where naive synchronous DI breaks down first. Even before workerization, the system should disclose its limits.

### Implementations at codebase

- `py/libs/di_core/src/di_core/size_guard.py` classifies `small`, `medium`, `large`, and `oversized`.
- `apps/py-api/py_api/api/documents.py` stores `size_category` during upload.
- `py/libs/di_core/src/di_core/chunk_selector.py` uses chunk budgets for LLM tasks.
- `apps/py-api/py_api/api/documents.py -> debug_chunks()` exposes size guard state and summarisation readiness.
- `apps/web/components/document-viewer.tsx` surfaces chunk coverage and truncation.

### How to Evaluate

- Upload long fixtures and inspect `size_category`, `recommended_max_llm_chunks`, and warnings.
- Compare standard summarisation versus hierarchical summarisation on larger documents.
- Relevant tests: `tests/smoke/test_large_document.py`.

### Exit Criteria

- Large-document behavior is explicit, not hidden.
- The system warns when AI coverage will only be partial.

### Interview Reflections

- Why is size classification useful even before async workers exist?
- What product risks come from silent truncation?
- How should UX communicate partial coverage to users?

## Phase 7 - Retrieval-Oriented Document Intelligence

### Goal

Make chunks retrieval-ready and add inspection tools for ranking and chunk selection.

### Why Matters

Retrieval quality is one of the biggest leverage points in both DI and Applied AI. This phase turns chunks into usable retrieval objects instead of plain text slices.

### Implementations at codebase

- `py/libs/di_core/src/di_core/enrichment.py` populates doc type, source filename, parse quality, and section label on chunks.
- `py/libs/di_core/src/di_core/section_detector.py` provides structural section labels.
- `py/libs/di_core/src/di_core/ranker.py` implements lexical and salience ranking.
- `py/libs/di_core/src/di_core/evidence.py` turns chunks into citation-ready `EvidenceReference` objects.
- `py/libs/di_core/src/di_core/retrieval_compare.py` compares selection strategies side by side.
- `apps/py-api/py_api/api/documents.py` exposes `/search` and `/retrieval-compare`.
- `apps/web/components/retrieval-compare.tsx` renders retrieval comparisons in the UI.

### How to Evaluate

- Run retrieval compare against multiple queries and inspect overlap and recommendation text.
- Verify chunk section labels and evidence metadata in the UI.
- Relevant tests: `tests/smoke/test_retrieval.py`, `tests/smoke/test_retrieval_phase5.py`.

### Exit Criteria

- Chunks carry retrieval-oriented metadata.
- Retrieval strategies can be compared and debugged without guessing.

### Interview Reflections

- Why is section awareness useful even with heuristic labels?
- Why separate ranking from chunking?
- How would you judge whether retrieval is helping downstream quality?

## Phase 8 - Evidence-Backed Summaries And Traceability

### Goal

Ensure AI outputs are grounded in evidence and traceable back to concrete chunks.

### Why Matters

Trust is the central DI theme here. Evidence-backed summaries are much easier to debug, review, and defend than free-form narrative.

### Implementations at codebase

- `py/libs/ai_core/src/ai_core/summariser.py` packages summary evidence, grounded key points, coverage meta, and uncertainty.
- `py/libs/ai_core/src/ai_core/grounding.py` audits grounding quality and builds evidence gap analysis.
- `py/libs/di_core/src/di_core/evidence.py` packages evidence from chunk IDs.
- `py/libs/di_core/src/di_core/coverage.py` quantifies coverage and generates prompt disclosure text.
- `py/libs/data_model/src/data_model/extraction.py` defines `GroundedKeyPoint`, `GroundingAudit`, `SummarisationMeta`, and evidence-bearing `SummaryResult`.
- `apps/web/components/extraction-result.tsx` renders grounding audit, evidence gap, coverage report, and evidence list.

### How to Evaluate

- Run grounded summary on a fixture with deterministic extraction first.
- Inspect grounding score, grounded key points, evidence usage, and warnings.
- Relevant tests: `tests/smoke/test_evidence_grounding.py`, `tests/smoke/test_grounding_phase3.py`.

### Exit Criteria

- Summary claims can be traced to chunk IDs.
- Weak or hallucinated evidence paths are surfaced, not hidden.

### Interview Reflections

- Why is per-claim evidence better than only a global citation list?
- What does a grounding score tell you, and what does it not tell you?
- How would reviewers use evidence-gap analysis in practice?

## Phase 9 - Evaluation For Document Intelligence

### Goal

Measure DI quality with fixture-based evaluation instead of intuition.

### Why Matters

This is where the repo moves from feature-building to disciplined quality measurement. Interviewers often care more about honest evaluation than about raw feature count.

### Implementations at codebase

- `py/libs/di_eval/src/di_eval/field_eval.py` scores extracted fields.
- `py/libs/di_eval/src/di_eval/summary_eval.py` scores summary dimensions.
- `py/libs/di_eval/src/di_eval/retrieval_eval.py` evaluates retrieval quality.
- `py/libs/di_eval/src/di_eval/slice_eval.py` computes slice-level breakdowns.
- `py/libs/di_eval/src/di_eval/runner.py` runs evaluation through the real API.
- `data/fixtures/ground_truth.json` defines expected fixture behavior.

### How to Evaluate

- Run the evaluation runner against the fixture set.
- Inspect field precision/recall/F1, summary coverage, retrieval lift, and slice breakdowns.
- Relevant tests: `tests/eval/test_field_eval.py`, `tests/eval/test_retrieval_eval.py`, `tests/eval/test_evaluation_run.py`.

### Exit Criteria

- There is a repeatable way to score DI outputs against fixtures.
- Output quality is reported by dimension rather than by a single vague score.

### Interview Reflections

- Why is one metric not enough for document systems?
- Why should retrieval and generation be evaluated separately?
- How do slice breakdowns change debugging priorities?

## Phase 10 - Preprocessing And Postprocessing For Production Thinking

### Goal

Add production-oriented cleanup and normalization around core extraction and parsing.

### Why Matters

Many practical accuracy gains come from text cleanup and value normalization, not from bigger models. This phase is about reducing preventable noise.

### Implementations at codebase

- `py/libs/di_core/src/di_core/preprocessor.py` removes control chars, normalizes whitespace, strips repeated headers/footers, and suppresses duplicate lines.
- `py/libs/di_core/src/di_core/postprocessor.py` normalizes dates and currency, clamps confidence, and deduplicates evidence.
- `py/libs/data_model/src/data_model/pipeline.py` defines pipeline stages and failure taxonomy.
- `py/libs/di_core/src/di_core/pipeline_trace.py` records stage timings and logs pipeline summaries.
- `apps/py-api/py_api/api/documents.py` stores `preprocess_meta` and `pipeline_trace` on the `Document`.

### How to Evaluate

- Upload messy markdown or PDF fixtures and compare raw parse versus post-cleanup behavior.
- Inspect `document.preprocess_meta` and `document.pipeline_trace`.
- Relevant tests: `tests/smoke/test_preprocessing.py`.

### Exit Criteria

- Noise removal and value normalization are explicit, inspectable stages.
- The pipeline exposes stage timing and failure semantics.

### Interview Reflections

- Why is preprocessing often more cost-effective than changing the model?
- Why should postprocessing standardize but never invent values?
- How does pipeline tracing change operational debugging?

## Phase 11 - Human-In-The-Loop For Document Intelligence

### Goal

Add structured review, correction, and feedback loops to the DI workflow.

### Why Matters

Real document systems rarely stop at automated output. HITL is where trust, risk control, and future learning loops meet.

### Implementations at codebase

- `py/libs/data_model/src/data_model/review.py` defines review status, corrections, complaints, and feedback records.
- `py/libs/di_core/src/di_core/review_queue.py` computes triggers, priorities, auto-accept rules, and feedback signals.
- `apps/py-api/py_api/api/documents.py` exposes review and correction endpoints plus review queue listing.
- `apps/web/app/review/page.tsx`, `apps/web/components/review-queue.tsx`, and `apps/web/components/review-panel.tsx` implement the review UI.

### How to Evaluate

- Run extraction or summary, open the review queue, approve/reject/correct outputs, and inspect generated feedback signals.
- Relevant tests: `tests/smoke/test_hitl.py`.

### Exit Criteria

- Outputs can be reviewed and corrected without mutating originals invisibly.
- Review triggers and priority are inspectable.
- Corrections generate structured feedback signals for future improvements.

### Interview Reflections

- Why should review state be explicit rather than implied?
- Why preserve original values instead of overwriting them?
- Which corrections should feed heuristics, prompts, or evaluation fixtures?

## Phase 12 - Scale Thought Exercise: 100k MAU / Millions Of Pages

### Goal

Reason about how the current synchronous MVP would evolve under production scale.

### Why Matters

This phase checks architectural judgment. The repo should make it possible to explain what breaks first and how to evolve the system safely.

### Implementations at codebase

- `docs/interview-reference/DI_Scale.md` is the main DI scale thought exercise.
- `py/libs/data_model/src/data_model/pipeline.py` gives explicit failure and retry semantics that would support workerized execution.
- `py/libs/storage/src/storage/local.py` already keeps storage behind an adapter boundary.
- `apps/py-api/py_api/api/documents.py` makes current in-memory boundaries obvious, which helps identify what must become durable.

### How to Evaluate

- Read `docs/interview-reference/DI_Scale.md` alongside the current runtime code.
- Identify where in-memory state, synchronous AI calls, and local filesystem assumptions would fail first.

### Exit Criteria

- You can explain the current bottlenecks and a credible low-risk next evolution path.
- You can separate present implementation from future production architecture cleanly.

### Interview Reflections

- What are the first things that break at scale in this repo?
- Which parts are easy to evolve because boundaries are already clean?
- What would you keep synchronous longer, and why?
