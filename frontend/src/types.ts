export type Role = "employee" | "reviewer" | "admin";

export interface User {
  username: string;
  display_name: string;
  role: Role;
}

export type KnowledgeStatus =
  | "current_approved"
  | "historical_or_dated"
  | "authoritative"
  | "missing"
  | "conflict";

export interface Citation {
  citation_id: number;
  label: string;
  source_file: string;
  source_type: string;
  sheet: string | null;
  row_number: number | null;
  section: string | null;
  product_sku: string | null;
  product_id: string | null;
  source_modified_at: string;
  chunk_id: string;
  source_version: string | null;
  approval_change_id: string | null;
  authority_class: string;
  knowledge_status: KnowledgeStatus;
}

export interface Claim {
  text: string;
  supported: boolean;
  sources: Citation[];
  claim_type: string;
}

export interface RetrievedContext {
  chunk_id: string;
  content: string;
  source_file: string;
  section: string | null;
  row_number: number | null;
  category: string;
  authority_class: string;
  dense_score: number | null;
  bm25_score: number | null;
  rrf_score: number;
  reranker_score: number;
  final_rank: number | null;
}

export interface QueryResult {
  answer: string;
  sufficient_information: boolean;
  sources: Citation[];
  retrieved_context: RetrievedContext[];
  structured_matches: Array<Record<string, unknown>>;
  claims: Claim[];
  conflicts: Array<Record<string, unknown>>;
  answer_context_chars: number;
  answer_context_chunks: number;
  debug: Record<string, unknown> | null;
}

export interface Evidence {
  chunk_id: string;
  source_file: string;
  source_type: string;
  row_start: number | null;
  row_end: number | null;
  section: string | null;
  sheet: string | null;
  product_sku: string | null;
  product_id: string | null;
  excerpt: string;
  authority_class: string;
  knowledge_status: KnowledgeStatus;
  source_date: string | null;
  source_modified_at: string;
  source_version: string | null;
  approval_change_id: string | null;
}

export interface ProductFact {
  id: string;
  field_name: string;
  value: unknown;
  source_file: string;
  source_row: number;
  source_date: string;
  authority_class: string;
  confidence: string;
  status: string;
  approved_at: string;
  reviewer_id: string;
  reason: string;
}

export interface Product {
  canonical_product_id: string;
  model: string;
  name: string;
  category: string;
  supported_attributes: Record<string, unknown>;
  unsupported_fields: string[];
  source_row: number;
  source_date: string;
  authority_class: string;
  confidence: string;
  status: string;
  facts: ProductFact[];
}

export interface FactChange {
  id: string;
  canonical_product_id: string;
  product_sku: string;
  field_name: string;
  proposed_value: unknown;
  existing_value: unknown;
  source_file: string;
  source_version: string;
  source_row: number;
  evidence: Record<string, unknown>;
  status: "pending" | "approved" | "rejected" | "superseded";
  created_at: string;
  decided_at: string | null;
  reviewer_id: string | null;
  reason: string | null;
  events: Array<Record<string, unknown>>;
}

export interface SourceSummary {
  id: string;
  filename: string;
  source_type: string;
  version: string;
  source_modified_at: string;
  source_date: string | null;
  authority_class: string;
  confidentiality: string;
  version_status: string | null;
  is_current: boolean | null;
  record_count: number;
  chunk_count: number;
  indexed: boolean;
}

export interface StagedSource {
  id: string;
  original_filename: string;
  source_type: string;
  size_bytes: number;
  status: string;
  findings: string[];
  preview: Record<string, unknown>;
  fact_updates: Array<Record<string, unknown>>;
  created_by: string;
  created_at: string;
  proposed_at: string | null;
}

export interface IngestionResult {
  run_id: string;
  source_documents: number;
  products: number;
  knowledge_records: number;
  chunks: number;
  qdrant_points: number;
  source_hashes_unchanged: boolean;
}

export interface IngestionJob {
  id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  phase: string;
  created_by: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  cancel_requested: boolean;
  cancellable: boolean;
  error_message: string | null;
  result: IngestionResult | null;
}
