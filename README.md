# DI-AAI-FS — Document Intelligence + Applied AI + Full-Stack

A platform for document ingestion, structured extraction, and evidence-backed AI analysis.

**Current state:** MVP vertical slice (local development only).

## What This MVP Does

```
Upload file → Parse text → Chunk → AI Summarise → Structured JSON → UI with evidence
```

This is the smallest runnable end-to-end path. It is not production-ready — it uses in-memory storage and synchronous processing. See `FINAL_ARCHITECTURE.md` for the full north-star design.

---

## Repo Structure

```
DI-AAI-FS/
├── AGENT.md                    # AI assistant behaviour rules
├── FINAL_ARCHITECTURE.md       # North-star architecture design
├── README.md                   # ← you are here
├── .env.example                # Environment variable template
├── pyproject.toml              # Python workspace (uv)
├── package.json                # Node.js workspace (pnpm)
├── pnpm-workspace.yaml
│
├── apps/
│   ├── py-api/                 # FastAPI backend (health, upload, summarise)
│   └── web/                    # Next.js frontend (upload, viewer, evidence)
│
├── py/libs/
│   ├── data_model/             # Pydantic schemas (Document, Chunk, Extraction)
│   ├── di_core/                # Document parsing + chunking
│   ├── ai_core/                # LLM adapter + prompt registry + summariser
│   └── storage/                # Local filesystem adapter (→ S3 later)
│
├── infra/
│   ├── compose/                # Docker Compose for local dev
│   └── docker/                 # Dockerfiles
│
├── data/
│   ├── fixtures/               # Sample input files for testing
│   └── contracts/              # Example JSON request/response shapes
│
├── tests/smoke/                # Smoke tests (health, upload)
└── scripts/dev/                # Developer utility scripts
```

---

## Prerequisites

### Required Tools

| Tool | Required Version | Purpose |
|------|-----------------|---------|
| **Python** | 3.12.x | Backend runtime, document processing, AI pipelines |
| **uv** | ≥ 0.9.16 | Fast Python package manager with workspace support |
| **Node.js** | ≥ 18, < 23 | Frontend runtime (Next.js) |
| **pnpm** | 10.x | Node.js package manager with workspace support |
| **Docker** | modern stable | Container runtime for Postgres, Redis |
| **Docker Compose** | v2 | Multi-container orchestration |
| **Git** | any modern | Version control |

### Quick Environment Check

Run the automated checker:

```zsh
zsh scripts/dev/check-env.sh
```

### Manual Check Commands

Each command below verifies one tool. If any fails, follow the install instructions.

```bash
# Python — must be 3.12.x
uv run python --version
# Expected: Python 3.12.x
# Install (macOS):  brew install python@3.12
# Install (pyenv):  pyenv install 3.12 && pyenv global 3.12
# Install (direct): https://www.python.org/downloads/

# uv — Python package manager
uv --version
# Expected: uv 0.9.x or later
# Install: curl -LsSf https://astral.sh/uv/install.sh | sh
# Or:      brew install uv

# Node.js — must be 18-22
node --version
# Expected: v18.x through v22.x
# Install (nvm):  nvm install 22
# Install (brew): brew install node@22
# Install (fnm):  fnm install 22

# pnpm — must be 10.x
pnpm --version
# Expected: 10.x.x
# Install: corepack enable && corepack prepare pnpm@latest --activate
# Or:      npm install -g pnpm

# Docker
docker --version
# Install: https://docs.docker.com/get-docker/

# Docker Compose v2
docker compose version
# Included with Docker Desktop.
# Or: https://docs.docker.com/compose/install/

# Git
git --version
# Install (macOS): xcode-select --install  OR  brew install git
```

---

## Getting Started

### 1. Clone and configure

```bash
git clone <repo-url> && cd DI-AAI-FS
cp .env.example .env
```

Edit `.env` and set your `OPENAI_API_KEY` (needed for the AI summarisation step).

### 2. Install Python dependencies

```bash
uv sync
```

This installs all Python workspace members (`py-api`, `data_model`, `di_core`, `ai_core`, `storage`) into a single virtual environment managed by `uv`.

### 3. Install Node.js dependencies

```bash
pnpm install
```

### 4. Start infrastructure (Postgres + Redis)

```bash
docker compose -f infra/compose/docker-compose.yml up postgres redis -d
```

> **Note:** The MVP uses in-memory storage, so Postgres/Redis are not strictly required yet. They are included to match the final architecture and will be wired in the next iteration.

### 5. Start the Python API

```bash
uv run uvicorn py_api.main:app --reload --port 8000
```

Verify: `curl http://localhost:8000/health` should return `{"status":"ok","service":"py-api","version":"0.1.0"}`

### 6. Start the Next.js frontend

In a separate terminal:

```bash
pnpm dev:web
```

Open http://localhost:3000 in your browser.

### 7. Test the vertical slice

1. Upload `data/fixtures/sample.txt` via the web UI
2. See the parsed document with chunks
3. Click "Summarise Document"
4. View the AI-generated summary with evidence references

### 8. Run smoke tests

```bash
uv run pytest tests/smoke/ -v
```

---

## API Endpoints (MVP)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| POST | `/documents/upload` | Upload and parse a file |
| GET | `/documents/{id}` | Retrieve document with chunks |
| POST | `/documents/{id}/summarise` | Run AI summarisation |
| GET | `/documents/{id}/extractions/{eid}` | Get extraction result |

---

## Architecture Decisions for the MVP

| Decision | Rationale |
|----------|-----------|
| **In-memory document store** | Simplest path to a working demo. PostgreSQL is next. |
| **Synchronous parsing** | No worker queue yet. Parsing happens in the API process. |
| **LiteLLM adapter** | Provider-agnostic LLM calls. Can swap OpenAI ↔ Anthropic ↔ local. |
| **Fixed-size chunking** | Deterministic and inspectable. Semantic chunking comes later. |
| **Local file storage** | Filesystem adapter with the same interface S3 will use. |
| **No auth** | MVP is local-only. Auth is a future concern. |
| **No BFF** | Frontend calls Python API directly. The BFF gateway comes later. |

---

## What Comes Next

Following the build order from `AGENT.md`:

1. ~~repo bootstrap and environment sanity~~ ✓
2. ~~minimal FastAPI service~~ ✓
3. ~~minimal Next.js UI~~ ✓
4. ~~upload + parse endpoint~~ ✓
5. ~~chunking and structured response~~ ✓
6. ~~one AI task with strict JSON output~~ ✓
7. ~~evidence display in UI~~ ✓
8. ~~local Docker Compose Dockerfiles ready~~ ✓
9. ~~smoke tests basic tests in place, expand coverage~~ ✓
10. PostgreSQL persistence (replace in-memory store)
11. Evaluation framework
12. HITL review queue
13. Worker-based async processing
