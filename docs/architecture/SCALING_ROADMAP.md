# Scaling Roadmap: 100k MAU / Millions of Pages

This document outlines how the current local-first MVP can evolve into a
durable multi-service platform as document volume, concurrency, and AI workload
intensity grow.

---

## 1. Current Design

### Pipeline (all synchronous, single process)

```
POST /upload
  → file.read()
  → LocalStorage.save()
  → parse_document()          [di_core/parser.py]
  → preprocess_document()     [di_core/preprocessor.py]
  → route_document()          [di_core/router.py]
  → chunk_text()              [di_core/chunker.py]
  → classify_document_size()  [di_core/size_guard.py]
  → enrich_chunks()           [di_core/enrichment.py]
  → store in _documents dict
  → return Document JSON

POST /extract
  → extract_fields()          [di_core/extractor.py]
  → postprocess_extraction()  [di_core/postprocessor.py]
  → _ensure_reviewable()      [di_core/review_queue.py]
  → return ExtractionResult

POST /summarise
  → select_chunks_for_llm()   [di_core/chunk_selector.py]
  → LLMAdapter call           [ai_core/summariser.py]
  → grounding_audit()         [ai_core/grounding.py]
  → package_evidence()        [di_core/evidence.py]
  → _ensure_reviewable()
  → return ExtractionResult
```

### State storage

| Store | Type | Scope |
|-------|------|-------|
| `_documents` | `dict[str, Document]` | In-process, lost on restart |
| `_extractions` | `dict[str, ExtractionResult]` | In-process |
| `_reviewables` | `dict[str, ReviewableOutput]` | In-process |
| `_corrections` | `dict[str, CorrectionRecord]` | In-process |
| `_feedback` | `list[FeedbackSignal]` | In-process |
| Raw file bytes | Local filesystem via `LocalStorage` | Survives restart |

### Infrastructure (Docker Compose)

- **py-api** — single FastAPI process
- **web** — Next.js frontend
- **postgres** — provisioned but not used for domain data yet
- **redis** — provisioned but not used yet

### Why this design is correct for now

- One vertical slice works end to end
- Every pipeline stage is a pure function (takes Document, returns result)
- Libraries (`di_core`, `ai_core`, `data_model`) are separate from the API layer
- Pipeline trace captures per-stage timing
- The code is inspectable and debuggable by one person

---

## 2. What Breaks First as Volume Grows

### 2.1 Memory: in-process dicts (breaks at ~1,000 concurrent docs)

Five module-level dicts hold all state. At 100k MAU with thousands of active
documents, a single uvicorn process runs out of memory. Horizontal scaling
(multiple workers) creates split-brain — each worker sees different state.

**First fix:** Move state to PostgreSQL. The Pydantic models map cleanly to
relational tables. `_ensure_reviewable()` becomes a `SELECT ... FOR UPDATE`
+ `INSERT` pattern.

### 2.2 Latency: synchronous pipeline (breaks at ~50 concurrent uploads)

A 100-page PDF takes ~2s to parse + chunk. A 3,000-page PDF takes 30s+.
Summarisation adds 5–30s of LLM latency. During that time, the uvicorn
worker is blocked.

**First fix:** Upload returns immediately with `status: processing`. Parsing
and downstream stages run in a background worker consuming from a Redis queue.

### 2.3 File storage: local disk (breaks at ~10,000 files)

LocalStorage writes to a single directory. No replication, no backup, no
multi-node access, no quota enforcement.

**First fix:** Swap `LocalStorage` for an S3-compatible adapter. The storage
interface (`save`, `read_bytes`, `exists`) already anticipates this.

### 2.4 LLM throughput: synchronous, unbounded (breaks at ~100 concurrent summaries)

Every summarise request makes a synchronous OpenAI call. No rate limiting,
no backpressure, no retry logic.

**First fix:** Queue summarisation jobs. Apply per-tenant rate limits. Add
circuit breaker with exponential backoff.

### 2.5 Search quality: heuristic ranking (degrades at ~100k chunks)

`LexicalRanker` and `SalienceRanker` iterate over all document chunks in
memory. No index, no embedding-based retrieval.

**First fix:** Store chunks in PostgreSQL with pgvector. Use embedding-based
retrieval for large corpora. Keep heuristic reranking as a second stage.

---

## 3. First Production Evolution

### Architecture: API + Workers + Postgres + Redis + S3

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Next.js │────▶│   BFF    │────▶│  py-api  │
│   web    │     │  (Node)  │     │ (FastAPI) │
└──────────┘     └──────────┘     └────┬─────┘
                                       │
                      ┌────────────────┼────────────────┐
                      ▼                ▼                ▼
               ┌────────────┐  ┌────────────┐  ┌────────────┐
               │  worker-   │  │  worker-   │  │  worker-   │
               │  ingest    │  │  ai        │  │  eval      │
               └──────┬─────┘  └──────┬─────┘  └──────┬─────┘
                      │               │               │
           ┌──────────┴───────────────┴───────────────┴──────────┐
           │                   Shared data layer                  │
           │  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
           │  │ Postgres │  │  Redis   │  │    S3    │          │
           │  │ +pgvector│  │          │  │          │          │
           │  └──────────┘  └──────────┘  └──────────┘          │
           └──────────────────────────────────────────────────────┘
```

### Synchronous (stays in py-api)

| Operation | Reason |
|-----------|--------|
| `POST /upload` | Accept file → S3 → create DB row → enqueue `doc.ingest` → return `{id, status: processing}` |
| `GET /documents` | Read from Postgres |
| `GET /documents/{id}` | Read from Postgres |
| `GET /review-queue` | Query Postgres ordered by priority |
| `POST /review` | Update Postgres row |
| `POST /correct` | Insert correction row, enqueue feedback job |

### Asynchronous (moves to workers via Redis queues)

| Job | Worker | Input | Output |
|-----|--------|-------|--------|
| `doc.ingest` | worker-ingest | S3 key + doc_id | Parsed pages, chunks, routing in Postgres |
| `doc.extract` | worker-ai | doc_id | Extraction result + reviewable in Postgres |
| `doc.summarise` | worker-ai | doc_id + extraction_id | Summary + grounding in Postgres |
| `doc.embed` | worker-ai | doc_id | Chunk embeddings in pgvector |
| `eval.run` | worker-eval | eval config | Metrics report |
| `feedback.process` | worker-eval | correction_id | Updated fixtures/heuristics |

### Storage migration

| Data | From | To |
|------|------|----|
| Raw files | `LocalStorage` → disk | S3 bucket |
| Documents + pages | `_documents` dict | `documents` + `pages` tables |
| Chunks | In-memory on Document | `chunks` table with pgvector index |
| Extractions | `_extractions` dict | `extractions` table |
| Review items | `_reviewables` dict | `review_items` table (indexed by status + priority) |
| Corrections | `_corrections` dict | `corrections` table (append-only) |
| Feedback | `_feedback` list | `feedback_signals` table |
| Job queue | N/A | Redis (Celery or Bull) |
| Hot cache | N/A | Redis (document metadata, chunk counts) |

### Database schema (first pass)

```sql
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'processing',
    content_type    TEXT,
    s3_key          TEXT NOT NULL,
    routing         JSONB,
    parse_meta      JSONB,
    size_category   TEXT,
    pipeline_trace  JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE pages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id),
    page_number     INT NOT NULL,
    text            TEXT NOT NULL,
    char_count      INT NOT NULL DEFAULT 0
);

CREATE TABLE chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id),
    index           INT NOT NULL,
    text            TEXT NOT NULL,
    embedding       vector(1536),
    page_numbers    INT[] NOT NULL DEFAULT '{}',
    section_label   TEXT,
    strategy        TEXT,
    metadata        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chunks_doc ON chunks(document_id);
CREATE INDEX idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops);

CREATE TABLE extractions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID NOT NULL REFERENCES documents(id),
    output_type         TEXT NOT NULL,
    model_used          TEXT NOT NULL DEFAULT 'deterministic',
    structured_fields   JSONB NOT NULL DEFAULT '[]',
    summary             JSONB,
    grounding_audit     JSONB,
    summarisation_meta  JSONB,
    processing_time_ms  INT NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE review_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id   UUID NOT NULL REFERENCES extractions(id),
    document_id     UUID NOT NULL REFERENCES documents(id),
    status          TEXT NOT NULL DEFAULT 'pending_review',
    trigger_reasons TEXT[] NOT NULL DEFAULT '{}',
    priority_score  FLOAT NOT NULL DEFAULT 0,
    decisions       JSONB NOT NULL DEFAULT '[]',
    correction_id   UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_review_status_priority ON review_items(status, priority_score DESC);

CREATE TABLE corrections (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id       UUID NOT NULL REFERENCES extractions(id),
    document_id         UUID NOT NULL REFERENCES documents(id),
    reviewer_id         TEXT NOT NULL,
    field_corrections   JSONB NOT NULL DEFAULT '[]',
    summary_correction  JSONB,
    evidence_mismatches JSONB NOT NULL DEFAULT '[]',
    notes               TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE feedback_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    correction_id   UUID NOT NULL REFERENCES corrections(id),
    category        TEXT NOT NULL,
    signal_type     TEXT NOT NULL,
    description     TEXT NOT NULL,
    priority        TEXT NOT NULL DEFAULT 'medium',
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 4. Main Bottlenecks (ordered by impact)

| # | Bottleneck | Impact | Breaking point |
|---|-----------|--------|----------------|
| 1 | In-memory state | Data loss, no horizontal scaling | Any restart or second worker |
| 2 | Synchronous ingestion | Blocked workers, timeout on large docs | ~50 concurrent uploads |
| 3 | LLM call in request path | Unpredictable latency, rate limits | ~100 concurrent summaries |
| 4 | Local file storage | No replication, single-node limit | ~10k files or multi-node deploy |
| 5 | No chunk index | Linear scan for search/ranking | ~100k chunks |
| 6 | No auth/rate limiting | Abuse, no multi-tenancy | Any public exposure |
| 7 | No duplicate detection | Wasted compute on re-uploads | Proportional to upload volume |

---

## 5. First Reliability Protections

### 5.1 Idempotent ingestion

Assign a content hash on upload. If the hash already exists, return the
existing document ID. This prevents duplicate processing for re-uploads.

### 5.2 Per-stage timeouts

Each pipeline stage should have a timeout. If parsing takes >60s, fail the
stage as RETRYABLE and re-queue with a backoff. The `PipelineTrace` and
`StageOutcome` models already support this classification.

### 5.3 Dead letter queue

Jobs that fail 3 times go to a dead letter queue for manual inspection.
The `FailureKind` enum (HARD, SOFT, RETRYABLE, REVIEW_NEEDED) maps directly
to retry policy:

- HARD → dead letter immediately
- SOFT → succeed with warning, no retry
- RETRYABLE → retry up to 3 times with backoff
- REVIEW_NEEDED → succeed but flag for HITL

### 5.4 Health checks and circuit breakers

- `/health` already exists
- Add `/health/ready` that checks DB + Redis + S3 connectivity
- Circuit breaker on LLM provider: if 5 consecutive failures, stop
  sending requests for 60s

### 5.5 Evidence immutability

Once chunks are created and an extraction references them by chunk ID,
those chunks must not be deleted or modified. Use soft-delete and
versioned chunk sets so evidence references remain valid.

### 5.6 Review queue backpressure

If the review queue grows beyond a threshold, pause auto-acceptance and
route more items to human review. Monitor `pending_count` as an
operational metric.

---

## 6. Horizontal Scaling Strategy

### What scales horizontally

| Component | How |
|-----------|-----|
| py-api | Stateless after DB migration; add instances behind load balancer |
| worker-ingest | Consume from Redis queue; add instances for throughput |
| worker-ai | Consume from Redis queue; scale independently based on LLM rate limits |
| web (Next.js) | Stateless; CDN + multiple instances |

### What scales vertically first

| Component | Why |
|-----------|-----|
| PostgreSQL | Single-writer DB; read replicas help reads, but writes need bigger instance first |
| Redis | Single instance handles ~100k ops/s; cluster only at very high queue volume |

### What needs a different solution at extreme scale

| Threshold | Change |
|-----------|--------|
| >10M chunks | pgvector → dedicated vector DB (Qdrant, Pinecone) |
| >1M documents | Partition Postgres tables by created_at or tenant_id |
| >1000 concurrent LLM calls | Multiple LLM providers with load balancing + fallback |
| >100 reviewers | Review queue needs assignment locking + conflict resolution |

---

## 7. Preserving Evidence Traceability at Scale

Evidence traceability is a product feature, not an engineering detail.
At scale, preserving it requires:

1. **Immutable chunk IDs** — never reuse or overwrite a chunk ID
2. **Versioned extractions** — if re-extraction runs, create a new extraction row; don't overwrite
3. **Correction audit trail** — corrections table is append-only
4. **Feedback lineage** — every feedback signal links to a correction, which links to an extraction, which links to a document
5. **Evidence validation on read** — when displaying evidence, verify the chunk still exists; if not, show a "source no longer available" marker

The full chain is:

```
Document → Pages → Chunks → Extraction → Evidence References
                                       → ReviewableOutput → Decisions
                                       → CorrectionRecord → FeedbackSignals
```

Every link in this chain has a UUID. At scale, this chain lives in
PostgreSQL with foreign key constraints, not in memory.

---

## 8. Cost Awareness

| Resource | Current cost | At 100k MAU |
|----------|-------------|-------------|
| LLM calls | ~$0.01/summary | $1,000–10,000/month depending on volume |
| Storage | Local disk (free) | S3: ~$0.023/GB/month |
| Compute | One process | 4–8 API instances + 4–16 workers |
| Database | Local Postgres | RDS: $200–800/month |
| OCR (future) | None | Textract: ~$1.50/1000 pages |

The biggest cost driver is LLM calls. Strategies to control cost:

- Cache summaries (same document → same summary unless extraction changes)
- Auto-accept high-confidence extractions to reduce HITL volume
- Use smaller/cheaper models for deterministic extraction validation
- Batch evaluation runs during off-peak hours
