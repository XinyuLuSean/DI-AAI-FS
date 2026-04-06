# Phase 13: Applied AI Prototype To Production

## Current Prototype Path

Today the Applied AI stack runs synchronously inside a single FastAPI process:

1. upload and parse the document
2. preprocess, route, chunk, and enrich it
3. call deterministic extraction or an AI task directly from the API request
4. validate, ground, and store the result in in-memory dictionaries
5. expose review and correction flows from the same process

This is intentionally simple and inspectable, but it means API latency, model calls,
and operational state are tightly coupled.

## What Stays Synchronous First

These paths are still reasonable to keep synchronous in an early production phase:

- health checks and lightweight configuration reads
- deterministic extraction
- document search and retrieval comparison
- small-document summarisation or chronology requests triggered interactively
- review queue reads and review/correction submissions

The main requirement is that synchronous AI calls have strong guardrails:

- explicit request timeouts
- bounded retries with backoff
- typed degraded-mode responses on provider failure
- basic runtime metrics for latency, validity, grounding, and review-needed rate

## What Moves Async First

The first jobs that should leave the request path are the ones with long tail latency
or high fan-out:

- hierarchical summarisation of large documents
- embedding generation and vector index refreshes
- prompt experiment runs and evaluation regressions
- batch extraction backfills
- long-document reprocessing after parser or prompt changes

Recommended split:

- `py-api`: request validation, metadata reads, queue submission, status lookup
- `worker-ai`: LLM calls, long-running summarisation/chronology, prompt experiments
- `worker-index`: embeddings, reranking prep, retrieval index maintenance

## Provider Strategy

The repo already has an adapter boundary in `ai_core.adapter.LLMAdapter`.
That should remain the only place that knows provider-specific calling details.

Production guidance:

- keep model/provider selection in config, not business logic
- treat timeouts, retries, and provider errors as adapter concerns
- attach provider-level telemetry at the adapter boundary
- cache only stable, idempotent workloads such as embeddings or experiment replays
- avoid caching review-sensitive summary outputs until invalidation rules are clear

## Reliability Risks

The first things that will break as load grows are:

- synchronous API worker starvation during slow model calls
- provider rate limits and transient upstream timeouts
- in-memory operational state disappearing on restart
- repeated expensive work because job identity and deduping are still implicit
- lack of shared metrics across processes once workers are added

Current mitigations added in this phase:

- configurable LLM timeout
- bounded retry with backoff for retryable provider failures
- typed `503` degraded-mode API responses for provider failures
- in-memory AI ops snapshot for latency/error/quality monitoring

Still future work:

- durable job queue
- persistent idempotency keys for long-running jobs
- distributed metrics and tracing
- concurrency caps per provider/model
- request/result caching with invalidation

## Queue Boundaries And Idempotency

Once workers are introduced, the queue boundary should sit at "prepared AI job"
rather than raw file upload. The API should enqueue:

- document id
- extraction or AI task type
- prompt/model version
- retrieval config
- grounding/extraction dependency ids
- idempotency key derived from those inputs

That lets the API reject duplicate long-running work and makes replay/debugging easier.

## Monitoring Dashboard V1

The first dashboard should track:

- provider call count
- provider error rate
- retryable provider error count
- average and max model latency
- average and max end-to-end generation latency
- retrieval request count and latency
- output validity rate
- grounding failure rate
- unsupported-claim rate
- review-needed rate

In the prototype these metrics are process-local and exposed via `/health/ai-ops`.
That is enough for debugging now and creates a clean contract for later Prometheus or
OpenTelemetry export.

## Biggest Bottlenecks

- single-process synchronous LLM execution
- lack of durable state for operational metrics and pending work
- repeated whole-document processing for evaluation and experiments
- no provider-aware concurrency management yet

## First Production Evolution

The lowest-risk next step is:

1. keep the current API contracts
2. push long-running AI jobs to workers
3. store job state and AI ops metrics durably
4. leave deterministic extraction and lightweight retrieval synchronous

That preserves the current product behavior while removing the worst latency and
reliability risks from the request path.
