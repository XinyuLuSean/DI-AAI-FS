/**
 * TypeScript mirrors of the Python Pydantic schemas.
 *
 * These types keep the frontend in sync with the API contract.
 * In the future, shared-types package or codegen from OpenAPI spec
 * will auto-generate these.
 */

export type ParseFailureReason =
  | "none"
  | "unsupported_file_type"
  | "file_not_found"
  | "empty_extraction"
  | "unreadable_pdf"
  | "zero_text_pdf";

export type ParseQuality = "good" | "degraded" | "unusable";

export interface ParseMeta {
  parse_strategy: string;
  file_suffix: string;
  page_count: number;
  empty_page_count: number;
  total_chars: number;
  text_density: number;
  failure_reason: ParseFailureReason;
  native_text_extracted: boolean;
  likely_scanned: boolean;
  likely_needs_ocr: boolean;
  ocr_applied: boolean;
  quality: ParseQuality;
  downstream_limitations: string[];
  warnings: string[];
}

export type DocumentType =
  | "unknown"
  | "legal"
  | "medical"
  | "billing"
  | "treatment"
  | "correspondence";

export interface RoutingRule {
  source: string;
  pattern: string;
  matched_type: DocumentType;
  weight: number;
}

export interface RoutingResult {
  predicted_type: DocumentType;
  confidence: number;
  matched_rules: RoutingRule[];
  is_fallback: boolean;
  warnings: string[];
}

export interface DocumentSource {
  storage_backend: string;
  path: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
}

export interface DocumentPage {
  page_number: number;
  text: string;
  char_count: number;
}

export type ChunkStrategy = "fixed_size" | "paragraph" | "page_bounded";

export interface ChunkMeta {
  strategy: ChunkStrategy;
  chunk_size: number;
  overlap: number;
  chunk_count: number;
  avg_chunk_chars: number;
  total_chars_chunked: number;
  max_chunks_limit: number | null;
  is_truncated: boolean;
  page_coverage: number[];
  warnings: string[];
}

export interface DocumentChunk {
  chunk_id: string;
  document_id: string;
  index: number;
  text: string;
  strategy: string;
  page_numbers: number[];
  char_start: number;
  char_end: number;
  token_estimate: number;
  is_truncated: boolean;
  doc_type: string;
  source_filename: string;
  parse_quality: string;
  section_label: string;
}

export type DocumentSizeCategory = "small" | "medium" | "large" | "oversized";

export interface SectionLabel {
  label: string;
  page_start: number;
  page_end: number;
  char_start: number;
  char_end: number;
  detection_method: string;
  confidence: number;
}

export interface DocumentResponse {
  id: string;
  filename: string;
  content_type: string;
  status: string;
  source: DocumentSource | null;
  parse_meta: ParseMeta | null;
  routing: RoutingResult | null;
  chunk_meta: ChunkMeta | null;
  size_category: DocumentSizeCategory | null;
  sections: SectionLabel[];
  pages: DocumentPage[];
  chunks: DocumentChunk[];
  created_at: string;
  updated_at: string;
  error: string | null;
}

export interface EvidenceReference {
  chunk_id: string;
  chunk_text: string;
  relevance_score: number;
  page_numbers: number[];
  source_filename: string;
  doc_type: string;
  section_label: string;
  parse_quality: string;
  char_start: number;
  char_end: number;
}

export type ExtractionMethod = "regex" | "keyword_window" | "llm" | "manual";

export interface StructuredField {
  field_name: string;
  field_value: string;
  confidence: number;
  extraction_method: ExtractionMethod | string;
  source_snippet: string;
  evidence: EvidenceReference[];
}

export interface GroundedKeyPoint {
  text: string;
  chunk_ids: string[];
  grounded: boolean;
}

export interface SummaryResult {
  summary_text: string;
  key_points: string[];
  grounded_key_points: GroundedKeyPoint[];
  evidence: EvidenceReference[];
  grounding_coverage: number;
}

export type OutputType = "deterministic" | "ai_summary";

export interface GroundingAudit {
  chunks_provided: number;
  chunks_cited_by_llm: number;
  chunks_cited_valid: number;
  chunks_cited_invalid: number;
  key_points_total: number;
  key_points_grounded: number;
  key_points_ungrounded: number;
  grounding_score: number;
  needs_review: boolean;
  warnings: string[];
}

export interface SummarisationMeta {
  total_chunks_available: number;
  total_pages_available: number;
  chunks_sent_to_llm: number;
  chunks_cited_by_llm: number;
  pages_covered_by_selection: number[];
  pages_covered_by_evidence: number[];
  coverage_ratio: number;
  evidence_usage_ratio: number;
  selection_strategy: string;
  is_partial: boolean;
  warnings: string[];
}

export interface ExtractionResponse {
  id: string;
  document_id: string;
  output_type: OutputType;
  model_used: string;
  prompt_name: string;
  prompt_version: string;
  structured_fields: StructuredField[];
  summary: SummaryResult | null;
  grounding_audit: GroundingAudit | null;
  summarisation_meta: SummarisationMeta | null;
  created_at: string;
  processing_time_ms: number;
}

// ── Document and extraction list types ────────────────────────────────────

export interface DocumentListItem {
  id: string;
  filename: string;
  status: string;
  content_type: string;
  doc_type: string | null;
  page_count: number;
  chunk_count: number;
  size_category: string | null;
  extraction_count: number;
  created_at: string;
}

export interface ExtractionListItem {
  id: string;
  document_id: string;
  output_type: string;
  model_used: string;
  field_count: number;
  has_summary: boolean;
  processing_time_ms: number;
  review_status: string | null;
  review_triggers: string[];
  review_priority: number;
  created_at: string;
}

// ── Phase 11: HITL Review Types ──────────────────────────────────────────

export type ReviewStatus =
  | "pending_review"
  | "in_review"
  | "approved"
  | "corrected"
  | "rejected"
  | "auto_accepted";

export type ReviewTriggerReason =
  | "low_confidence_field"
  | "no_fields_extracted"
  | "weak_grounding"
  | "ungrounded_key_points"
  | "hallucinated_chunk_ids"
  | "partial_coverage"
  | "degraded_parse_quality"
  | "low_routing_confidence"
  | "manual_request";

export interface ReviewDecision {
  id: string;
  extraction_id: string;
  document_id: string;
  reviewer_id: string;
  status: ReviewStatus;
  notes: string;
  created_at: string;
}

export interface ReviewableOutput {
  id: string;
  extraction_id: string;
  document_id: string;
  status: ReviewStatus;
  trigger_reasons: ReviewTriggerReason[];
  priority_score: number;
  decisions: ReviewDecision[];
  correction_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewQueueResponse {
  items: ReviewableOutput[];
  total: number;
  pending_count: number;
  auto_accepted_count: number;
}

export interface CorrectionResponse {
  correction_id: string;
  total_corrections: number;
  feedback_signals_generated: number;
  review_status: string;
}
