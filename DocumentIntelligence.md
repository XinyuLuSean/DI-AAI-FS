# DocumentIntelligence

## 1. Goal

This file is the interview-oriented deep-dive plan for the **Document Intelligence** part of this repo.

The objective is not to randomly add features.

The objective is to turn the current runnable demo into a sequence of **small, realistic, manually deployable document-intelligence exercises** that help me practice:

- reading a real repo quickly
- understanding the existing document pipeline end to end
- making clean, incremental changes
- explaining tradeoffs clearly
- thinking in terms of users, business impact, and scale
- discussing productionization, evaluation, and reliability at interview depth

This plan is intentionally **phase-by-phase** and **module-by-module**.

---

## 2. Current Baseline

Before starting any phase, assume the current repo already supports this MVP path:

`upload file -> parse text -> chunk text -> run AI summarisation -> return structured JSON -> render evidence-backed output in UI`

Current document-intelligence baseline to understand first:

- upload endpoint stores files locally
- parsing currently supports:
  - native-text PDFs
  - `.txt`, `.md`, `.text`
- parsing is synchronous
- chunking is deterministic:
  - fixed-size character windows
  - overlap
  - chunk provenance includes page numbers and character offsets
- summarisation uses only the first set of chunks
- storage is local
- state is in-memory
- there is no OCR fallback yet
- there is no retrieval index yet
- there is no document router yet
- there is no evaluation harness yet
- there is no HITL workflow yet

This is good. It is the correct minimal starting point.

---

## 3. Files To Read First

Before each phase, always re-read these files:

- `apps/py-api/py_api/api/documents.py`
- `apps/py-api/py_api/main.py`
- `apps/py-api/py_api/core/config.py`
- `py/libs/di_core/src/di_core/parser.py`
- `py/libs/di_core/src/di_core/chunker.py`
- `py/libs/data_model/src/data_model/document.py`
- `py/libs/data_model/src/data_model/extraction.py`
- `py/libs/ai_core/src/ai_core/summariser.py`
- `py/libs/storage/src/storage/local.py`
- `apps/web/app/page.tsx`

The agent must understand the existing flow before proposing any changes.

---

## 4. How The Agent Must Guide Me

For this file, the agent must behave like a **step-by-step technical mentor**, not an autopilot.

For every phase, the agent must do this:

1. explain the current state of the relevant code
2. explain why the next step matters for document intelligence
3. identify the smallest meaningful implementation step
4. tell me exactly which files to inspect
5. tell me exactly what commands to run
6. tell me how to verify the result locally
7. ask me to confirm completion before moving to the next phase
8. end each phase with interview-style reflection questions

The agent must **not** skip straight to large production implementations.

The agent must **not** silently redesign the whole repo.

The agent must optimize for:

- small runnable changes
- manual deployment
- interview realism
- clear tradeoff explanations

---

## 5. Default Development Commands

Use these commands unless a phase explicitly changes them.

## 5.1 Setup

```bash
cp .env.example .env
uv sync
pnpm install
docker compose -f infra/compose/docker-compose.yml up postgres redis -d
````

## 5.2 Run backend

```bash
uv run uvicorn py_api.main:app --reload --app-dir apps/py-api
```

## 5.3 Run frontend

```bash
pnpm --filter @di-aai-fs/web dev
```

## 5.4 Run smoke tests

```bash
uv run pytest tests/smoke -q
```

---

## 6. Learning Rules For This Document Intelligence Track

1. Always start from the current runnable flow.
2. Prefer the smallest possible real implementation.
3. Preserve provenance at every step.
4. Keep deterministic extraction separate from open-ended generation.
5. Every new document feature must make debugging easier.
6. Every new step must be manually testable.
7. Every phase must produce something I can explain in an interview.

---

## 7. Phase 0 — Baseline Walkthrough And System Trace

## Goal

Fully understand the current document-intelligence flow before changing anything.

## Why this phase matters

In an interview, failing to understand the current data flow quickly is fatal. This phase trains repo reading and system tracing.

## Read first

* `apps/py-api/py_api/api/documents.py`
* `py/libs/di_core/src/di_core/parser.py`
* `py/libs/di_core/src/di_core/chunker.py`
* `py/libs/ai_core/src/ai_core/summariser.py`
* `apps/web/app/page.tsx`

## Tasks

1. Trace the exact flow from upload to UI render.
2. Identify where:

   * file bytes are received
   * file path is stored
   * pages are created
   * chunks are created
   * evidence is attached
   * extraction JSON is returned
3. Write a short local note describing:

   * input shape
   * output shape
   * synchronous boundaries
   * current limitations

## Required deliverable

A local note or markdown section with:

* current flow diagram
* current limitations
* current strongest design choices
* current biggest DI gaps

## Verification

Be able to answer, without looking:

* what function parses PDFs?
* what function chunks text?
* where page provenance comes from
* where evidence references are assembled
* why this repo is not yet production-grade

## Interview reflection

* Why is this MVP good enough as a first vertical slice?
* Why is synchronous parsing acceptable here but not at scale?
* What is the business value of keeping evidence references even in the MVP?

---

## 8. Phase 1 — Parser Deep Dive: File Types, Failure Modes, Provenance

## Goal

Strengthen parsing so the repo starts behaving like a real document-intelligence system instead of just a happy-path demo.

## Why this phase matters

Document intelligence starts with raw input quality. Interviewers often probe whether I understand messy input, unsupported formats, and failure classification.

## Read first

* `py/libs/di_core/src/di_core/parser.py`
* `py/libs/data_model/src/data_model/document.py`
* `apps/py-api/py_api/api/documents.py`

## Tasks

### Module 1A — Parser observability

Add explicit parsing metadata such as:

* parse strategy used
* file suffix
* page count
* empty-page count
* parse warnings

### Module 1B — Failure classification

Improve parser failures into categories like:

* unsupported file type
* missing file
* empty extraction
* unreadable PDF
* zero-text PDF

### Module 1C — Document metadata enrichment

Add lightweight metadata to the document record:

* file extension
* total characters
* total pages
* parse method
* text density or empty-page ratio

## Implementation rules

* Do not introduce OCR yet
* Keep parsing synchronous in this phase
* Keep interfaces simple
* Use explicit schema fields, not loose dictionaries

## Verification

Test with:

* one clean PDF
* one plain text file
* one unsupported extension
* one PDF with almost no extracted text

## Exit criteria

I can clearly explain:

* what the parser currently does
* what it does not do
* how parse quality signals influence downstream AI reliability

## Interview reflection

* Why should parse warnings survive into downstream pipeline stages?
* How would low text density affect summarisation quality?
* Why is provenance important even before retrieval exists?

---

## 9. Phase 2 — Chunking Deep Dive: Deterministic Baseline And Better Strategies

## Goal

Understand and improve chunking as a first-class DI design decision.

## Why this phase matters

Chunking is one of the most interviewable document-intelligence topics because it affects accuracy, latency, retrieval quality, and evidence traceability.

## Read first

* `py/libs/di_core/src/di_core/chunker.py`
* `py/libs/data_model/src/data_model/document.py`

## Tasks

### Module 2A — Make chunking configurable

Expose:

* chunk size
* overlap
* max chunk count
* truncation warnings

### Module 2B — Add chunk metadata

Add fields such as:

* chunk strategy
* source page span
* source character span
* approximate token count
* is_truncated

### Module 2C — Compare chunking strategies

Implement and compare:

1. current fixed-size character chunking
2. paragraph-aware chunking
3. page-bounded chunking

The implementation can still be simple.

### Module 2D — Add chunk inspection tooling

Create a local debug view or debug output to inspect:

* chunk text
* chunk boundaries
* page coverage
* overlap behavior

## Verification

Use one long PDF and one short text file.
For each strategy, inspect:

* number of chunks
* average chunk size
* page coverage
* whether important sections are cut awkwardly

## Exit criteria

I can explain:

* why fixed chunking is a good baseline
* where it breaks down
* how chunk choice changes downstream summarisation and retrieval

## Interview reflection

* Why not jump to semantic chunking immediately?
* What is the tradeoff between chunk size and retrieval precision?
* Why does inspectability matter in startup environments?

---

## 10. Phase 3 — Document Typing And Routing

## Goal

Introduce the first version of document-aware preprocessing.

## Why this phase matters

Real document-intelligence systems do not treat legal records, medical records, bills, and treatment notes identically.

## Read first

* `py/libs/di_core/src/di_core/parser.py`
* `py/libs/data_model/src/data_model/document.py`
* `apps/py-api/py_api/api/documents.py`

## Tasks

### Module 3A — Add document type enum

Start with:

* unknown
* legal
* medical
* billing
* treatment
* correspondence

### Module 3B — Add a simple routing layer

Implement a lightweight classifier/router using:

* filename heuristics
* content keyword heuristics
* page-level hints

Do not start with ML.

### Module 3C — Store router confidence and reasons

For interview clarity, keep routing explainable:

* predicted type
* confidence
* matched heuristics
* fallback status

## Verification

Test several fixture files and inspect:

* predicted type
* why it was predicted
* how uncertain cases are handled

## Exit criteria

I can explain:

* why routing should be early in the pipeline
* why heuristic routing is acceptable in an MVP
* how this routing would influence later extraction/summarisation strategies

## Interview reflection

* Why is explainable routing better than opaque routing early on?
* How would wrong document type prediction hurt downstream extraction?
* When would I replace heuristics with ML classification?

---

## 11. Phase 4 — Deterministic Extraction Track

## Goal

Add a clean deterministic extraction path separate from open-ended summarisation.

## Why this phase matters

Interviews often test whether I can separate exact fields from fuzzy narrative outputs. This is one of the most important distinctions in document intelligence.

## Read first

* `py/libs/data_model/src/data_model/extraction.py`
* `py/libs/ai_core/src/ai_core/summariser.py`
* `apps/py-api/py_api/api/documents.py`

## Tasks

### Module 4A — Define deterministic field schema

Start with fields like:

* document_type
* service_date
* provider_name
* total_amount
* claim_number
* patient_name

Not all fields need to work for all documents.

### Module 4B — Implement simple field extraction

Start with:

* regex
* keyword-window heuristics
* page-local scanning
* conservative confidence scoring

### Module 4C — Attach evidence correctly

Every field must carry:

* evidence chunk IDs or page references
* supporting snippet
* confidence
* extraction method

### Module 4D — Keep summarisation separate

Do not merge deterministic fields into the narrative summary implementation.
Keep the two paths distinct.

## Verification

Use documents where at least 2–3 fields can be extracted reliably.
Inspect:

* extracted value
* confidence
* evidence mapping
* failure cases

## Exit criteria

I can explain:

* why deterministic extraction should not be evaluated like summaries
* why conservative extraction is better than over-claiming
* how evidence enables faster human review

## Interview reflection

* Why is precision often more important than recall for some legal/medical fields?
* When would I intentionally return “not found” instead of guessing?
* How do deterministic fields improve downstream AI tasks?

---

## 12. Phase 5 — OCR-Ready Design Without Full OCR Explosion

## Goal

Make the repo OCR-aware and low-quality-document-aware.

## Why this phase matters

Interviewers love asking about scanned PDFs, bad OCR, or image-only documents.

## Read first

* `py/libs/di_core/src/di_core/parser.py`
* `py/libs/data_model/src/data_model/document.py`

## Tasks

### Module 5A — Add parse-quality signals

Add fields such as:

* native_text_extracted
* text_density
* likely_scanned
* likely_needs_ocr

### Module 5B — Add OCR adapter interface

Do not fully build a giant OCR system first.
Create an interface or stub for:

* local Tesseract adapter
* future AWS Textract adapter

### Module 5C — Add fallback decision logic

Define when the system would trigger OCR:

* zero native text
* too many empty pages
* extremely low text density

### Module 5D — Add explicit non-OCR fallback behavior

If OCR is unavailable locally, the system should return:

* clear warning
* parse quality status
* downstream limitation note

## Verification

Use a low-text PDF or fake scanned sample.
Verify:

* low-quality signals are set
* OCR need is identified
* system fails honestly instead of silently pretending success

## Exit criteria

I can explain:

* how OCR should fit into the pipeline
* how to avoid blocking the whole system on OCR
* why “honest degraded mode” is important

## Interview reflection

* When should OCR run synchronously vs asynchronously?
* Why should OCR be an adapter, not hardcoded into parser logic?
* How do OCR errors propagate into AI quality?

---

## 13. Phase 6 — Large Document Handling

## Goal

Design and implement the first large-document-safe behaviors.

## Why this phase matters

This is directly aligned with thousands-of-page PDFs and large-scale document workflows.

## Read first

* `py/libs/di_core/src/di_core/parser.py`
* `py/libs/di_core/src/di_core/chunker.py`
* `apps/py-api/py_api/api/documents.py`

## Tasks

### Module 6A — Add size-aware guards

Track:

* file size
* page count
* char count
* chunk count
* truncation decisions

### Module 6B — Add progressive processing strategy

Even if still synchronous, structure the code so the future path is obvious:

* parse pages incrementally
* avoid building unnecessary giant strings too early
* isolate expensive steps

### Module 6C — Add summarisation budget logic

Current summariser uses only early chunks.
Replace naive first-N chunk selection with a more explicit strategy:

* head chunks
* sampled chunks
* type/routing-aware chunk selection
* warning when summary is partial

### Module 6D — Add large-document debug reporting

Return or log:

* total pages
* total chunks
* chunks actually sent to LLM
* coverage estimate
* truncation or sampling policy used

## Verification

Use a larger synthetic or real document.
Inspect:

* memory behavior
* chunk count
* selected chunk count
* whether the system openly reports partial coverage

## Exit criteria

I can explain:

* why first-N chunk summarisation is dangerous
* how to preserve speed while being honest about coverage
* how large documents change DI system design

## Interview reflection

* How would I handle a 3,000-page PDF differently from a 10-page PDF?
* What should happen if the LLM context budget is much smaller than the document?
* Why is partial-coverage disclosure important for user trust?

---

## 14. Phase 7 — Retrieval-Oriented Document Intelligence

## Goal

Make the DI layer retrieval-ready even before building a full production RAG system.

## Why this phase matters

Strong document-intelligence interviews often bridge parsing/chunking into retrieval design.

## Read first

* `py/libs/di_core/src/di_core/chunker.py`
* `py/libs/data_model/src/data_model/document.py`
* `py/libs/data_model/src/data_model/extraction.py`

## Tasks

### Module 7A — Add retrieval metadata to chunks

Examples:

* doc type
* source filename
* page span
* section label if available
* route/category
* quality flags

### Module 7B — Add chunk ranking hooks

Do not implement a full vector DB yet.
Create interfaces for:

* lexical scoring
* heuristic salience scoring
* future embedding retrieval

### Module 7C — Add citation-ready evidence packaging

Make sure evidence can support:

* UI display
* reviewer inspection
* future RAG answer grounding

### Module 7D — Introduce section-awareness if feasible

Examples:

* headers
* page groups
* detected repeated billing patterns
* chronology sections

Keep this simple and inspectable.

## Verification

Select example queries or tasks and inspect:

* which chunks are likely relevant
* why they are relevant
* whether provenance is sufficient for future grounded answers

## Exit criteria

I can explain:

* how DI choices influence later RAG quality
* why metadata-rich chunks outperform plain raw text chunks
* why retrieval should prefer useful evidence instead of just “more text”

## Interview reflection

* How can domain knowledge influence retrieval without becoming brittle?
* Why might page-level metadata matter as much as embeddings?
* How do I reduce irrelevant retrieval in legal/medical scenarios?

---

## 15. Phase 8 — Evidence-Backed Summaries And Traceability

## Goal

Improve evidence support and traceability for narrative outputs.

## Why this phase matters

Evidence-backed summarisation is a core differentiator in trustworthy document AI.

## Read first

* `py/libs/ai_core/src/ai_core/summariser.py`
* `py/libs/data_model/src/data_model/extraction.py`
* `apps/web/app/page.tsx`

## Tasks

### Module 8A — Strengthen evidence binding

Ensure summary output contains:

* chunk IDs used
* page references
* supporting snippets
* explicit grounding coverage

### Module 8B — Distinguish summary from extracted facts

The summary should not pretend to be the same thing as deterministic fields.

### Module 8C — Add unsupported-claim safeguards

If the summary references facts not supported by chosen evidence, the system should:

* lower confidence
* mark a warning
* request review
* or refuse to claim certainty

### Module 8D — Add evidence coverage reporting

For every summary, record:

* how many chunks were available
* how many chunks were used
* what pages were covered
* whether the summary is likely partial

## Verification

Inspect a generated summary and ask:

* does every major claim have evidence?
* is evidence actually relevant?
* are unsupported or weakly-supported claims visible?

## Exit criteria

I can explain:

* why evidence-backed summaries are different from generic chat summaries
* how grounding reduces hallucination risk
* how evidence traceability helps paralegals or reviewers move faster

## Interview reflection

* What does “trustworthy summary” mean in a document workflow?
* Why is provenance a product feature, not just an engineering detail?
* How should the UI present evidence for human review?

---

## 16. Phase 9 — Evaluation For Document Intelligence

## Goal

Build the first honest evaluation harness for DI outputs.

## Why this phase matters

Evaluation is one of the highest-signal topics for applied AI + document intelligence interviews.

## Read first

* `py/libs/data_model/src/data_model/extraction.py`
* current deterministic extraction code
* current summarisation code

## Tasks

### Module 9A — Deterministic field evaluation

Create fixture-based scoring for:

* exact match
* normalized exact match
* tolerance-based numeric/date comparison
* precision / recall / F1 for extracted fields

### Module 9B — Summary evaluation dimensions

Do not use one metric.
Score summaries using multiple dimensions:

* factual coverage
* grounding/evidence support
* contradiction / unsupported claim count
* actionability
* semantic closeness if reference summaries exist

### Module 9C — Slice-based evaluation

Break evaluation down by:

* document type
* parse quality
* page count bucket
* file type
* likely_scanned vs native text

### Module 9D — DI system metrics

Track:

* parse latency
* chunking latency
* summarisation latency
* field extraction latency
* extraction failure rate
* evidence attachment rate

## Verification

Run evaluation on a small fixture set and produce:

* one deterministic metrics report
* one summary evaluation report
* one slice breakdown

## Exit criteria

I can explain:

* why average metrics are not enough
* why deterministic fields and summaries need separate evaluation methods
* how evaluation guides product decisions, not just model tuning

## Interview reflection

* How do I balance precision and recall for extracted fields?
* Why is latency part of DI quality, not separate from it?
* How do slice-based failures change roadmap priorities?

---

## 17. Phase 10 — Preprocessing And Postprocessing For Production Thinking

## Goal

Upgrade the DI pipeline from “demo behavior” toward “production thinking.”

## Why this phase matters

This is where prototype-level code starts to sound like real startup engineering.

## Read first

* parser code
* chunker code
* extraction code
* summariser code
* document/extraction schemas

## Tasks

### Module 10A — Preprocessing

Add explicit preprocessing stages such as:

* whitespace normalization
* repeated header/footer removal
* page text cleanup
* duplicate text suppression
* Unicode normalization

### Module 10B — Postprocessing

Add postprocessing for:

* field normalization
* date normalization
* currency normalization
* confidence clamping
* duplicate evidence cleanup

### Module 10C — Failure and retry semantics

Define which failures are:

* hard failures
* soft warnings
* review-needed outputs
* retryable processing failures

### Module 10D — Health and observability

Improve logs and status visibility for:

* parse stage
* chunk stage
* extraction stage
* summary stage
* low-quality document handling

## Verification

Run the same fixture set before and after preprocessing/postprocessing and compare:

* extraction cleanliness
* duplicate noise
* evidence quality
* failure transparency

## Exit criteria

I can explain:

* how preprocessing affects accuracy
* how postprocessing affects reliability and user trust
* why observability is part of DI design

## Interview reflection

* Which preprocessing steps are safe and which are risky?
* Why should postprocessing not silently “invent” corrections?
* What logs would I want during a large production incident?

---

## 18. Phase 11 — Human-In-The-Loop For Document Intelligence

## Goal

Design the first real HITL contract for document review.

## Why this phase matters

HITL is a major topic in document AI because human review is often required for high-stakes outputs.

## Read first

* document schemas
* extraction schemas
* UI rendering path
* evaluation ideas from Phase 9

## Tasks

### Module 11A — Reviewable output design

Design schemas to support:

* approved
* corrected
* rejected
* needs-review
* unsupported-claim

### Module 11B — Correction capture

Add a minimal correction record for:

* field corrections
* summary corrections
* evidence mismatch reports
* parse quality complaints

### Module 11C — Review queue thought model

Even if UI is minimal, define:

* what gets reviewed first
* what triggers review automatically
* what can be auto-accepted
* what is too risky to auto-accept

### Module 11D — Feedback loop design

Document how corrections would later influence:

* heuristics
* prompts
* retrieval
* evaluation
* future fine-tuning datasets

## Verification

Create at least one sample corrected output and show how the correction would be stored.

## Exit criteria

I can explain:

* why HITL is not just “humans fixing bad AI”
* how HITL improves trust, speed, and learning loops
* how review burden should be minimized with good DI design

## Interview reflection

* What should humans verify instead of rewrite?
* Which outputs should always be reviewed?
* How would I reduce reviewer workload over time?

---

## 19. Phase 12 — Scale Thought Exercise: 100k MAU / Millions Of Pages

## Goal

Practice scaling conversations starting from the repo I actually built.

## Why this phase matters

The interview may jump from code to large-scale system thinking very quickly.

## Tasks

This phase is mostly design discussion based on the repo.

### Module 12A — Separate synchronous vs asynchronous work

Define what remains synchronous:

* upload acknowledgement
* metadata creation

Define what must become asynchronous:

* parsing
* OCR
* embedding generation
* batch extraction
* evaluation

### Module 12B — Workerization roadmap

Map current code to future services:

* parser worker
* OCR worker
* extraction worker
* evaluation worker

### Module 12C — Storage roadmap

Map:

* local storage -> S3
* in-memory state -> Postgres
* local synchronous processing -> queue + workers
* simple chunk retrieval -> indexed retrieval

### Module 12D — Quality-at-scale risks

List:

* giant documents
* OCR noise
* repeated headers
* duplicate documents
* retrieval drift
* unsupported claims
* latency explosions
* evidence mismatches

## Deliverable

Write a short architecture note:

* current design
* first production evolution
* main bottlenecks
* first reliability protections

## Interview reflection

* What breaks first as volume grows?
* Which parts should scale horizontally?
* How would I preserve evidence traceability at scale?

---

## 20. Interview Drill Mode

After each completed phase, the agent must run a short drill with me.

## Drill structure

1. explain the problem in business terms
2. explain the current implementation
3. explain what changed
4. explain why it helps the user
5. explain tradeoffs
6. explain what breaks at scale
7. explain how to evaluate it

## Sample prompts

* Walk me through the current parsing pipeline.
* Why is your chunking design reasonable for an MVP?
* How would you handle scanned PDFs?
* How do you separate deterministic extraction from summarisation?
* How would you evaluate AI-generated medical or legal summaries?
* What would you change first for thousand-page PDFs?
* How would you make the output reviewable and trustworthy?

---

## 21. Recommended Build Order

Unless I explicitly override it, the agent should guide me in exactly this order:

1. Phase 0 — Baseline walkthrough
2. Phase 1 — Parser depth
3. Phase 2 — Chunking depth
4. Phase 3 — Document routing
5. Phase 4 — Deterministic extraction
6. Phase 5 — OCR-ready design
7. Phase 6 — Large-document handling
8. Phase 7 — Retrieval-oriented DI
9. Phase 8 — Evidence-backed summaries
10. Phase 9 — Evaluation
11. Phase 10 — Pre/postprocessing and observability
12. Phase 11 — HITL
13. Phase 12 — Scale thought exercise

Do not skip ahead unless I explicitly request it.

---

## 22. Definition Of Success

This document-intelligence track is successful if, by the end, I can do all of the following confidently:

* read and explain the existing repo’s DI flow quickly
* improve parsing and chunking without breaking the vertical slice
* discuss low-quality docs, OCR, and provenance clearly
* separate deterministic extraction from open-ended summarisation
* explain evidence-backed design decisions
* describe evaluation rigorously
* discuss HITL and productionization with good tradeoff awareness
* connect implementation details to user trust, business value, and scale

The goal is not just to build more code.

The goal is to become able to say:

**“I understand how to grow a small runnable document-intelligence demo into a production-oriented, evidence-backed, reviewable system — and I can explain every step clearly.”**

