# Phase 0 — Baseline Applied AI Walkthrough

## Current AI Task

The repo has **one AI task**: LLM-based document summarisation.

It runs as a **grounded summarisation** pipeline — the LLM receives pre-extracted
deterministic fields as ground truth constraints alongside document chunks,
producing a JSON summary with per-claim evidence binding.

---

## Current AI Flow Diagram

```
User clicks "Summarise (LLM, grounded)"
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│  Frontend (page.tsx)                                         │
│  summariseDocument(docId, extractionId) → POST /summarise    │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  API Endpoint (documents.py: summarise)                      │
│  1. Look up Document from in-memory store                    │
│  2. If extraction_id provided → load prior deterministic     │
│     extraction → use its StructuredFields as grounding       │
│  3. Call summarise_document(doc, grounding_fields)           │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Chunk Selection (chunk_selector.py)                         │
│  select_chunks_for_llm(doc, max_chunks=10, strategy=HEAD)    │
│                                                              │
│  Strategies: head, tail, head_tail, sampled, routing_aware   │
│  Returns: (selected_chunks, SummarisationMeta)               │
│  Meta tracks: chunks sent vs available, page coverage,       │
│               is_partial flag, warnings                      │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Prompt Construction (prompts.py)                            │
│                                                              │
│  System: SUMMARISE_SYSTEM or GROUNDED_SUMMARISE_SYSTEM       │
│  User:   build_summarise_user_prompt(chunks, fields)         │
│                                                              │
│  Prompt shape:                                               │
│    [If grounded] PRE-EXTRACTED FIELDS (treat as truth):      │
│      - field_name: value (confidence: N)                     │
│    DOCUMENT CHUNKS:                                          │
│      [chunk_id=abc123] text...                               │
│      ---                                                     │
│      [chunk_id=def456] text...                               │
│                                                              │
│  Expected output schema (instructed in system prompt):       │
│    { summary_text, key_points[{point, chunk_ids}],           │
│      structured_fields[{field_name, field_value, confidence}]│
│      chunk_ids_used }                                        │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  LLM Provider Call (adapter.py)                              │
│                                                              │
│  LLMAdapter.complete_json(system, user)                      │
│  Provider: LiteLLM (swappable: OpenAI, Anthropic, local)     │
│  Model:    gpt-4o-mini (env: LLM_MODEL)                     │
│  Temp:     0.0                                               │
│  Mode:     response_format=json_object                       │
│  Returns:  parsed dict                                       │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Post-LLM Grounding Audit (grounding.py)                     │
│                                                              │
│  audit_grounding(raw_key_points, used_ids, provided_ids)     │
│  Per key point:                                              │
│    - validate cited chunk_ids against actually provided set   │
│    - mark grounded vs ungrounded                             │
│  Aggregate:                                                  │
│    - grounding_score = grounded/total key points             │
│    - needs_review if: hallucinated IDs or score < 50%        │
│    - warnings for invalid IDs or ungrounded claims           │
│                                                              │
│  enrich_summarisation_meta(meta, used_ids, chunk_map)        │
│    - adds chunks_cited_by_llm, evidence_usage_ratio          │
│    - warns if LLM cited zero provided chunks                 │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Evidence Packaging (evidence.py)                            │
│                                                              │
│  package_evidence_from_ids(used_ids, chunk_map)              │
│  For each valid chunk ID:                                    │
│    → EvidenceReference {                                     │
│        chunk_id, chunk_text (≤300 chars), page_numbers,      │
│        source_filename, doc_type, section_label,             │
│        parse_quality, char_start, char_end                   │
│      }                                                       │
│  Silently skips hallucinated IDs                             │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Response Assembly (summariser.py)                            │
│                                                              │
│  ExtractionResult {                                          │
│    output_type: "ai_summary"                                 │
│    model_used: "gpt-4o-mini"                                 │
│    structured_fields: [LLM-extracted fields]                 │
│    summary: SummaryResult {                                  │
│      summary_text, key_points, grounded_key_points,          │
│      evidence, grounding_coverage                            │
│    }                                                         │
│    grounding_audit: GroundingAudit { score, warnings, ... }  │
│    summarisation_meta: SummarisationMeta { coverage, ... }   │
│    processing_time_ms                                        │
│  }                                                           │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Backend Storage + Review (documents.py)                      │
│                                                              │
│  _extractions[result.id] = result                            │
│  _ensure_reviewable(result.id) → ReviewableOutput            │
│    (auto-classifies triggers: low confidence, weak grounding,│
│     partial coverage, etc.)                                  │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Frontend Rendering (extraction-result.tsx)                   │
│                                                              │
│  1. Output type badge: "AI Summary" (purple)                 │
│  2. GroundingAuditPanel: score %, review-needed flag,        │
│     valid/invalid chunk citations, warnings                  │
│  3. SummarisationMetaPanel: chunks sent/available,           │
│     coverage %, strategy, partial-summary flag               │
│  4. Summary text + grounding_coverage badge                  │
│     (green ≥80%, yellow ≥50%, red <50%)                      │
│  5. GroundedKeyPointsList: green/red dots per point,         │
│     chunk ID citations, "ungrounded" badges                  │
│  6. EvidencePanel (collapsible): chunk text, pages,          │
│     relevance score, section label, parse quality            │
│  7. Structured fields with confidence badges                 │
└──────────────────────────────────────────────────────────────┘
```

---

## Current Prompt Shape

**System prompt** (two variants):
- `SUMMARISE_SYSTEM` — standalone, chunks only
- `GROUNDED_SUMMARISE_SYSTEM` — adds "the pre-extracted fields are ground truth, do not contradict them"

**Key prompt rules:**
- Be factual, only state what the text supports
- For each key_point, list the specific chunk_ids that support it
- chunk_ids_used is the union of all referenced chunk_ids
- Do NOT make unsupported claims
- Do NOT contradict pre-extracted fields (grounded variant)

**Expected JSON output schema:**
```json
{
  "summary_text": "2-4 sentence summary",
  "key_points": [
    {"point": "claim text", "chunk_ids": ["id1", "id2"]}
  ],
  "structured_fields": [
    {"field_name": "...", "field_value": "...", "confidence": 0.0-1.0}
  ],
  "chunk_ids_used": ["id1", "id2", "id3"]
}
```

---

## Current Model/Provider Assumptions

| Aspect | Current state |
|---|---|
| Provider abstraction | LiteLLM — supports OpenAI, Anthropic, local models |
| Default model | `gpt-4o-mini` (via `LLM_MODEL` env var) |
| Temperature | 0.0 (deterministic) |
| JSON mode | `response_format: {"type": "json_object"}` |
| Streaming | Not implemented |
| Retry/timeout | Not implemented (relies on LiteLLM defaults) |
| Batch support | Not implemented |
| Cost tracking | Not implemented |

---

## Current Evidence Behavior

**Strong points:**
1. **Per-claim evidence binding** — each key point carries its own `chunk_ids`, not just a global citation list
2. **Post-LLM grounding audit** — validates cited chunk IDs against the set actually provided, catches hallucinated IDs
3. **Grounding score** — quantifies what fraction of key points have valid evidence
4. **Review trigger** — flags for human review when grounding is weak (<50%) or hallucinated IDs detected
5. **Rich evidence references** — carry page numbers, section label, doc type, parse quality, char offsets
6. **Summarisation meta transparency** — records chunks sent vs available, coverage ratio, is_partial flag
7. **Evidence usage ratio** — tracks what fraction of provided chunks were actually cited

**Evidence is assembled at two levels:**
- `package_evidence_from_ids()` — global evidence list from LLM's `chunk_ids_used`
- `audit_grounding()` — per-key-point evidence binding from each point's `chunk_ids`

---

## Current Strongest Design Choices

1. **Grounding by pre-extracted fields** — deterministic extraction runs first, its fields become constraints for the LLM. This prevents the LLM from contradicting known facts (dates, amounts, names).

2. **Separation of concerns** — prompt construction (`prompts.py`), provider call (`adapter.py`), grounding validation (`grounding.py`), evidence packaging (`evidence.py`), and chunk selection (`chunk_selector.py`) are all separate modules.

3. **Budget-aware chunk selection with transparency** — the system knows it can't send all chunks, selects explicitly, and discloses coverage. `SummarisationMeta` makes partial coverage visible to both the UI and reviewers.

4. **Per-claim evidence binding** — `GroundedKeyPoint` traces each claim to specific chunks, enabling reviewers to verify individual statements rather than trusting the summary as a whole.

5. **OutputType distinction** — `deterministic` vs `ai_summary` are first-class output types, so evaluation, HITL, and UI can apply different trust levels.

6. **JSON-mode enforcement** — uses OpenAI's JSON mode rather than hoping for valid JSON from free text.

7. **Routing-aware chunk selection** — document type influences which chunks are selected (legal→head_tail, billing→head, medical→sampled).

---

## Current Limitations (Biggest Applied AI Gaps)

### No retrieval stack
Chunks are selected by **position** (head, tail, sampled), not by **relevance** to any query or task. For long documents, this means the LLM may never see the most important content.

### No evaluation harness
There is no way to measure whether the summarisation output is correct, complete, or grounded beyond the post-hoc grounding audit. No golden test set, no regression testing, no comparison between prompt versions.

### No prompt versioning
Prompts are hardcoded string constants. There is no version tracking, no A/B comparison infrastructure, and no way to trace which prompt version produced which result.

### No model/provider comparison
Only one model path exists. There is no way to compare outputs across models or measure quality/latency/cost tradeoffs.

### One AI task only
Only summarisation exists. No classification, no contradiction detection, no semantic matching, no chronology extraction.

### No uncertainty modeling
The system flags weak grounding but does not model uncertainty explicitly. The LLM has no instruction to abstain, say "not enough evidence", or calibrate its own confidence.

### No streaming or cancellation
The LLM call is synchronous and blocking. No partial rendering, no abort, no timeout.

### No cost or latency tracking per request
Processing time is tracked but token usage, cost, and provider latency are not.

### Validation is parse-only
If the LLM returns valid JSON that doesn't match the expected schema (e.g., missing `key_points`), the system defaults to empty lists rather than raising validation errors.

### In-memory storage
Documents, extractions, and reviews live in Python dicts. Restarting the server loses all state.

---

## What Makes The Current AI Path MVP-Only

1. **Single task** — only summarisation, no task framework
2. **No evaluation** — no way to know if quality is improving or regressing
3. **No retrieval** — position-based chunk selection is a ceiling for long-document quality
4. **No prompt lifecycle** — prompts are static, unversioned, untested
5. **No production safeguards** — no timeout, retry, rate limiting, cost cap
6. **No persistent storage** — in-memory only
7. **Schema enforcement is soft** — malformed LLM output degrades silently to defaults

---

## Verification Answers

**Where does the summariser get its input?**
From `select_chunks_for_llm()` in `chunk_selector.py`, which picks a subset of the document's chunks based on strategy and budget. Optionally, grounding fields come from a prior deterministic extraction.

**Does it use all chunks or a subset?**
A subset. Default `max_chunks=10`. If the document has fewer than 10 chunks, all are used. Otherwise, the selection strategy picks which ones.

**Is the output schema-controlled?**
Partially. The LLM is instructed to return specific JSON, and `response_format=json_object` enforces valid JSON. But the *content* schema is validated only by `.get()` with defaults — if `key_points` is missing, it becomes `[]` silently.

**Where are evidence references assembled?**
Two places: (1) `package_evidence_from_ids()` builds the global evidence list from `chunk_ids_used`, (2) `audit_grounding()` validates and enriches per-key-point evidence from each point's `chunk_ids`.

**What makes the current AI path MVP-only?**
See limitations above — one task, no evaluation, no retrieval, no prompt versioning, soft validation, in-memory storage.
