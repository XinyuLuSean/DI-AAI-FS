# Applied AI Phases

This file maps the Applied AI curriculum in `AppliedAI.md` to the current codebase.

The goal is not to restate the learning plan word-for-word. The goal is to show how each phase is currently represented in the repo and how the pieces connect in practice.

Pair this with `docs/architecture/DI_Map.md` for the baseline AI execution path and `docs/applied-ai/AI_Scale.md` for the productionization follow-through.

## Phase 0 - Baseline Applied AI Walkthrough

### Goal

Understand the current AI execution path end to end before optimizing or extending it.

### Why Matters

Applied AI work is mostly systems work. You need to know where chunks come from, where prompts are built, where validation happens, and where evidence is attached.

### Implementations at codebase

- `docs/architecture/DI_Map.md` already documents the baseline AI flow.
- `py/libs/ai_core/src/ai_core/summariser.py` is the main AI orchestration path.
- `apps/py-api/py_api/api/documents.py -> summarise()` wires the API request to the summariser.
- `py/libs/data_model/src/data_model/extraction.py` holds the structured AI output contracts.
- `apps/web/components/extraction-result.tsx` renders grounding, evidence, and summary output.

### How to Evaluate

- Run a grounded summary from the UI after deterministic extraction.
- Inspect the request and response through `/documents/{id}/summarise`.
- Relevant tests: `tests/smoke/test_prompt_templates.py`, `tests/smoke/test_output_validation.py`.

### Exit Criteria

- You can explain chunk selection, prompt building, provider call, validation, evidence packaging, and UI rendering.

### Interview Reflections

- Why is the current AI path small but valid?
- Where are the main hallucination risks in the baseline?
- Why is evidence already a first-class citizen?

## Phase 1 - Prompt Design As A First-Class Interface

### Goal

Treat prompts as explicit, versioned system components instead of inline strings.

### Why Matters

Prompt quality is not just copywriting. It is contract design, observability, version control, and experimentability.

### Implementations at codebase

- `py/libs/ai_core/src/ai_core/prompts.py` defines `PromptTemplate`, `TaskType`, prompt registry entries, prompt metadata, and prompt builders.
- `SUMMARISE_V1`, `SUMMARISE_V1_1`, `GROUNDED_SUMMARISE_V1`, `GROUNDED_SUMMARISE_V1_1`, and `CHRONOLOGY_V1` are registered prompt templates.
- `py/libs/ai_core/src/ai_core/summariser.py` resolves prompt templates instead of building inline prompt text.
- `apps/py-api/py_api/api/documents.py -> summarise()` allows prompt lookup by name and version.

### How to Evaluate

- Inspect prompt registry contents with `get_prompt()` or `list_prompt_registry()`.
- Run summary with different prompt versions.
- Relevant tests: `tests/smoke/test_prompt_templates.py`.

### Exit Criteria

- Prompts are discoverable, versionable, and tied to result metadata.
- Prompt goals, evidence requirements, uncertainty instructions, and guardrails are explicit.

### Interview Reflections

- Why should prompt metadata live next to prompt text?
- What is the value of prompt versioning before large-scale experimentation?
- What makes a prompt a system interface rather than a string constant?

## Phase 2 - Structured Outputs And Schema Discipline

### Goal

Make AI outputs schema-controlled, validated, and recoverable when partially malformed.

### Why Matters

Most production AI failures are contract failures. Structured output validation is one of the highest-signal signs of real applied AI discipline.

### Implementations at codebase

- `py/libs/ai_core/src/ai_core/validation.py` defines `ValidationStatus`, `ValidationIssue`, `ValidationResult`, and task-specific schema models.
- `validate_summarisation_output()` performs strict validation plus partial recovery for non-critical issues.
- `validate_chronology_output()` does the same for chronology extraction.
- `py/libs/ai_core/src/ai_core/summariser.py` and `chronology.py` attach validation status and warnings to `ExtractionResult`.
- `apps/web/components/extraction-result.tsx` renders validation warning banners.

### How to Evaluate

- Run validation against malformed fixture outputs.
- Check how missing or malformed fields are classified.
- Relevant tests: `tests/smoke/test_output_validation.py`, `tests/smoke/test_task_expansion_phase4.py`.

### Exit Criteria

- Wrong-shaped output fails clearly.
- Recoverable output is accepted with warnings rather than silently normalized away.

### Interview Reflections

- Why is partial recovery better than binary success or failure?
- What output issues are safe to recover from?
- Why should validation warnings be visible to users or reviewers?

## Phase 3 - Evidence-Backed Generation And Grounding

### Goal

Bind generated claims to source evidence and explicitly audit grounding quality.

### Why Matters

Grounding is the main trust mechanism in this repo's AI stack. It is how the system distinguishes "useful summary" from "unsupported narrative."

### Implementations at codebase

- `py/libs/ai_core/src/ai_core/grounding.py` audits grounding, enriches key points with snippets and pages, and builds evidence gap analysis.
- `py/libs/ai_core/src/ai_core/summariser.py` applies grounding audit, safeguards, evidence gap analysis, and grounding coverage.
- `py/libs/di_core/src/di_core/evidence.py` turns cited chunks into evidence references.
- `py/libs/data_model/src/data_model/extraction.py` defines `GroundedKeyPoint`, `GroundingAudit`, and `EvidenceGapAnalysis`.
- `apps/web/components/extraction-result.tsx` renders grounding, evidence gap, and coverage.

### How to Evaluate

- Run grounded summarisation and inspect grounded versus ungrounded key points.
- Verify hallucinated chunk IDs are rejected from evidence packaging.
- Relevant tests: `tests/smoke/test_grounding_phase3.py`, `tests/smoke/test_evidence_grounding.py`.

### Exit Criteria

- The system can quantify grounding quality and surface unsupported claims.
- Per-claim evidence is available for review and debugging.

### Interview Reflections

- What is the difference between citation presence and true grounding?
- Why is post-LLM audit still needed even with a strong prompt?
- How would you explain grounding score limitations to stakeholders?

## Phase 4 - Task Expansion: More Than Just Summarisation

### Goal

Show that the AI platform can support multiple task types, not just one summary flow.

### Why Matters

A real Applied AI platform is reusable infrastructure plus task-specific logic. This phase proves the stack is extensible.

### Implementations at codebase

- `py/libs/ai_core/src/ai_core/task.py` defines the shared `AITask` abstraction and orchestration pattern.
- `py/libs/ai_core/src/ai_core/chronology.py` is the second AI task, parallel to summarisation.
- `py/libs/ai_core/src/ai_core/prompts.py` contains chronology prompt template and builder.
- `apps/py-api/py_api/api/documents.py -> chronology()` exposes chronology extraction over HTTP.
- `py/libs/data_model/src/data_model/extraction.py` defines `ChronologyEvent` and `ChronologyResult`.

### How to Evaluate

- Run `POST /documents/{id}/chronology` on a date-rich fixture.
- Compare chronology output shape to summary output shape.
- Relevant tests: `tests/smoke/test_task_expansion_phase4.py`.

### Exit Criteria

- The repo has at least two distinct AI tasks with shared infrastructure and different output contracts.

### Interview Reflections

- What should be shared across AI tasks versus task-specific?
- Why is chronology evaluation different from summary evaluation?
- How do you keep task sprawl from becoming architecture sprawl?

## Phase 5 - Retrieval Foundations For Applied AI

### Goal

Replace naive first-N chunk selection with explicit, inspectable retrieval strategies.

### Why Matters

Retrieval quality often dominates answer quality for document AI. This phase starts making context selection intentional.

### Implementations at codebase

- `py/libs/di_core/src/di_core/chunk_selector.py` implements positional, routing-aware, query-ranked, and diversified chunk selection.
- `py/libs/di_core/src/di_core/retrieval_compare.py` compares strategy outputs and recommends a strategy.
- `py/libs/di_core/src/di_core/ranker.py` provides salience and lexical scoring.
- `apps/py-api/py_api/api/documents.py -> retrieval_compare()` exposes retrieval strategy comparison.
- `apps/web/components/retrieval-compare.tsx` visualizes strategy overlap and differences.

### How to Evaluate

- Compare head versus query-ranked versus diversified on the same query.
- Inspect strategy overlap, unique chunks, and average relevance.
- Relevant tests: `tests/smoke/test_retrieval_phase5.py`, `tests/smoke/test_retrieval.py`.

### Exit Criteria

- Retrieval selection is explicit and debuggable.
- The system can show why one selection strategy may be better than another.

### Interview Reflections

- Why is first-N selection often a misleading baseline?
- Why is retrieval comparison UX valuable in an internal AI platform?
- How do you tell whether retrieval improvements actually matter downstream?

## Phase 6 - Embeddings, Vector Retrieval, And Reranking

### Goal

Add embedding-based retrieval and hybrid reranking behind clean interfaces.

### Why Matters

This is where lexical retrieval evolves into semantic retrieval. The important design choice is not just "use embeddings" but "keep embedding concerns isolated and testable."

### Implementations at codebase

- `py/libs/ai_core/src/ai_core/embedding.py` defines embedding provider abstractions and a deterministic hash embedding adapter.
- `py/libs/di_core/src/di_core/vector_index.py` provides an in-memory vector index.
- `py/libs/di_core/src/di_core/reranker.py` adds vector ranking, hybrid retrieval, and score fusion.
- `py/libs/di_core/src/di_core/retrieval_compare.py -> compare_with_hybrid()` includes vector and hybrid strategies.
- `apps/web/components/retrieval-compare.tsx` can enable vector plus hybrid comparison.

### How to Evaluate

- Run retrieval comparison with `include_hybrid=true`.
- Inspect vector and hybrid relevance against positional baselines.
- Relevant tests: `tests/smoke/test_embeddings_phase6.py`.

### Exit Criteria

- Semantic retrieval exists behind provider and index boundaries.
- Hybrid retrieval can be demonstrated without external vector infrastructure.

### Interview Reflections

- Why is a simple in-memory vector index still useful for learning and architecture work?
- Why does hybrid retrieval often beat single-signal retrieval?
- What would need to change first to productionize the vector path?

## Phase 7 - Long-Context And Large-Document AI Strategy

### Goal

Make the AI layer honest and effective on large documents where full context is impossible.

### Why Matters

Most real documents exceed practical context budgets. The important skill is designing around that constraint rather than pretending it does not exist.

### Implementations at codebase

- `py/libs/di_core/src/di_core/coverage.py` quantifies selected-context coverage and generates disclosure text.
- `py/libs/di_core/src/di_core/chunk_selector.py` builds budget-aware `SummarisationMeta`.
- `py/libs/ai_core/src/ai_core/hierarchical.py` implements hierarchical map-reduce summarisation.
- `py/libs/ai_core/src/ai_core/summariser.py` injects coverage disclosure into the prompt when coverage is partial.
- `apps/web/components/extraction-result.tsx` shows coverage report and partial-coverage warnings.

### How to Evaluate

- Compare standard summarisation and hierarchical summarisation on a long fixture.
- Inspect `coverage_report`, `summarisation_meta`, and warnings.
- Relevant tests: `tests/smoke/test_long_context_phase7.py`.

### Exit Criteria

- The model is told when it is operating on partial context.
- There is a separate long-document strategy rather than only increasing `max_chunks`.

### Interview Reflections

- Why is coverage disclosure important for trustworthy AI behavior?
- What tradeoff does hierarchical summarisation make?
- When is sampled context good enough, and when is it not?

## Phase 8 - Classification, Clustering, And Semantic Matching

### Goal

Expand beyond free-form generation into explainable AI tasks that support operations and QA.

### Why Matters

Applied AI is not only about generation. Classification and matching are often more operationally useful and more reliable.

### Implementations at codebase

- `py/libs/di_core/src/di_core/semantic.py -> classify_document_readiness()` provides explainable readiness classification.
- `semantic.py -> align_extracted_fields_to_chunks()` provides semantic fact-to-evidence matching.
- `py/libs/data_model/src/data_model/extraction.py` defines classification and semantic matching result contracts.
- `apps/py-api/py_api/api/documents.py` exposes `/classify` and `/semantic-match`.
- `apps/web/app/page.tsx` and `apps/web/components/extraction-result.tsx` render both tasks.

### How to Evaluate

- Run readiness classification after deterministic extraction.
- Run semantic matching on extracted fields and inspect matched versus unmatched facts.
- Relevant tests: `tests/smoke/test_phase8_classification_matching.py`.

### Exit Criteria

- The repo demonstrates at least one non-generative AI task and one evidence-alignment task.
- Outputs remain structured and explainable.

### Interview Reflections

- Why is an explainable classifier often more useful than a generative model?
- Why align deterministic fields back to chunks?
- Where would clustering be useful later even though this repo keeps it lightweight?

## Phase 9 - Evaluation: Deterministic Facts Vs Open-Ended Outputs

### Goal

Evaluate deterministic extraction, retrieval, and AI generation with the right metrics for each.

### Why Matters

Applied AI evaluation should match task type. Precision/recall for fields is not the same as factual coverage and grounding for summaries.

### Implementations at codebase

- `py/libs/di_eval/src/di_eval/field_eval.py` scores deterministic fields.
- `py/libs/di_eval/src/di_eval/summary_eval.py` scores summary coverage, grounding, contradictions, evidence support, and actionability.
- `py/libs/di_eval/src/di_eval/retrieval_eval.py` measures retrieval lift and overlap.
- `py/libs/di_eval/src/di_eval/slice_eval.py` aggregates metrics by slice.
- `py/libs/di_eval/src/di_eval/runner.py` runs evaluation through the real API stack.

### How to Evaluate

- Run the evaluation suite against `data/fixtures/ground_truth.json`.
- Review different metrics by task and by slice.
- Relevant tests: `tests/eval/test_field_eval.py`, `tests/eval/test_retrieval_eval.py`, `tests/eval/test_evaluation_run.py`.

### Exit Criteria

- Different task types have different evaluation dimensions.
- Evaluation is fixture-based and repeatable.

### Interview Reflections

- Why is "single score" evaluation misleading?
- How do you connect retrieval metrics to answer quality?
- Why should evaluation use the real API path when possible?

## Phase 10 - Prompt Optimization And Experiment Tracking

### Goal

Compare prompt, model, and retrieval variants in a controlled, structured way.

### Why Matters

Prompt work becomes engineering only when variants can be compared and explained systematically.

### Implementations at codebase

- `py/libs/di_eval/src/di_eval/experiment.py` defines experiment variants, rows, and side-by-side comparisons.
- `py/libs/ai_core/src/ai_core/prompts.py` supports multiple prompt versions.
- `py/libs/data_model/src/data_model/extraction.py -> ExperimentMeta` stores prompt/model/retrieval metadata on outputs.
- `py/libs/ai_core/src/ai_core/summariser.py` fills `ExperimentMeta` on summary outputs.

### How to Evaluate

- Run summary experiments with different prompt versions or chunk strategies.
- Compare factual coverage, grounding, evidence support, and latency across rows.
- Relevant tests: `tests/smoke/test_prompt_experiments_phase10.py`.

### Exit Criteria

- Prompt experiments are represented as structured comparisons, not anecdotal notes.
- AI outputs keep enough metadata to support experiment audit and replay.

### Interview Reflections

- Why does experiment tracking need more than prompt text?
- Which dimensions matter most when comparing prompt variants?
- Why is latency part of prompt optimization, not just quality?

## Phase 11 - Hallucination Control, Uncertainty, And Safe Failure

### Goal

Make the system degrade safely when evidence, parse quality, or validation is weak.

### Why Matters

This is one of the clearest markers of mature Applied AI work. A trustworthy system knows when not to overstate.

### Implementations at codebase

- `py/libs/ai_core/src/ai_core/safety.py` builds `UncertaintyAssessment`, detects contradictions, and applies safe summary degradation.
- `py/libs/ai_core/src/ai_core/summariser.py` integrates uncertainty assessment and abstention logic into final summary assembly.
- `py/libs/data_model/src/data_model/extraction.py` stores uncertainty metadata on AI outputs.
- `apps/web/components/extraction-result.tsx` renders uncertainty-related panels.
- `apps/py-api/py_api/api/documents.py` returns typed `503` responses for provider failures.

### How to Evaluate

- Force weak grounding or provider failure and inspect degraded output or degraded-mode response.
- Review uncertainty flags and abstention behavior.
- Relevant tests: `tests/smoke/test_safe_failure_phase11.py`.

### Exit Criteria

- The AI layer can recommend review, flag weak evidence, and degrade output instead of pretending confidence.
- Provider failure returns structured degraded-mode responses.

### Interview Reflections

- Why is abstention often better than forcing a confident answer?
- What should trigger review versus hard failure?
- How do contradiction warnings complement grounding checks?

## Phase 12 - Human-In-The-Loop For Applied AI

### Goal

Use review and correction workflows to close the loop on AI quality issues.

### Why Matters

Applied AI systems improve when reviewer actions are captured as structured learning signals, not only as one-off fixes.

### Implementations at codebase

- `py/libs/data_model/src/data_model/review.py` captures summary corrections, evidence mismatch reports, parse complaints, and feedback signals.
- `py/libs/di_core/src/di_core/review_queue.py` maps reviewer corrections back to improvement categories.
- `apps/py-api/py_api/api/documents.py` exposes correction and feedback endpoints.
- `apps/web/app/review/page.tsx` and `apps/web/components/review-panel.tsx` provide the review interface.

### How to Evaluate

- Submit review decisions and corrections from the UI.
- Inspect stored correction payloads and generated feedback signals.
- Relevant tests: `tests/smoke/test_hitl.py`.

### Exit Criteria

- AI outputs are reviewable and correctable with structured feedback.
- Corrections can inform prompts, retrieval, parsing, or evaluation fixtures later.

### Interview Reflections

- Why should feedback signals classify likely failure source?
- Why not auto-apply human corrections into live outputs?
- Which kinds of reviewer feedback are highest value for model/system improvement?

## Phase 13 - From Prototype To Production Applied AI

### Goal

Harden the AI path with operational visibility, retry behavior, degraded-mode handling, and a clear sync-to-async evolution path.

### Why Matters

Production Applied AI is as much about reliability and observability as about output quality.

### Implementations at codebase

- `docs/applied-ai/AI_Scale.md` describes the productionization direction.
- `py/libs/ai_core/src/ai_core/adapter.py` centralizes provider timeouts, retries, and typed provider failures.
- `py/libs/ai_core/src/ai_core/ops.py` records in-memory AI ops metrics.
- `apps/py-api/py_api/api/health.py -> /health/ai-ops` exposes runtime and ops metrics.
- `apps/py-api/py_api/api/documents.py` translates provider failures into typed `503` degraded-mode responses.

### How to Evaluate

- Hit `/health/ai-ops` before and after retrieval or AI calls.
- Force provider failure and inspect the degraded-mode payload.
- Relevant tests: `tests/smoke/test_phase13_productionization.py`.

### Exit Criteria

- Provider failures are typed and observable.
- AI runtime metrics are exposed for debugging and operational reasoning.
- The repo documents which paths should remain synchronous and which should move async first.

### Interview Reflections

- What is the first production bottleneck in this repo's AI path?
- Why is adapter-level telemetry the right place to start?
- Which workloads would you move off the request path first, and which would you keep synchronous longer?
