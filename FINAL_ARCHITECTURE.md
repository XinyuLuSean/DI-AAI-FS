# FINAL_ARCHITECTURE

## 1. Purpose

This repository is the long-term north-star architecture for an interview-oriented but production-minded platform that combines:

1. **Document Intelligence**
2. **Applied AI / LLM systems**
3. **Full-stack product delivery**

The repo must support two realities at the same time:

- **Near-term goal:** quickly bootstrap a very small, runnable, interview-ready vertical slice
- **Long-term goal:** grow into a production-grade platform that can ingest large volumes of documents, extract structured information, run evidence-backed AI workflows, and expose those workflows through a reliable full-stack application

This document defines the final architecture, stack constraints, repo structure, scaling path, and design rules. The initial implementation may be tiny, but it must not block future evolution.

---

## 2. Product Goal

Build a platform that can:

- accept uploaded files such as PDFs, text files, and future mixed-media documents
- normalize and classify documents
- extract structured facts
- create evidence-backed summaries and case analysis outputs
- support retrieval and question-answering over document collections
- expose all of the above through a web UI and APIs
- support evaluation, human review, and production observability

The system must be designed for:

- correctness first
- explainability and evidence traceability
- easy local development
- interview realism
- scalable migration from prototype to production

---

## 3. Architectural Principles

## 3.1 Separation of concerns
The platform is split into three major domains:

- **Document Intelligence Layer**
- **Applied AI Layer**
- **Full-Stack Product Layer**

Each domain must be independently testable.

## 3.2 Thin vertical slice first
The first runnable version must implement one minimal end-to-end path:

`upload document -> parse document -> store chunks -> run one AI task -> render result in UI`

No large framework additions unless they serve this path.

## 3.3 Schema-first design
Every important boundary must have an explicit schema:

- ingestion payloads
- parsed document models
- extraction outputs
- AI response schemas
- API response contracts
- evaluation result formats

## 3.4 Evidence-backed AI by default
Any generated summary, answer, or analysis must be linked to source evidence whenever possible.

## 3.5 Deterministic vs open-ended output separation
Evaluation and system design must distinguish:

- **deterministic fields**: dates, names, codes, totals, providers, document types, claim numbers
- **open-ended fields**: summaries, narratives, timelines, case analysis

These are not evaluated the same way and should not share a single scoring strategy.

## 3.6 Local-first, cloud-ready
The repo must run locally with Docker Compose, but the final design must map cleanly to AWS production infrastructure.

## 3.7 Human-in-the-loop is a first-class capability
The system must support review queues, correction workflows, and feedback capture from the beginning of the architecture.

## 3.8 Production reliability is part of the product
Logging, health checks, retries, idempotency, validation, and evaluation are core features, not afterthoughts.

---

## 4. Final Production Architecture

## 4.1 Logical layers

### A. Presentation Layer
Responsibilities:

- file upload UI
- document list and status UI
- extraction result viewer
- evidence panel
- document chat / ask-doc UI
- human review UI
- evaluation dashboards
- streaming interaction controls
- reset / clear / cancel actions

Primary runtime:

- Next.js + React + TypeScript

### B. Product Gateway Layer
Responsibilities:

- frontend-safe API surface
- auth/session integration
- request shaping
- response normalization
- streaming proxying
- feature flags
- rate limiting
- API composition across Python services

Primary runtime:

- Node.js + TypeScript

This layer can be skipped in the earliest local skeleton if needed, but it is part of the final architecture.

### C. Document Intelligence Layer
Responsibilities:

- file intake
- document routing
- PDF parsing
- OCR fallback
- page-level metadata extraction
- document segmentation
- chunking
- normalization
- structured extraction
- source/evidence indexing

Primary runtime:

- Python + FastAPI + workers

### D. Applied AI Layer
Responsibilities:

- prompt execution
- schema-constrained generation
- document summarization
- chronology generation
- semantic matching
- retrieval
- reranking
- grounding
- structured case analysis
- model evaluation
- regression testing for prompts/models
- feedback ingestion for future improvements

Primary runtime:

- Python + FastAPI + background workers

### E. Data and Persistence Layer
Responsibilities:

- transactional application data
- document metadata
- extracted facts
- chunk storage metadata
- AI run history
- evaluation runs
- HITL corrections
- vector search
- caching
- object storage

Primary systems:

- PostgreSQL
- pgvector
- Redis
- S3-compatible object storage

### F. Observability and Operations Layer
Responsibilities:

- logs
- metrics
- traces
- health endpoints
- retry visibility
- queue visibility
- failure isolation
- alerting
- regression reporting

Primary systems:

- OpenTelemetry
- Prometheus
- Grafana
- Sentry
- CloudWatch in AWS production

---

## 5. End-to-End Data Flow

## 5.1 Upload and intake
1. User uploads a file in the web app
2. Web app sends metadata and file to the product gateway or directly to Python API in the smallest bootstrap version
3. File is stored in object storage
4. A document ingestion job is created
5. Worker picks up ingestion job

## 5.2 Parsing and normalization
1. Worker parses the document
2. If native text exists, extract directly
3. If scanned or low-quality, run OCR fallback
4. Build normalized page/block/chunk structures
5. Store chunk metadata and extraction-ready payloads

## 5.3 Extraction and indexing
1. Run document classification
2. Run deterministic field extraction
3. Build embeddings for chunks
4. Store vector references
5. Persist structured outputs and evidence links

## 5.4 AI workflow
1. User selects a task or enters a query
2. Retrieval selects relevant chunks
3. Reranker improves candidate evidence ordering
4. LLM generates structured output under a strict schema
5. System attaches evidence references and validation status
6. Result is returned to the UI

## 5.5 HITL and evaluation
1. Reviewer inspects output
2. Reviewer confirms, edits, or rejects fields/summary
3. Corrections are stored
4. Evaluation jobs compare system output against references and/or corrections
5. Metrics are updated for dashboards and regressions

---

## 6. Major Runtime Components

## 6.1 `apps/web`
User-facing web application.

Responsibilities:

- upload UI
- document status UI
- extraction viewer
- evidence viewer
- ask-doc and summary UI
- review queue UI
- evaluation dashboard UI

## 6.2 `apps/bff`
Node.js / TypeScript product gateway.

Responsibilities:

- typed API layer for the frontend
- request/response composition
- streaming proxy
- auth/session middleware
- API guards
- feature flags

## 6.3 `apps/py-api`
Python FastAPI service.

Responsibilities:

- ingestion API
- document APIs
- extraction APIs
- retrieval APIs
- AI task APIs
- evaluation APIs
- health/status endpoints

## 6.4 `apps/worker-ingest`
Background worker for parsing and chunking.

Responsibilities:

- parse PDFs/text
- OCR fallback
- chunking
- metadata extraction
- document routing
- normalization

## 6.5 `apps/worker-ai`
Background worker for AI operations.

Responsibilities:

- batch extractions
- summarization
- retrieval jobs
- embedding generation
- reranking
- offline scoring tasks

## 6.6 `apps/worker-eval`
Background worker for evaluation/regression.

Responsibilities:

- deterministic field scoring
- semantic summary evaluation
- rubric-based LLM judge workflows
- evaluation slicing
- reporting

---

## 7. Final Repo Structure

```text
DI-AAI-FS/
├─ AGENT.md
├─ FINAL_ARCHITECTURE.md
├─ README.md
├─ .editorconfig
├─ .gitignore
├─ .env.example
├─ pnpm-workspace.yaml
├─ pyproject.toml
├─ uv.lock
├─ package.json
├─ pnpm-lock.yaml
│
├─ apps/
│  ├─ web/                         # Next.js app
│  │  ├─ app/
│  │  ├─ components/
│  │  ├─ features/
│  │  ├─ lib/
│  │  ├─ hooks/
│  │  ├─ styles/
│  │  └─ tests/
│  │
│  ├─ bff/                         # Node.js/TypeScript gateway
│  │  ├─ src/
│  │  └─ tests/
│  │
│  ├─ py-api/                      # FastAPI app
│  │  ├─ src/
│  │  │  ├─ api/
│  │  │  ├─ core/
│  │  │  ├─ services/
│  │  │  ├─ db/
│  │  │  ├─ models/
│  │  │  └─ main.py
│  │  └─ tests/
│  │
│  ├─ worker-ingest/
│  │  ├─ src/
│  │  └─ tests/
│  │
│  ├─ worker-ai/
│  │  ├─ src/
│  │  └─ tests/
│  │
│  └─ worker-eval/
│     ├─ src/
│     └─ tests/
│
├─ packages/
│  ├─ shared-types/                # cross-service TS schemas/types
│  ├─ ui/                          # reusable React UI components
│  ├─ tsconfig/                    # shared TS config
│  ├─ prompts/                     # prompt templates, prompt metadata, prompt tests
│  └─ client-sdk/                  # frontend/server SDKs for calling APIs
│
├─ py/
│  ├─ libs/
│  │  ├─ di_core/                  # parsing, OCR, chunking, routing
│  │  ├─ ai_core/                  # retrieval, prompting, generation, reranking
│  │  ├─ eval_core/                # metrics, scoring, slicing, rubric workflows
│  │  ├─ data_model/               # Pydantic/ORM/shared schemas
│  │  ├─ storage/                  # S3/Postgres/Redis adapters
│  │  └─ observability/            # logging, tracing, metrics helpers
│  │
│  └─ tests/
│
├─ data/
│  ├─ fixtures/                    # sample local input documents
│  ├─ seeds/
│  └─ contracts/                   # example JSON inputs/outputs
│
├─ infra/
│  ├─ compose/                     # local Docker Compose
│  ├─ docker/                      # Dockerfiles
│  ├─ aws/
│  │  ├─ terraform/
│  │  └─ diagrams/
│  ├─ k8s/                         # future EKS manifests or Helm charts
│  └─ monitoring/
│
├─ scripts/
│  ├─ dev/
│  ├─ setup/
│  ├─ seed/
│  └─ ci/
│
├─ docs/
│  ├─ architecture/
│  ├─ decisions/                   # ADRs
│  ├─ api/
│  ├─ evaluation/
│  ├─ prompts/
│  └─ runbooks/
│
└─ tests/
   ├─ e2e/
   ├─ contract/
   └─ smoke/
````

---

## 8. Stack Lock and Version Constraints

These are the default technology choices unless there is an explicit architectural reason to change them.

## 8.1 Anchors

* **Python:** `3.12.x`
* **Node.js:** `>=18 <23`
* **uv:** `>=0.9.16`
* **pnpm:** `10.x`

## 8.2 Frontend and TypeScript stack

* **TypeScript:** `5.8+`
* **Next.js:** `16.x`
* **React:** `19.x`
* **Tailwind CSS:** `4.x`
* **TanStack Query:** `5.x`
* **Zustand:** `5.x`
* **Zod:** `3.x`
* **Playwright:** `1.5x`
* **ESLint:** `9.x`
* **Prettier:** `3.x`

## 8.3 Python API and worker stack

* **FastAPI:** `0.115+`
* **Uvicorn:** `0.3x`
* **Pydantic:** `2.12+`
* **SQLAlchemy:** `2.0+`
* **Alembic:** `1.1x`
* **psycopg:** `3.2+`
* **httpx:** `0.28+`
* **tenacity:** `9.x`
* **structlog:** `24+`

## 8.4 Document Intelligence stack

* **PyMuPDF:** `1.25+`
* **pypdf:** `5.x`
* **pdfplumber:** `0.11+`
* **Pillow:** `10+`
* **Polars:** `1.x`
* **Tesseract OCR / Paddle OCR:** installed at system level for local OCR fallback
* **AWS Textract:** production OCR option for difficult/scanned documents

## 8.5 Applied AI stack

* **LiteLLM:** `1.x`
* **OpenAI/Anthropic provider SDKs:** only if needed behind a small adapter layer
* **sentence-transformers or provider embeddings:** allowed behind adapter layer
* **reranker implementation:** provider or local model, but hidden behind an internal interface
* **JSON-schema constrained outputs:** required for extraction/summarization APIs

## 8.6 Data and queue stack

* **PostgreSQL:** `16+`
* **pgvector:** `0.8+`
* **Redis:** `7.2+`
* **Celery or RQ:** choose one for local bootstrap; queue abstraction must allow migration to SQS in production
* **S3-compatible object storage:** required for source documents and artifacts

## 8.7 Observability and quality stack

* **OpenTelemetry:** current stable line
* **Prometheus:** current stable line
* **Grafana:** current stable line
* **Sentry:** current stable line
* **pytest:** `8.x`
* **mypy:** `1.1x`
* **Ruff:** `0.1x+`

## 8.8 Container/runtime stack

* **Docker Engine:** modern stable version
* **Docker Compose v2**
* **AWS ECS/Fargate:** default first production target
* **AWS EKS/Kubernetes:** future scale target, not first deployment target

---

## 9. Why This Stack

## 9.1 Python is the core for document and AI workflows

Python owns:

* parsing
* OCR orchestration
* chunking
* extraction
* retrieval
* evaluation
* data transformations
* AI task pipelines

## 9.2 Node.js is the product delivery bridge

Node.js/TypeScript owns:

* full-stack product flow
* frontend integration
* gateway concerns
* request shaping
* streaming UX
* production UI velocity

## 9.3 Postgres is the source of truth

Postgres is the central transactional store for:

* document metadata
* extraction outputs
* review records
* evaluation history
* prompt/model runs
* app state that must be queryable and auditable

## 9.4 S3/Redis/queue are mandatory even for a small system

They make the architecture naturally extensible to large-file and asynchronous processing scenarios.

---

## 10. Initial Runnable Skeleton That Must Exist First

The first implementation of this repo should be intentionally small.

It must include only these capabilities:

1. upload one PDF or text file
2. store metadata
3. parse text from the file
4. chunk the text
5. run one simple AI workflow over the chunks
6. return a strict JSON response
7. render the result in a web page
8. show the evidence chunks used
9. include at least one smoke test

## 10.1 Minimum initial services

Start with only:

* `apps/web`
* `apps/py-api`
* `py/libs/di_core`
* `py/libs/ai_core`
* `py/libs/data_model`
* `infra/compose`
* `data/fixtures`
* `tests/smoke`

## 10.2 Optional omissions for the first slice

The following may be deferred but must not be blocked by the architecture:

* `apps/bff`
* `worker-eval`
* AWS-specific deployment
* OCR fallback
* reranker
* HITL review UI
* dashboarding
* auth

---

## 11. Domain Models That Must Exist Early

The system should define these entities early, even if the first version uses simplified tables/schemas:

* `Case`
* `Document`
* `DocumentSource`
* `DocumentPage`
* `DocumentChunk`
* `ExtractionRun`
* `StructuredField`
* `EvidenceReference`
* `PromptRun`
* `SummaryResult`
* `ReviewTask`
* `ReviewDecision`
* `EvaluationRun`
* `EvaluationMetric`

---

## 12. API Surface (Final Direction)

The final platform should expose APIs in categories like:

* `/health`
* `/documents/upload`
* `/documents/{id}`
* `/documents/{id}/chunks`
* `/documents/{id}/extract`
* `/documents/{id}/summary`
* `/documents/{id}/ask`
* `/documents/{id}/review`
* `/evaluations/run`
* `/evaluations/{id}`
* `/prompts`
* `/metrics`

The first slice should implement only what is needed to demo the vertical flow.

---

## 13. Evaluation Strategy

## 13.1 Deterministic field evaluation

Use:

* exact match
* normalized exact match
* tolerance-based numeric/date comparison
* precision/recall/F1 for extracted fields
* slice-based breakdown by document type and source quality

## 13.2 Open-ended summary evaluation

Use a combination of:

* fact coverage
* grounding / evidence support
* contradiction detection
* semantic similarity
* rubric scoring
* actionability for end users
* reviewer correction rate

## 13.3 System metrics

Track:

* ingestion latency
* parse latency
* retrieval latency
* generation latency
* end-to-end latency
* failure rate
* queue age
* throughput
* review turnaround
* evidence attachment rate

---

## 14. HITL Requirements

The final system must support:

* review queue creation
* reviewer edits to structured fields
* reviewer edits to summaries
* reviewer confidence/approval flags
* failure categorization
* correction persistence
* export of reviewed datasets for future tuning/evaluation

The first slice does not need full HITL UI, but the data model must leave room for it.

---

## 15. Production Deployment Target

## 15.1 Local development

Use Docker Compose with:

* web
* py-api
* postgres
* redis
* local object storage or filesystem-backed storage

## 15.2 First production deployment

Deploy on AWS using:

* ECS/Fargate
* RDS Postgres
* ElastiCache Redis
* S3
* CloudWatch
* secrets manager

## 15.3 Future scale deployment

When needed, evolve toward:

* EKS
* autoscaled ingestion workers
* autoscaled AI workers
* dedicated retrieval services
* separate evaluation pipeline
* stronger multi-tenant isolation

---

## 16. Non-Goals for the First Iteration

The initial implementation should not try to solve all of these immediately:

* enterprise auth
* multi-region deployment
* advanced permissioning
* full fine-tuning pipeline
* production-grade multi-tenancy
* full legal-domain ontology
* all document types
* all cloud automation

Those belong to later iterations.

---

## 17. Build Rules

1. Every new feature must preserve the small runnable local path
2. No hidden magic: all important flows should be traceable through code and logs
3. No direct LLM calls from UI components
4. No schema-less core API responses
5. No hardcoded secrets
6. No provider lock-in without an adapter
7. No large dependency additions without clear justification
8. Every AI output intended for users should prefer evidence references
9. Every service should expose a health endpoint
10. Every major interface should have example fixtures/contracts

---

## 18. Definition of Success

This repository is successful when it becomes:

* a small but runnable interview-oriented system at the start
* a clean learning environment for manual setup and understanding
* a serious foundation for document intelligence, applied AI, and full-stack product growth
* a repo that can scale in complexity without requiring a rewrite of the core boundaries