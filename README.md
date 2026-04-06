# DI-AAI-FS — Document Intelligence + Applied AI + Full-Stack

A platform for document ingestion, structured extraction, evidence-backed AI analysis, and human-in-the-loop review.

**Current state:** Document Intelligence Phases 1–12 and Applied AI Phases 1–13 are implemented in the current local-first repo. The system is still intentionally synchronous and in-memory, but it now includes retrieval comparison, hierarchical summarisation, safe-failure handling, review workflows, and Phase 13 AI ops visibility. See `docs/architecture/FINAL_ARCHITECTURE.md` for the north-star production design, `docs/interview-reference/DI_Scale.md` for the DI scaling roadmap, and `docs/applied-ai/AI_Scale.md` for the Applied AI productionization note.

## Documentation Guide

- `docs/architecture/DI_AAI_Map.md` is the best repo-wide entry point if you want the full backend, frontend, data, and runtime map.
- `docs/document-intelligence/DocumentIntelligence.md` and `docs/document-intelligence/DocumentIntelligence_Phases.md` cover the DI learning path and how it maps onto this codebase.
- `AppliedAI.md` and `docs/applied-ai/AppliedAI_Phases.md` do the same for the Applied AI side.
- `docs/architecture/DI_Map.md` walks the current baseline AI path end to end.
- `docs/interview-reference/DI_Scale.md`, `docs/applied-ai/AI_Scale.md`, and `docs/interview-reference/InterviewInsights.md` are the fastest way to review scaling and interview framing.

## What This System Does

```
Upload file
  → Parse (PDF / TXT / MD)
  → Preprocess (unicode, whitespace, header/footer removal)
  → Route (document type classification)
  → Chunk (fixed-size / paragraph / page-bounded)
  → Size classify + enrich for retrieval
  → Deterministic field extraction (regex + keyword-window)
  → AI summarisation (LLM with evidence grounding)
  → Postprocess (date/currency normalisation, confidence clamping)
  → Auto-classify for human review (trigger reasons + priority)
  → Review queue with approve / reject / correct workflow
  → Feedback signal generation from corrections
```

Two UI views:

- **Upload page** — document list, upload, extract, summarise, view results with evidence and review status
- **Review Queue** — prioritised list of items needing human review, with field diff view and correction capabilities

---

## Repo Structure

```
DI-AAI-FS/
├── AppliedAI.md                # Phase-by-phase Applied AI deep-dive plan
├── README.md                   # ← you are here
├── .env.example                # Environment variable template
├── pyproject.toml              # Python workspace (uv)
├── package.json                # Node.js workspace (pnpm)
│
├── apps/
│   ├── py-api/                 # FastAPI backend
│   │   └── py_api/api/
│   │       └── documents.py    # All document endpoints (upload, extract, summarise, review, correct)
│   └── web/                    # Next.js frontend
│       ├── app/
│       │   ├── page.tsx        # Upload page with document list + detail view
│       │   ├── review/page.tsx # Review queue page
│       │   └── layout.tsx      # Root layout with navigation
│       ├── components/
│       │   ├── upload-panel.tsx
│       │   ├── document-viewer.tsx
│       │   ├── extraction-result.tsx
│       │   ├── review-queue.tsx
│       │   └── review-panel.tsx
│       └── lib/
│           ├── api.ts          # API client functions
│           └── types.ts        # TypeScript type mirrors of Pydantic models
│
├── py/libs/
│   ├── data_model/             # Pydantic schemas
│   │   └── src/data_model/
│   │       ├── document.py     # Document, Page, Chunk, Routing, ParseMeta
│   │       ├── extraction.py   # ExtractionResult, StructuredField, Evidence, Grounding
│   │       ├── pipeline.py     # PipelineTrace, StageOutcome, FailureKind
│   │       └── review.py       # ReviewableOutput, CorrectionRecord, FeedbackSignal
│   │
│   ├── di_core/                # Document intelligence core
│   │   └── src/di_core/
│   │       ├── parser.py       # PDF/TXT/MD parsing with failure classification
│   │       ├── preprocessor.py # Unicode, whitespace, header/footer cleanup
│   │       ├── router.py       # Heuristic document type classification
│   │       ├── chunker.py      # Fixed-size, paragraph, page-bounded chunking
│   │       ├── extractor.py    # Regex + keyword-window field extraction
│   │       ├── postprocessor.py# Date/currency normalisation, confidence clamping
│   │       ├── size_guard.py   # Document size classification
│   │       ├── chunk_selector.py # Budget-aware chunk selection for LLM
│   │       ├── enrichment.py   # Retrieval metadata enrichment
│   │       ├── section_detector.py # Section/heading detection
│   │       ├── ranker.py       # Lexical + salience chunk ranking
│   │       ├── evidence.py     # Evidence packaging from chunks
│   │       ├── ocr.py          # OCR adapter interface (Tesseract, Textract stubs)
│   │       ├── pipeline_trace.py # Per-stage timing and outcome tracking
│   │       └── review_queue.py # Review triggers, priority scoring, feedback generation
│   │
│   ├── ai_core/                # LLM adapter + prompt registry + summariser
│   │   └── src/ai_core/
│   │       ├── adapter.py      # Provider-agnostic LLM adapter (LiteLLM)
│   │       ├── prompts.py      # Prompt registry with templates
│   │       ├── summariser.py   # Evidence-backed summarisation pipeline
│   │       └── grounding.py    # Grounding audit (hallucination detection)
│   │
│   ├── di_eval/                # Evaluation framework
│   │   └── src/di_eval/
│   │       ├── field_scorer.py # Exact/normalised/tolerance field scoring
│   │       ├── summary_scorer.py # Multi-dimension summary evaluation
│   │       ├── slicer.py       # Slice-based breakdown by doc type, quality, etc.
│   │       └── runner.py       # Evaluation pipeline orchestrator
│   │
│   └── storage/                # Local filesystem adapter (→ S3 later)
│
├── infra/
│   ├── compose/                # Docker Compose (postgres, redis, py-api, web)
│   └── docker/                 # Dockerfiles
│
├── data/
│   ├── fixtures/               # Sample input files for testing
│   └── contracts/              # Example JSON request/response shapes
│
├── docs/
│   ├── applied-ai/
│   │   ├── AI_Scale.md
│   │   └── AppliedAI_Phases.md
│   ├── architecture/
│   │   ├── DI_AAI_Map.md
│   │   ├── DI_Map.md
│   │   └── FINAL_ARCHITECTURE.md
│   ├── document-intelligence/
│   │   ├── DocumentIntelligence.md
│   │   └── DocumentIntelligence_Phases.md
│   └── interview-reference/
│       ├── DI_Scale.md
│       ├── InterviewInfos.md
│       └── InterviewInsights.md
│
└── tests/
    ├── smoke/                  # smoke coverage for DI + Applied AI phases
    │   ├── test_health.py
    │   ├── test_upload.py
    │   ├── test_chunking.py
    │   ├── test_routing.py
    │   ├── test_extraction.py
    │   ├── test_ocr_awareness.py
    │   ├── test_large_document.py
    │   ├── test_retrieval.py
    │   ├── test_evidence_grounding.py
    │   ├── test_preprocessing.py
    │   └── test_hitl.py        # Review queue, corrections, feedback, list APIs
    └── eval/
        ├── test_field_eval.py
        └── test_evaluation_run.py
```

---

## Prerequisites


| Tool               | Required Version | Purpose                                            |
| ------------------ | ---------------- | -------------------------------------------------- |
| **Python**         | 3.12.x           | Backend runtime, document processing, AI pipelines |
| **uv**             | ≥ 0.9.16         | Fast Python package manager with workspace support |
| **Node.js**        | ≥ 18, < 25       | Frontend runtime (Next.js)                         |
| **pnpm**           | 10.x             | Node.js package manager with workspace support     |
| **Docker**         | modern stable    | Container runtime for Postgres, Redis              |
| **Docker Compose** | v2               | Multi-container orchestration                      |


Quick check: `zsh scripts/dev/check-env.sh`

---

## Getting Started

### 1. Clone and configure

```bash
git clone https://github.com/XinyuLuSean/DI-AAI-FS.git && cd DI-AAI-FS
cp .env.example .env
```

Edit `.env` and set your `OPENAI_API_KEY` (needed for AI summarisation).

### 2. Install dependencies

```bash
uv sync          # Python workspace
pnpm install     # Node.js workspace
```

### 3. Start infrastructure

```bash
docker compose -f infra/compose/docker-compose.yml up postgres redis -d
```

> **Note:** The MVP uses in-memory storage, so Postgres/Redis are not strictly required yet. They are included to match the final architecture.

### 4. Start the backend

```bash
uv run uvicorn py_api.main:app --reload --port 8000
```

Verify: `curl http://localhost:8000/health` → `{"status":"ok","service":"py-api","version":"0.1.0"}`

### 5. Start the frontend

```bash
pnpm dev:web
```

Open [http://localhost:3000](http://localhost:3000)

### 6. Test the flow

1. Upload a document (e.g. `data/fixtures/sample.txt` or any PDF)
2. View parsed document with chunks, routing, and size classification
3. Click **Extract** → see deterministic fields with confidence and evidence
4. Click **Summarise** → see AI-generated summary with grounding audit
5. Navigate to **Review Queue** → see items prioritised by review triggers
6. Approve, reject, or correct extracted fields with side-by-side diff

### 7. Run checks

```bash
pnpm run check
```

This runs the Python test suite plus the web typecheck/build flow. For backend-only verification, use `pnpm run test:py`.

---

## API Endpoints


| Method | Path                                        | Description                         |
| ------ | ------------------------------------------- | ----------------------------------- |
| GET    | `/health`                                   | Service health check                |
| POST   | `/documents/upload`                         | Upload and parse a file             |
| GET    | `/documents`                                | List all documents (lightweight)    |
| GET    | `/documents/{id}`                           | Get document with full detail       |
| GET    | `/documents/{id}/extractions`               | List extractions with review status |
| GET    | `/documents/{id}/extractions/{eid}`         | Get extraction result               |
| POST   | `/documents/{id}/extract`                   | Run deterministic field extraction  |
| POST   | `/documents/{id}/summarise`                 | Run AI summarisation with grounding |
| POST   | `/documents/{id}/search`                    | Search chunks with ranking          |
| GET    | `/documents/{id}/chunks/debug`              | Debug view of all chunks            |
| GET    | `/documents/review-queue`                   | Get review queue sorted by priority |
| POST   | `/documents/{id}/extractions/{eid}/review`  | Submit review decision              |
| GET    | `/documents/{id}/extractions/{eid}/review`  | Get review status                   |
| POST   | `/documents/{id}/extractions/{eid}/correct` | Submit field corrections            |


---

## Architecture Decisions


| Decision                                  | Rationale                                                                               |
| ----------------------------------------- | --------------------------------------------------------------------------------------- |
| **In-memory document store**              | Simplest path to a working demo. PostgreSQL is the next step (see `docs/interview-reference/DI_Scale.md`). |
| **Synchronous pipeline**                  | No worker queue yet. All stages run in the API process.                                 |
| **LiteLLM adapter**                       | Provider-agnostic LLM calls. Can swap OpenAI ↔ Anthropic ↔ local.                       |
| **Three chunking strategies**             | Fixed-size (baseline), paragraph-aware, page-bounded — configurable per request.        |
| **Separate extraction and summarisation** | Deterministic fields evaluated on precision/recall; summaries on coverage/grounding.    |
| **Heuristic routing**                     | Filename + content keyword heuristics. ML classification is a future upgrade.           |
| **OCR as adapter stub**                   | Interface exists; Tesseract/Textract can be wired without changing pipeline.            |
| **HITL as first-class**                   | Review triggers, priority scoring, and correction capture built into the pipeline.      |
| **Local file storage**                    | Filesystem adapter with the same interface S3 will use.                                 |
| **No auth**                               | MVP is local-only. Auth is a future concern.                                            |


---

## Key Design Patterns

**Pure pipeline functions** — Every stage (`parse_document`, `chunk_text`, `extract_fields`, etc.) is a pure function that takes a `Document` and returns a result. No HTTP awareness, no state mutation. This makes workerization straightforward.

**Evidence traceability** — Every extracted field and summary claim links to source chunk IDs, page numbers, and supporting snippets. The chain `Document → Chunks → Extraction → Evidence → Review → Correction → Feedback` is fully navigable.

**Failure classification** — Pipeline outcomes are categorised as HARD / SOFT / RETRYABLE / REVIEW_NEEDED via `StageOutcome` and `FailureKind`. This maps directly to retry policy and HITL routing.

**Review triggers** — After every extraction, `create_reviewable_output()` auto-classifies whether human review is needed based on: low confidence fields, weak grounding, hallucinated chunk IDs, degraded parse quality, and more.

---

## What Comes Next

Following the build order from `docs/architecture/FINAL_ARCHITECTURE.md`:

1. ~~Repo bootstrap and environment sanity~~ ✓
2. ~~Minimal FastAPI service~~ ✓
3. ~~Minimal Next.js UI~~ ✓
4. ~~Upload + parse endpoint~~ ✓
5. ~~Chunking and structured response~~ ✓
6. ~~AI summarisation with strict JSON output~~ ✓
7. ~~Evidence display in UI~~ ✓
8. ~~Local Docker Compose~~ ✓
9. ~~Smoke tests and eval coverage~~ ✓
10. ~~Document routing and type classification~~ ✓
11. ~~Deterministic field extraction~~ ✓
12. ~~OCR-ready design~~ ✓
13. ~~Large document handling~~ ✓
14. ~~Retrieval-oriented DI~~ ✓
15. ~~Evidence-backed summaries with grounding audit~~ ✓
16. ~~Evaluation framework~~ ✓
17. ~~Preprocessing and postprocessing~~ ✓
18. ~~HITL review queue with UI~~ ✓
19. ~~Scale analysis and architecture note~~ ✓
20. PostgreSQL persistence (replace in-memory store)
21. Worker-based async processing (Redis queues)
22. Durable job state + distributed AI ops metrics
23. Auth + multi-user review workflows
