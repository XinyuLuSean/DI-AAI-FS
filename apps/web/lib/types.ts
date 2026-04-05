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

export interface SummaryResult {
  summary_text: string;
  key_points: string[];
  evidence: EvidenceReference[];
}

export interface ExtractionResponse {
  id: string;
  document_id: string;
  model_used: string;
  structured_fields: StructuredField[];
  summary: SummaryResult | null;
  created_at: string;
  processing_time_ms: number;
}
