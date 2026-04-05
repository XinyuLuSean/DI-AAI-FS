# AppliedAI

## 1. Goal

This file is the interview-oriented deep-dive plan for the **Applied AI** part of this repo.

I have already completed the Document Intelligence track.

Now the objective is to deepen the **Applied AI / LLM / evaluation / grounding / retrieval / productionization** side in a way that is:

- realistic for practical interviews
- built on top of the current runnable demo
- deployable step by step
- easy to explain from business, user, and engineering perspectives
- extensible toward a production-grade platform later

This plan is intentionally **phase-by-phase** and **module-by-module**.

The goal is not to randomly add AI buzzwords.

The goal is to become able to say:

**“I can take parsed document data, design an evidence-backed AI workflow around it, evaluate it honestly, and evolve it from a prototype into a production-oriented system.”**

---

## 2. Current Baseline

Before starting, assume the current repo already supports a small AI path:

`upload file -> parse -> chunk -> call summariser -> return structured extraction JSON -> render result with evidence in UI`

Current Applied AI baseline:

- one main AI task exists: summarisation
- the AI path is backend-driven
- structured response contracts already exist
- evidence references are already part of the UI flow
- the current AI behavior is still simple and MVP-level
- there is no retrieval stack yet
- there is no ranking stack yet
- there is no prompt versioning workflow yet
- there is no evaluation harness yet
- there is no HITL feedback loop yet
- there is no model/provider abstraction depth beyond the current summariser path
- there is no production monitoring for AI quality yet

This is correct as a starting point.

---

## 3. Files To Read First

Before every phase, re-read these files:

- `py/libs/ai_core/src/ai_core/summariser.py`
- `py/libs/data_model/src/data_model/extraction.py`
- `py/libs/data_model/src/data_model/document.py`
- `apps/py-api/py_api/api/documents.py`
- `apps/py-api/py_api/core/config.py`
- `apps/web/app/page.tsx`
- any current prompt-related or provider-related files inside `py/libs/ai_core/`

The agent must understand the current end-to-end AI flow before proposing changes.

---

## 4. How The Agent Must Guide Me

For this file, the agent must behave like a **practical AI systems mentor**, not a vague LLM advisor.

For every phase, the agent must do this:

1. explain the current state of the relevant code
2. explain why the next step matters for Applied AI
3. identify the smallest meaningful implementation step
4. tell me exactly which files to inspect
5. tell me exactly what commands to run
6. tell me how to verify the result locally
7. ask me to confirm completion before moving to the next phase
8. end each phase with interview-style reflection questions

The agent must optimize for:

- small runnable changes
- manual deployment
- evidence-backed AI behavior
- evaluation discipline
- strong business/user reasoning
- clear tradeoff explanations

The agent must **not** skip directly to giant frameworks or full production stacks.

---

## 5. Default Development Commands

Use these commands unless a phase explicitly changes them.

## 5.1 Setup

```bash
cp .env.example .env
uv sync
pnpm install
docker compose -f infra/compose/docker-compose.yml up postgres redis -d
```

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

## 6. Learning Rules For This Applied AI Track

1. Always build on the current runnable vertical slice.
2. Keep AI outputs structured and inspectable.
3. Prefer evidence-backed outputs over free-form output.
4. Separate deterministic extraction from open-ended generation.
5. Never discuss evaluation as a single score.
6. Prompting, retrieval, and postprocessing must all be observable.
7. Every AI change must be explainable in terms of user value and business value.
8. Every phase must produce something I can defend in an interview.

---

## 7. Phase 0 — Baseline Applied AI Walkthrough

## Goal

Fully understand the current AI execution path before changing anything.

## Why this phase matters

In an interview, if I cannot trace the current AI flow quickly, I will struggle to debug, improve, or defend it.

## Read first

- `py/libs/ai_core/src/ai_core/summariser.py`
- `apps/py-api/py_api/api/documents.py`
- `py/libs/data_model/src/data_model/extraction.py`
- `apps/web/app/page.tsx`

## Tasks

1. Trace the exact AI flow:
  - where chunks are selected
  - where prompt construction happens
  - where provider/model call happens
  - where structured response is validated
  - where evidence references are attached
  - where output is rendered
2. Write a short local note describing:
  - current AI task
  - current prompt shape
  - current model/provider assumptions
  - current evidence behavior
  - biggest current AI gaps

## Required deliverable

A short markdown note with:

- current AI flow diagram
- current limitations
- current strongest design choices
- current biggest Applied AI gaps

## Verification

Be able to answer:

- where the summariser gets its input
- whether it uses all chunks or a subset
- whether the output is schema-controlled
- where evidence references are assembled
- what makes the current AI path MVP-only

## Interview reflection

- Why is this small AI path a valid first step?
- What are the main hallucination risks in the current design?
- Why is evidence attachment already valuable even before retrieval exists?

---

## 8. Phase 1 — Prompt Design As A First-Class Interface

## Goal

Turn prompts into explicit, inspectable, versionable system components.

## Why this phase matters

Prompt design is one of the highest-signal applied AI topics in interviews, especially when paired with structured output and evidence requirements.

## Read first

- `py/libs/ai_core/src/ai_core/summariser.py`
- `py/libs/data_model/src/data_model/extraction.py`

## Tasks

### Module 1A — Isolate prompt construction

Move or cleanly organize prompt-building logic so it is clearly separate from:

- input preparation
- provider call
- output validation

### Module 1B — Add prompt metadata

Track at least:

- prompt name
- prompt version
- task type
- expected output schema
- model assumptions

### Module 1C — Make prompt goals explicit

Prompts should state:

- what task is being performed
- what evidence constraints apply
- what uncertainty behavior is expected
- what must not be guessed

### Module 1D — Add example-driven prompt sanity checks

Create at least one local prompt fixture or prompt test input/output pair.

## Verification

For one AI task, inspect:

- prompt text
- input chunks used
- output schema expected
- failure behavior if output is malformed

## Exit criteria

I can explain:

- why prompt construction should be explicit
- why prompt versioning matters
- how prompt design affects reliability and latency

## Interview reflection

- Why is prompt engineering an engineering discipline, not just trial and error?
- What happens when prompts are buried inside business logic?
- Why should the model be instructed to avoid unsupported claims?

---

## 9. Phase 2 — Structured Outputs And Schema Discipline

## Goal

Make structured output handling one of the strongest parts of the AI system.

## Why this phase matters

In production AI systems, structure is often what makes outputs usable, testable, and integrable with full-stack workflows.

## Read first

- `py/libs/data_model/src/data_model/extraction.py`
- current summariser output logic
- API response contracts

## Tasks

### Module 2A — Tighten output schemas

Ensure AI outputs use explicit schemas with:

- required vs optional fields
- confidence fields where appropriate
- evidence references
- warning/status fields

### Module 2B — Add validation and fallback handling

If the model returns malformed output:

- validate strictly
- classify the failure
- attempt controlled recovery if appropriate
- fail honestly if needed

### Module 2C — Separate field classes

Split outputs into:

- deterministic fields
- open-ended narrative fields
- evidence metadata
- warning/review fields

### Module 2D — Add schema contract fixtures

Create a small library of valid and invalid response examples.

## Verification

Run the system with:

- one valid output path
- one malformed model output simulation
- one low-confidence or partial case

Inspect whether the backend responds clearly and predictably.

## Exit criteria

I can explain:

- why schema-constrained AI outputs are necessary
- how structured outputs improve downstream debugging
- why deterministic and open-ended outputs should not be mixed

## Interview reflection

- Why is free-form model output dangerous in product systems?
- What should happen when validation fails?
- Why are warnings/review flags part of the output contract?

---

## 10. Phase 3 — Evidence-Backed Generation And Grounding

## Goal

Upgrade the AI layer so grounded generation becomes an explicit design principle, not an accidental side effect.

## Why this phase matters

Grounding, citation, hallucination control, and evidence traceability are central to high-stakes document AI systems.

## Read first

- `py/libs/ai_core/src/ai_core/summariser.py`
- extraction schemas
- UI evidence rendering path

## Tasks

### Module 3A — Make evidence usage explicit

Track:

- which chunks are sent to the model
- which chunks are cited in the output
- whether each major claim has supporting evidence

### Module 3B — Add unsupported-claim safeguards

If the model output contains claims not supported by provided evidence:

- mark warnings
- lower confidence
- require review
- or reject unsupported sections

### Module 3C — Add grounding metadata

For each AI result, store:

- chunk IDs used
- page references
- coverage notes
- evidence count
- grounding completeness or confidence

### Module 3D — Improve evidence packaging

Ensure evidence is useful for:

- UI display
- reviewer verification
- future retrieval/reranking
- auditability

## Verification

Inspect one generated summary and ask:

- are the main claims tied to evidence?
- are page references available?
- is the system honest when evidence is weak?

## Exit criteria

I can explain:

- why evidence-backed outputs matter for trust
- how grounding reduces hallucination risk
- why traceability is both a product and engineering concern

## Interview reflection

- What does “grounded output” mean in practice?
- How should the system behave when evidence is incomplete?
- Why is evidence traceability especially important in legal or medical workflows?

---

## 11. Phase 4 — Task Expansion: More Than Just Summarisation

## Goal

Expand the AI layer into multiple task types while keeping clean boundaries.

## Why this phase matters

Applied AI interviews often test whether I can generalize from one AI feature into a broader task framework.

## Read first

- summariser code
- current schema definitions
- current API routes

## Tasks

### Module 4A — Add task abstraction

Define a clean task layer for at least:

- summarisation
- case analysis
- structured extraction enhancement
- semantic matching
- document classification support

### Module 4B — Implement one new AI task

Choose one realistic next step, for example:

- chronology summary
- contradiction check
- evidence-backed issue extraction
- semantic similarity between summary and source chunks

### Module 4C — Keep task interfaces consistent

Each task should define:

- input contract
- prompt or scoring logic
- output schema
- evidence requirements
- evaluation method

### Module 4D — Avoid task sprawl

Do not add many half-baked AI tasks.
Prefer one clean new task that can be inspected and evaluated.

## Verification

Run at least two different AI tasks against the same document and inspect:

- input differences
- output schema differences
- evidence handling differences
- business usefulness differences

## Exit criteria

I can explain:

- how one AI platform supports multiple task types
- why task abstraction matters
- how task-specific evaluation differs

## Interview reflection

- Why should summarisation and case analysis be separate tasks?
- What makes a new AI task product-worthy instead of just technically interesting?
- How do task interfaces help scale development?

---

## 12. Phase 5 — Retrieval Foundations For Applied AI

## Goal

Lay the first retrieval-aware AI foundation without overbuilding a full RAG platform too early.

## Why this phase matters

RAG design details are highly interviewable, especially when connected to long documents and evidence-backed outputs.

## Read first

- chunk metadata structures
- current AI input preparation logic
- any retrieval-adjacent code or data models

## Tasks

### Module 5A — Add retrieval-oriented chunk metadata

Ensure chunk metadata is rich enough for retrieval:

- doc type
- page span
- source file
- parse quality flags
- routing/category information
- section hints if available

### Module 5B — Add a retrieval interface

Define a clean abstraction for:

- lexical retrieval
- metadata filtering
- future embedding retrieval
- future reranking

### Module 5C — Start with simple retrieval

Before vector search, implement something small and inspectable, such as:

- keyword filtering
- metadata-aware chunk selection
- heuristic salience ranking

### Module 5D — Compare retrieval input strategies

For one task, compare:

- first-N chunks
- keyword-selected chunks
- metadata-filtered chunks
- simple ranked chunks

## Verification

Use a query or task and inspect:

- selected chunks
- why they were selected
- whether they are more relevant than naive first-N selection

## Exit criteria

I can explain:

- why retrieval quality starts before embeddings
- why chunk metadata matters
- why naive first-N context is dangerous for long documents

## Interview reflection

- Why is retrieval design part of Applied AI, not just infra?
- How can domain knowledge shape retrieval without making it brittle?
- Why can a simple retriever be better than a bad vector search?

---

## 13. Phase 6 — Embeddings, Vector Retrieval, And Reranking

## Goal

Introduce modern retrieval components in a controlled and explainable way.

## Why this phase matters

This is one of the most likely Applied AI discussion areas in interviews.

## Read first

- retrieval interface from Phase 5
- chunk metadata models
- storage/repo design constraints

## Tasks

### Module 6A — Add embedding adapter interface

Hide embedding/provider logic behind a small internal interface.

### Module 6B — Add a small vector index path

Start simple:

- local prototype index
- or Postgres/pgvector-compatible design if already convenient

### Module 6C — Add reranking hook

Add a clear stage after initial retrieval:

- heuristic reranker
- cross-encoder reranker
- provider reranker
- or simple score-combining reranker

### Module 6D — Compare retrieval pipelines

Compare:

1. naive first-N chunks
2. lexical retrieval
3. vector retrieval
4. vector + rerank
5. metadata filter + vector + rerank

## Verification

Choose one realistic question or analysis task and inspect:

- retrieved chunk relevance
- evidence quality
- latency tradeoffs
- token budget efficiency

## Exit criteria

I can explain:

- what embeddings are doing in this system
- why reranking is useful
- how retrieval and latency trade off against each other

## Interview reflection

- Why is vector retrieval alone often not enough?
- Why can reranking improve both relevance and grounding?
- How should I think about cost, latency, and quality together?

---

## 14. Phase 7 — Long-Context And Large-Document AI Strategy

## Goal

Design and implement better AI behavior for very long documents.

## Why this phase matters

Handling long PDFs and large document sets is a direct interview topic.

## Read first

- current summariser input logic
- retrieval logic
- document/chunk metadata

## Tasks

### Module 7A — Replace naive context selection

Stop relying on a naive early-chunk strategy.
Introduce a more explicit strategy:

- retrieve relevant chunks
- diversify selected evidence
- sample across pages or sections when needed
- disclose coverage limits

### Module 7B — Add coverage-aware AI input preparation

Track:

- total chunks available
- chunks selected
- page coverage
- whether the output is partial
- why those chunks were selected

### Module 7C — Add hierarchical AI strategy

Design for:

- chunk-level analysis
- section-level aggregation
- document-level synthesis

This can be simple at first.

### Module 7D — Add long-document warnings

If context coverage is partial, the output should say so explicitly.

## Verification

Use a longer document and inspect:

- how chunks are selected
- whether selection is more meaningful than first-N
- whether output discloses partial coverage

## Exit criteria

I can explain:

- how to keep AI focused on long documents
- why coverage awareness matters
- how hierarchical summarisation improves reliability

## Interview reflection

- What breaks first with thousand-page PDFs?
- Why is it dangerous to pretend full coverage when only part of the document was used?
- How do retrieval and summarisation interact in long-context systems?

---

## 15. Phase 8 — Classification, Clustering, And Semantic Matching

## Goal

Use structured document outputs as the basis for broader Applied AI tasks beyond generation.

## Why this phase matters

The JD-style scope for an Applied AI platform includes classification, clustering, and semantic matching, not just chat-like summarisation.

## Read first

- document metadata models
- chunk metadata models
- deterministic extraction outputs
- retrieval pipeline

## Tasks

### Module 8A — Classification

Implement one useful classification task, for example:

- document category classification
- urgency classification
- review-needed classification
- low-quality-document classification

### Module 8B — Semantic matching

Implement one matching task, for example:

- summary-to-source alignment
- extracted fact to evidence alignment
- duplicate or near-duplicate chunk matching
- related document matching

### Module 8C — Clustering thought path

Start simple:

- chunk/topic grouping
- document similarity grouping
- case material grouping

Do not overbuild this phase.

### Module 8D — Reuse structured outputs

Design these tasks using:

- chunk metadata
- deterministic fields
- parse-quality signals
- embeddings or simple similarity signals

## Verification

Run at least one classification and one semantic-matching example.
Inspect:

- input features
- chosen method
- explainability
- business usefulness

## Exit criteria

I can explain:

- how Applied AI extends beyond generation
- how structured data improves AI task quality
- why matching/classification may be more reliable than free-form generation in some workflows

## Interview reflection

- When is classification better than generation?
- Why is semantic matching useful for review or QA?
- How can clustering help in document-heavy workflows?

---

## 16. Phase 9 — Evaluation: Deterministic Facts vs Open-Ended Outputs

## Goal

Build a real evaluation discipline for the Applied AI layer.

## Why this phase matters

This is one of the most important high-signal discussion areas in interviews.

## Read first

- extraction schemas
- AI task outputs
- current prompt and retrieval logic

## Tasks

### Module 9A — Deterministic evaluation

For exact or near-exact fields, score:

- exact match
- normalized exact match
- tolerance-based match
- precision / recall / F1
- field-level slice reports

### Module 9B — Open-ended evaluation

For summaries and case analysis, evaluate along multiple dimensions:

- factual coverage
- grounding/evidence support
- contradiction count
- unsupported claim count
- semantic closeness if references exist
- actionability for end users

### Module 9C — Retrieval-aware evaluation

For AI tasks that depend on retrieval, separately evaluate:

- retrieval relevance
- evidence usefulness
- answer grounding
- retrieval latency
- token efficiency

### Module 9D — Slice-based analysis

Break results down by:

- document type
- parse quality
- page count bucket
- low-text vs clean text
- task type
- model/prompt version

## Verification

Run a small fixture-based evaluation and produce:

- one deterministic report
- one summary or case-analysis report
- one slice breakdown
- one retrieval-aware comparison if relevant

## Exit criteria

I can explain:

- why one AI score is not enough
- why deterministic and open-ended tasks need different metrics
- how evaluation informs roadmap decisions

## Interview reflection

- Why is balancing precision and recall task-dependent?
- Why should latency be part of evaluation?
- Why are slice failures often more valuable than average scores?

---

## 17. Phase 10 — Prompt Optimization And Experiment Tracking

## Goal

Turn prompt iteration from ad hoc tweaking into a clean experimental workflow.

## Why this phase matters

Interviews often probe whether prompt optimization is disciplined or just random.

## Read first

- prompt structures
- evaluation code
- current config/model selection logic

## Tasks

### Module 10A — Prompt registry

Create a small registry for:

- prompt name
- prompt version
- task
- model
- expected schema
- notes

### Module 10B — Controlled comparison workflow

Make it easy to compare:

- prompt A vs prompt B
- model A vs model B
- retrieval strategy A vs B
- evidence packaging A vs B

### Module 10C — Log experiment metadata

Track:

- task type
- prompt version
- model version
- retrieval configuration
- latency
- output validity
- evaluation scores

### Module 10D — Stop “prompt drift”

Ensure it is always clear which prompt configuration produced which result.

## Verification

Run at least one controlled comparison and inspect:

- what changed
- what improved
- what got worse
- whether the tradeoff is worth it

## Exit criteria

I can explain:

- how prompt optimization should be run like an experiment
- why logging prompt/model versions matters
- how to avoid untraceable prompt drift

## Interview reflection

- What makes a prompt experiment trustworthy?
- Why can a “better sounding” output still be a worse product result?
- How do I optimize for business value instead of aesthetics?

---

## 18. Phase 11 — Hallucination Control, Uncertainty, And Safe Failure

## Goal

Design safer AI behavior for uncertain, incomplete, or weak-evidence cases.

## Why this phase matters

High-stakes AI systems are judged heavily on how they fail, not just how they succeed.

## Read first

- output schema
- evidence handling logic
- evaluation reports
- current error/fallback behavior

## Tasks

### Module 11A — Add uncertainty behaviors

Teach the system to:

- abstain
- mark low confidence
- request review
- signal partial evidence coverage
- distinguish unknown from inferred

### Module 11B — Add unsupported-claim detection workflow

Create one explicit workflow for:

- unsupported summary claims
- contradictions with deterministic fields
- missing critical evidence

### Module 11C — Add safe degradation paths

If retrieval is weak, or parse quality is poor, the system should:

- narrow scope
- return partial result
- return review-needed output
- avoid high-confidence claims

### Module 11D — Surface risk clearly

Add fields such as:

- confidence
- evidence sufficiency
- partial coverage
- review recommended
- likely low-quality source

## Verification

Create one deliberately weak-evidence case and inspect whether the system degrades honestly.

## Exit criteria

I can explain:

- why abstention is sometimes better than generation
- how uncertainty should be surfaced
- why safe failure is part of product trust

## Interview reflection

- When should the system refuse to answer?
- Why is overconfident wrong output worse than incomplete output?
- How do uncertainty and user trust relate?

---

## 19. Phase 12 — Human-In-The-Loop For Applied AI

## Goal

Design the AI layer so it works with reviewers instead of pretending they do not exist.

## Why this phase matters

HITL is central for high-stakes document workflows.

## Read first

- AI output schemas
- evaluation outputs
- document-review concepts from the DI track
- UI output rendering path

## Tasks

### Module 12A — Reviewable AI output design

Outputs should support:

- approve
- correct
- reject
- unsupported claim
- missing evidence
- needs-review

### Module 12B — Capture feedback usefully

For each corrected output, capture:

- what was wrong
- what type of failure it was
- whether retrieval, prompt, parse quality, or schema caused it
- what evidence should have been used

### Module 12C — Review prioritization logic

Define which AI outputs should be reviewed first:

- low confidence
- partial coverage
- weak evidence
- critical document types
- unusual extracted values

### Module 12D — Feedback-to-improvement mapping

Document how feedback can later improve:

- prompts
- retrieval
- chunking
- deterministic extraction
- evaluation data
- fine-tuning data

## Verification

Create at least one corrected AI output example and show how the system would store and classify the feedback.

## Exit criteria

I can explain:

- why HITL should focus on verification and correction, not full rewrites
- how feedback loops improve AI quality over time
- how to reduce reviewer burden without lowering trust

## Interview reflection

- What should humans validate instead of rewrite?
- Which outputs should always be reviewed?
- How should feedback be turned into system improvement?

---

## 20. Phase 13 — From Prototype To Production Applied AI

## Goal

Practice productionization thinking for the AI layer based on the code I actually built.

## Why this phase matters

Interviews often jump from “show me the code” to “how would this run at scale?”

## Tasks

### Module 13A — Separate synchronous vs asynchronous AI work

Define what remains synchronous:

- user-triggered small response requests
- fast retrieval and summarisation if feasible

Define what becomes asynchronous:

- batch extraction
- embedding generation
- reranking prep
- evaluation jobs
- regression runs
- long-document processing

### Module 13B — Model serving and provider strategy

Document:

- when to use external LLM APIs
- when to cache results
- when to add adapters
- where model/provider switching belongs
- how to isolate vendor-specific behavior

### Module 13C — Reliability at scale

Define:

- timeouts
- retries/backoff
- idempotency
- concurrency guards
- queue boundaries
- degraded-mode behavior

### Module 13D — Observability

Track:

- model latency
- retrieval latency
- generation latency
- output validity rate
- grounding failure rate
- unsupported-claim rate
- review-needed rate
- provider error rate

## Deliverable

Write a short architecture note describing:

- current prototype AI path
- first production evolution
- biggest bottlenecks
- biggest failure risks
- first monitoring dashboard ideas

## Exit criteria

I can explain:

- how to evolve the current AI system toward production
- what should move async first
- what should be monitored first
- what reliability safeguards matter most

## Interview reflection

- What breaks first as traffic and document volume grow?
- Which metrics would I put on the first production dashboard?
- Why is reliability part of AI quality?

---

## 21. Interview Drill Mode

After each completed phase, the agent must run a short drill with me.

## Drill structure

1. explain the business problem
2. explain the current implementation
3. explain what changed
4. explain why it helps users
5. explain the tradeoffs
6. explain failure modes
7. explain how it should be evaluated
8. explain how it would change at scale

## Sample prompts

- Walk me through your current summarisation pipeline.
- How do you keep AI outputs evidence-backed?
- Why do deterministic fields and summaries need different evaluation methods?
- How would you improve retrieval for long PDFs?
- How do you decide whether to abstain, warn, or answer?
- How would you compare two prompts fairly?
- What does HITL look like in this system?
- How would you productionize this Applied AI layer?

---

## 22. Recommended Build Order

Unless I explicitly override it, the agent should guide me in exactly this order:

1. Phase 0 — Baseline Applied AI walkthrough
2. Phase 1 — Prompt design
3. Phase 2 — Structured outputs
4. Phase 3 — Evidence-backed grounding
5. Phase 4 — Task expansion
6. Phase 5 — Retrieval foundations
7. Phase 6 — Embeddings, vector retrieval, reranking
8. Phase 7 — Long-context strategy
9. Phase 8 — Classification, clustering, semantic matching
10. Phase 9 — Evaluation
11. Phase 10 — Prompt optimization and experiment tracking
12. Phase 11 — Hallucination control and uncertainty
13. Phase 12 — HITL for Applied AI
14. Phase 13 — Prototype to production AI

Do not skip ahead unless I explicitly request it.

---

## 23. Definition Of Success

This Applied AI track is successful if, by the end, I can do all of the following confidently:

- trace the current AI flow through the repo quickly
- explain prompt design as an engineering interface
- enforce structured outputs and validation clearly
- make outputs evidence-backed and reviewable
- design and compare retrieval strategies thoughtfully
- explain embeddings and reranking without hand-waving
- separate deterministic and open-ended evaluation rigorously
- reason about uncertainty, hallucination control, and abstention
- connect HITL to trust and continuous improvement
- explain how to evolve the AI layer from local prototype to production

The goal is not just to add more LLM code.

The goal is to become able to say:

**“I understand how to turn parsed documents into reliable, grounded, structured AI outputs — and I can evaluate, debug, and productionize that system with clear tradeoff reasoning.”**