# Repo Map

## Purpose

This repo is a local-first Document Intelligence plus Applied AI learning system.

Core product loop:

`upload document -> parse -> preprocess -> route -> chunk -> enrich -> extract / summarise / classify / match / chronology -> review -> evaluate`

The system is intentionally synchronous and mostly in-memory, but the codebase already includes retrieval, evaluation, HITL, safe-failure, and productionization scaffolding.

## Top-Level Layout

| Path | Role |
| --- | --- |
| `apps/py-api` | FastAPI backend entrypoint and HTTP API |
| `apps/web` | Next.js frontend for upload, inspection, retrieval comparison, and review |
| `py/libs/data_model` | Shared Pydantic domain contracts |
| `py/libs/di_core` | Document Intelligence pipeline logic |
| `py/libs/ai_core` | Applied AI logic: prompts, adapter, validation, grounding, tasks |
| `py/libs/di_eval` | Evaluation and experiment tooling |
| `py/libs/storage` | Storage abstraction, currently local filesystem |
| `data/fixtures` | Sample documents and evaluation fixtures |
| `data/contracts` | Example API JSON contracts |
| `docs/architecture` | Architecture and scale notes |
| `docs/applied-ai` | Baseline walkthrough notes |
| `tests/smoke` | End-to-end and phase-oriented smoke tests |
| `tests/eval` | Evaluation harness tests |
| `infra` | Dockerfiles and compose setup |
| `scripts` | Environment checks and setup helpers |

## Runtime Entry Points

### Backend

- `apps/py-api/py_api/main.py`
  - Creates the FastAPI app.
  - Registers CORS.
  - Mounts `health` and `documents` routers.
- `apps/py-api/py_api/api/documents.py`
  - Main application surface.
  - Holds in-memory stores for documents, extractions, reviewables, corrections, and feedback.
  - Orchestrates upload, extraction, summarisation, retrieval, review, and debugging endpoints.
- `apps/py-api/py_api/api/health.py`
  - Simple health endpoint.
  - AI ops snapshot endpoint for Phase 13 productionization.
- `apps/py-api/py_api/core/config.py`
  - Environment-driven settings for storage and LLM runtime.

### Frontend

- `apps/web/app/layout.tsx`
  - App shell and navigation.
- `apps/web/app/page.tsx`
  - Main document workbench.
  - Loads documents, document detail, extraction runs, and AI outputs.
- `apps/web/app/review/page.tsx`
  - HITL review queue workflow.
- `apps/web/lib/api.ts`
  - Frontend API client layer.
- `apps/web/lib/types.ts`
  - TypeScript mirrors of backend response contracts.

## Core Backend Flow

### 1. Upload and Ingest

- `apps/web/components/upload-panel.tsx`
  - Uploads `.pdf`, `.txt`, `.md`, `.text`.
- `apps/web/lib/api.ts -> uploadDocument()`
  - Calls `POST /documents/upload`.
- `apps/py-api/py_api/api/documents.py -> upload_document()`
  - Reads bytes from `UploadFile`.
  - Saves file via `storage.LocalStorage`.
  - Creates a `Document`.
  - Runs parse, preprocess, route, chunk, size classify, and enrich.
  - Stores the finished `Document` in `_documents`.

### 2. Parse and Preprocess

- `py/libs/di_core/src/di_core/parser.py`
  - Parses native-text PDFs with PyMuPDF.
  - Parses text and markdown as one-page text documents.
  - Detects scanned / low-density PDFs.
  - Attempts OCR through an adapter boundary.
  - Produces `ParseMeta`.
- `py/libs/di_core/src/di_core/preprocessor.py`
  - Cleans unicode, whitespace, control chars, headers/footers, and duplicate lines.
  - Produces `PreprocessMeta`.

### 3. Routing, Chunking, Enrichment

- `py/libs/di_core/src/di_core/router.py`
  - Heuristic filename plus content routing to `DocumentType`.
- `py/libs/di_core/src/di_core/chunker.py`
  - Deterministic chunking with provenance.
  - Supports fixed-size, paragraph, and page-bounded strategies.
  - Produces `ChunkMeta`.
- `py/libs/di_core/src/di_core/size_guard.py`
  - Classifies document size and summarisation recommendations.
- `py/libs/di_core/src/di_core/enrichment.py`
  - Enriches chunks with doc type, source file, parse quality, and section labels.
- `py/libs/di_core/src/di_core/section_detector.py`
  - Heuristic section labeling.

### 4. Deterministic Extraction

- `apps/py-api/py_api/api/documents.py -> extract()`
  - Calls deterministic extraction and postprocessing.
- `py/libs/di_core/src/di_core/extractor.py`
  - Regex and keyword-window field extraction.
  - Returns `ExtractionResult` with `OutputType.DETERMINISTIC`.
- `py/libs/di_core/src/di_core/postprocessor.py`
  - Normalizes dates, amounts, confidence ranges, and evidence lists.

### 5. Applied AI Tasks

- `apps/py-api/py_api/api/documents.py -> summarise()`
  - Grounded summary endpoint.
- `py/libs/ai_core/src/ai_core/summariser.py`
  - Selects chunks.
  - Builds prompts.
  - Calls LLM adapter.
  - Validates output.
  - Audits grounding.
  - Packages evidence and uncertainty metadata.
- `apps/py-api/py_api/api/documents.py -> chronology()`
  - Timeline extraction endpoint.
- `py/libs/ai_core/src/ai_core/chronology.py`
  - Second AI task, parallel to summarisation.
- `apps/py-api/py_api/api/documents.py -> hierarchical_summarise_endpoint()`
  - Long-document hierarchical summarisation endpoint.
- `py/libs/ai_core/src/ai_core/hierarchical.py`
  - Chunk-level fact extraction.
  - Section-level aggregation.
  - Single synthesis call for document summary.
- `apps/py-api/py_api/api/documents.py -> classify()` and `semantic_match()`
  - Explainable readiness classification and evidence alignment.
- `py/libs/di_core/src/di_core/semantic.py`
  - Non-generative classification and semantic matching.

### 6. Retrieval and Search

- `apps/py-api/py_api/api/documents.py -> search_chunks()`
  - Salience or lexical ranking.
- `apps/py-api/py_api/api/documents.py -> retrieval_compare()`
  - Side-by-side retrieval strategy comparison.
- `py/libs/di_core/src/di_core/chunk_selector.py`
  - Head, tail, head-tail, sampled, routing-aware, query-ranked, diversified.
- `py/libs/di_core/src/di_core/ranker.py`
  - Salience, lexical, and embedding-aware ranking abstractions.
- `py/libs/di_core/src/di_core/retrieval_compare.py`
  - Comparison report and recommendation generation.
- `py/libs/di_core/src/di_core/reranker.py`
  - Hybrid retrieval and RRF fusion.
- `py/libs/di_core/src/di_core/vector_index.py`
  - In-memory vector search.
- `py/libs/ai_core/src/ai_core/embedding.py`
  - Embedding provider boundary and deterministic hash embeddings.

### 7. Review and Feedback

- `apps/py-api/py_api/api/documents.py`
  - Review queue, review status, correction submission, correction listing, feedback signals.
- `py/libs/di_core/src/di_core/review_queue.py`
  - Review triggers, priority scoring, auto-accept, and feedback signal generation.
- `py/libs/data_model/src/data_model/review.py`
  - Reviewable output, review decisions, corrections, and feedback contracts.
- `apps/web/app/review/page.tsx`
  - Review queue screen.
- `apps/web/components/review-queue.tsx`
  - Queue list and priority visualization.
- `apps/web/components/review-panel.tsx`
  - Approve, reject, correct, and inspect evidence.

### 8. Evaluation and Experimentation

- `py/libs/di_eval/src/di_eval/runner.py`
  - API-first fixture evaluation runner.
- `py/libs/di_eval/src/di_eval/field_eval.py`
  - Deterministic field evaluation.
- `py/libs/di_eval/src/di_eval/summary_eval.py`
  - Multi-dimensional summary evaluation.
- `py/libs/di_eval/src/di_eval/retrieval_eval.py`
  - Retrieval quality scoring.
- `py/libs/di_eval/src/di_eval/slice_eval.py`
  - Slice-based breakdowns.
- `py/libs/di_eval/src/di_eval/experiment.py`
  - Prompt/model/retrieval experiment comparison.
- `py/libs/di_eval/src/di_eval/system_metrics.py`
  - Pipeline latency and routing/extraction health metrics.

## Shared Contracts

### Document Contracts

- `py/libs/data_model/src/data_model/document.py`
  - `Document`
  - `DocumentPage`
  - `DocumentChunk`
  - `ParseMeta`
  - `RoutingResult`
  - `ChunkMeta`
  - `DocumentSizeCategory`
  - `SectionLabel`

### Extraction and AI Contracts

- `py/libs/data_model/src/data_model/extraction.py`
  - `ExtractionResult`
  - `StructuredField`
  - `EvidenceReference`
  - `SummaryResult`
  - `ChronologyResult`
  - `ClassificationResult`
  - `SemanticMatchResult`
  - `GroundingAudit`
  - `SummarisationMeta`
  - `ExperimentMeta`
  - `UncertaintyAssessment`

### Pipeline and Review Contracts

- `py/libs/data_model/src/data_model/pipeline.py`
  - `PipelineStage`
  - `FailureKind`
  - `StageOutcome`
  - `PipelineTrace`
- `py/libs/data_model/src/data_model/review.py`
  - `ReviewableOutput`
  - `ReviewDecision`
  - `CorrectionRecord`
  - `FeedbackSignal`

## Frontend Screen Map

### Upload / Document Workbench

- `apps/web/app/page.tsx`
  - Sidebar of uploaded documents.
  - Upload panel.
  - Parsed document viewer.
  - Extraction status cards.
  - Deterministic extraction trigger.
  - Grounded summary trigger.
  - Hierarchical summary trigger.
  - Timeline trigger.
  - Readiness classification trigger.
  - Semantic matching trigger.
  - Retrieval comparison panel.

### Document Detail Components

- `apps/web/components/document-viewer.tsx`
  - Parse info, routing info, chunk info, chunk explorer.
- `apps/web/components/extraction-result.tsx`
  - Summary, grounding, evidence, coverage, structured fields, classification, chronology, semantic match.
- `apps/web/components/retrieval-compare.tsx`
  - Strategy comparison UI.

### Review UI

- `apps/web/app/review/page.tsx`
  - Queue page container.
- `apps/web/components/review-queue.tsx`
  - Pending and resolved items.
- `apps/web/components/review-panel.tsx`
  - Review action surface and evidence inspection.

## Tests Map

### Smoke / Phase-Oriented Backend Tests

- `tests/smoke/test_upload.py`
  - Upload, parsing, and document creation.
- `tests/smoke/test_chunking.py`
  - Chunking strategies and provenance.
- `tests/smoke/test_routing.py`
  - Document routing.
- `tests/smoke/test_extraction.py`
  - Deterministic extraction.
- `tests/smoke/test_ocr_awareness.py`
  - OCR-aware parser behavior.
- `tests/smoke/test_large_document.py`
  - Size guard and large-document handling.
- `tests/smoke/test_retrieval.py` and `tests/smoke/test_retrieval_phase5.py`
  - Retrieval ranking and comparison.
- `tests/smoke/test_evidence_grounding.py` and `tests/smoke/test_grounding_phase3.py`
  - Grounding and evidence-backed outputs.
- `tests/smoke/test_preprocessing.py`
  - Pre/postprocessing related behavior.
- `tests/smoke/test_hitl.py`
  - Review queue and correction workflows.
- `tests/smoke/test_prompt_templates.py`
  - Prompt registry and prompt contracts.
- `tests/smoke/test_output_validation.py`
  - Structured output validation.
- `tests/smoke/test_task_expansion_phase4.py`
  - Chronology and task abstraction.
- `tests/smoke/test_embeddings_phase6.py`
  - Embeddings and vector retrieval.
- `tests/smoke/test_long_context_phase7.py`
  - Long-document AI strategy and hierarchical summarisation.
- `tests/smoke/test_phase8_classification_matching.py`
  - Readiness classification and semantic matching.
- `tests/smoke/test_prompt_experiments_phase10.py`
  - Prompt experiments and registry usage.
- `tests/smoke/test_safe_failure_phase11.py`
  - Uncertainty and safe-failure behavior.
- `tests/smoke/test_phase13_productionization.py`
  - AI ops visibility and degraded-mode behavior.

### Evaluation Tests

- `tests/eval/test_field_eval.py`
- `tests/eval/test_retrieval_eval.py`
- `tests/eval/test_evaluation_run.py`

## Data and Fixtures

- `data/fixtures`
  - Mixed PDFs, markdown, plain text, scanned examples, and reference documents.
- `data/fixtures/ground_truth.json`
  - Ground truth for evaluation runs.
- `data/contracts`
  - Example JSON outputs for upload and extraction.

## Infra and Tooling

- `infra/compose/docker-compose.yml`
  - Postgres, Redis, and app containers for local dev shape.
- `infra/docker/py-api.Dockerfile`
  - Backend container.
- `infra/docker/web.Dockerfile`
  - Frontend container.
- `scripts/dev/check-env.sh`
  - Environment sanity check.
- `package.json`
  - Repo-level commands like `pnpm run check`.
- `pyproject.toml`
  - Python workspace and pytest settings.
- `pnpm-workspace.yaml`
  - Node workspace definition.
- `uv.lock` and `pnpm-lock.yaml`
  - Locked dependencies.

## Important Docs

- `docs/architecture/DI_AAI_Map.md`
  - This repo-wide map. Start here if you want the full shape before drilling into DI or AI specifics.
- `README.md`
  - Current repo overview and run instructions.
- `docs/architecture/DI_Map.md`
  - Baseline AI walkthrough from UI action to API orchestration, chunk selection, prompt execution, and grounded result rendering.
- `docs/architecture/SCALING_ROADMAP.md`
  - Scaling path from the current local MVP to workers, queues, and durable storage.
- `docs/applied-ai/AI_Scale.md`
  - Applied AI productionization note.
- `docs/architecture/FINAL_ARCHITECTURE.md`
  - North-star architecture note.

## Current State Management

- Documents are stored in `_documents` in `apps/py-api/py_api/api/documents.py`.
- Extractions are stored in `_extractions`.
- Review queue state is stored in `_reviewables`.
- Corrections are stored in `_corrections`.
- Feedback signals are stored in `_feedback`.
- Uploaded raw files are written to local `uploads/`.

This means:

- Process restart clears operational state except raw files.
- No persistence layer exists yet for documents, extractions, or reviews.
- This is intentional for the learning MVP, but it is the main production gap.

## Notable Inactive or Placeholder Areas

- `packages/shared-types/`
  - Directory exists but currently has no source files.
- `apps/py-api/py_api/models/`
  - Present but unused in the current architecture.
- `apps/py-api/py_api/services/`
  - Present but unused in the current architecture.
- `tests/e2e/`
  - Present but currently empty.

## Mental Model For Reading The Repo

If you want to understand the repo quickly, read in this order:

1. `README.md`
2. `apps/py-api/py_api/api/documents.py`
3. `py/libs/data_model/src/data_model/document.py`
4. `py/libs/data_model/src/data_model/extraction.py`
5. `py/libs/di_core/src/di_core/parser.py`
6. `py/libs/di_core/src/di_core/chunker.py`
7. `py/libs/di_core/src/di_core/extractor.py`
8. `py/libs/ai_core/src/ai_core/summariser.py`
9. `apps/web/app/page.tsx`
10. `apps/web/components/extraction-result.tsx`
11. `py/libs/di_core/src/di_core/review_queue.py`
12. `apps/web/app/review/page.tsx`

## Short Repo Summary

This repo is best thought of as five layers:

- API orchestration: `apps/py-api`
- Product UI: `apps/web`
- Shared contracts: `py/libs/data_model`
- DI and AI engines: `py/libs/di_core` plus `py/libs/ai_core`
- Evaluation and architecture thinking: `py/libs/di_eval` plus `docs/architecture`

That split is clean enough that you can describe the system as:

`HTTP/API layer -> domain contracts -> deterministic DI pipeline -> AI pipeline -> review/eval loops`
