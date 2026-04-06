# DI-AAI-FS — Document Intelligence Playground

A local-first playground for document ingestion, structured extraction,
retrieval, grounded AI workflows, and human review.

## What It Covers

- PDF, TXT, and Markdown upload plus parsing and preprocessing
- Heuristic document routing and multiple chunking strategies
- Deterministic field extraction with evidence references
- Grounded summarisation, chronology, classification, and semantic matching
- Retrieval comparison, reranking, and review-queue workflows
- Evaluation helpers plus basic AI operations visibility

The current runtime is intentionally synchronous and mostly in-memory. That
keeps the project easy to inspect locally while still exercising the core
document-intelligence and applied-AI paths end to end.

## Documentation

- `docs/architecture/DI_AAI_Map.md` — best repo-wide entry point
- `docs/architecture/DI_Map.md` — baseline AI request path, prompt flow, and grounding flow
- `docs/architecture/SCALING_ROADMAP.md` — path from local MVP to workers + durable storage
- `docs/applied-ai/AI_Scale.md` — reliability and ops notes for AI workloads
- `docs/architecture/FINAL_ARCHITECTURE.md` — long-term north-star architecture

## Repo Layout

```text
DI-AAI-FS/
├── README.md
├── .env.example
├── pyproject.toml
├── package.json
├── apps/
│   ├── py-api/        # FastAPI backend
│   └── web/           # Next.js frontend
├── py/libs/
│   ├── ai_core/       # prompts, adapter, summarisation, chronology, validation
│   ├── data_model/    # shared Pydantic contracts
│   ├── di_core/       # parsing, chunking, extraction, retrieval, review logic
│   ├── di_eval/       # evaluation runners and metrics
│   └── storage/       # local storage abstraction
├── data/
│   ├── contracts/
│   └── fixtures/
├── docs/
│   ├── applied-ai/
│   │   └── AI_Scale.md
│   └── architecture/
│       ├── DI_AAI_Map.md
│       ├── DI_Map.md
│       ├── FINAL_ARCHITECTURE.md
│       └── SCALING_ROADMAP.md
├── infra/
│   ├── compose/
│   └── docker/
└── tests/
    ├── eval/
    └── smoke/
```

## Prerequisites

- Python `3.12.x`
- `uv >= 0.9.16`
- Node.js `>=18 <25`
- `pnpm 10.x`
- Docker + Docker Compose v2

Quick check: `bash scripts/dev/check-env.sh`

## Getting Started

### 1. Clone and configure

```bash
git clone <your-github-repo-url>
cd <repo-directory>
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env` if you want live AI calls.

### 2. Install dependencies

```bash
uv sync
pnpm install
```

### 3. Optional local infrastructure

```bash
docker compose -f infra/compose/docker-compose.yml up postgres redis -d
```

Postgres and Redis are included to match the planned architecture, but the
current MVP still stores application state in memory.

### 4. Start the backend

```bash
uv run uvicorn py_api.main:app --reload --port 8000
```

Verify with `curl http://localhost:8000/health`.

### 5. Start the frontend

```bash
pnpm dev:web
```

Open `http://localhost:3000`.

### 6. Run the main workflow

1. Upload a sample document such as `data/fixtures/sample.txt`
2. Inspect parse metadata, routing, chunks, and size classification
3. Run deterministic extraction
4. Run grounded summarisation or another AI task
5. Open the review queue and inspect or correct flagged outputs

### 7. Run checks

```bash
pnpm run check
```

For backend-only verification, use `pnpm run test:py`.

## Current Constraints

- Documents, extractions, review items, and feedback remain in process memory
- Long-running AI calls still execute synchronously in the API request path
- Docker includes future infrastructure that the current slice does not fully use yet

Those tradeoffs are intentional for a small local-first build. The next
evolution is documented in `docs/architecture/SCALING_ROADMAP.md`.
