/**
 * TypeScript mirrors of the Python Pydantic schemas.
 *
 * These types keep the frontend in sync with the API contract.
 * In the future, shared-types package or codegen from OpenAPI spec
 * will auto-generate these.
 */

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

export interface DocumentChunk {
  chunk_id: string;
  document_id: string;
  index: number;
  text: string;
  page_numbers: number[];
  char_start: number;
  char_end: number;
  token_estimate: number;
}

export interface DocumentResponse {
  id: string;
  filename: string;
  content_type: string;
  status: string;
  source: DocumentSource | null;
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

export interface StructuredField {
  field_name: string;
  field_value: string;
  confidence: number;
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
