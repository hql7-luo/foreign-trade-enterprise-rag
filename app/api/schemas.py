"""Public API contracts for querying and debugging the RAG pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryRequest(StrictRequest):
    question: str = Field(min_length=1, max_length=2000)
    debug: bool = False
    top_k: int = Field(default=8, ge=1, le=20)


class CitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    citation_id: int
    label: str
    source_file: str
    source_type: str
    sheet: str | None
    row_number: int | None
    section: str | None
    product_sku: str | None
    product_id: str | None
    source_modified_at: str
    chunk_id: str
    source_version: str | None = None
    approval_change_id: str | None = None
    authority_class: str
    knowledge_status: str


class StructuredMatchResponse(BaseModel):
    product_id: str
    model: str
    title: str
    product_group: str
    match_score: float
    match_reason: str


class RetrievedContextResponse(BaseModel):
    chunk_id: str
    content: str
    source_file: str
    source_type: str
    section: str | None
    row_number: int | None
    product_sku: str | None
    product_id: str | None
    category: str
    authority_class: str
    dense_score: float | None
    bm25_score: float | None
    dense_rank: int | None
    bm25_rank: int | None
    rrf_score: float
    fused_rank: int | None
    structured_boost: float
    heuristic_score: float
    cross_encoder_score: float | None
    reranker_score: float
    final_rank: int | None


class ClaimResponse(BaseModel):
    text: str
    supported: bool
    sources: list[CitationResponse]
    claim_type: str
    support_state: str | None = None


class QueryResponse(BaseModel):
    answer: str
    sufficient_information: bool
    sources: list[CitationResponse]
    retrieved_context: list[RetrievedContextResponse]
    structured_matches: list[StructuredMatchResponse]
    claims: list[ClaimResponse]
    answer_context_chars: int
    answer_context_chunks: int
    conflicts: list[dict[str, Any]]
    debug: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    indexed: bool
    database_counts: dict[str, int]
    latest_ingestion: dict[str, Any] | None


class FactChangeProposalRequest(StrictRequest):
    product_id: str = Field(min_length=1, max_length=100)
    field_name: str = Field(min_length=2, max_length=64)
    proposed_value: Any
    source_file: str = Field(min_length=1, max_length=255)
    source_row: int = Field(ge=1)
    evidence: dict[str, Any] = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=2000)


class FactReviewDecisionRequest(StrictRequest):
    reason: str = Field(min_length=1, max_length=2000)


class FactChangeResponse(BaseModel):
    id: str
    canonical_product_id: str
    product_sku: str
    field_name: str
    proposed_value: Any
    existing_value: Any
    source_document_id: str
    source_file: str
    source_version: str
    source_row: int
    evidence: dict[str, Any]
    status: str
    created_at: str
    decided_at: str | None
    reviewer_id: str | None
    reason: str | None
    events: list[dict[str, Any]] = Field(default_factory=list)


class UserResponse(BaseModel):
    username: str
    display_name: str
    role: str


class LoginRequest(StrictRequest):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=200)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    user: UserResponse


class EvidenceResponse(BaseModel):
    chunk_id: str
    source_file: str
    source_type: str
    row_start: int | None
    row_end: int | None
    section: str | None
    sheet: str | None
    product_sku: str | None
    product_id: str | None
    excerpt: str
    authority_class: str
    knowledge_status: str
    source_date: str | None
    source_modified_at: str
    source_version: str | None
    approval_change_id: str | None


class ProductFactResponse(BaseModel):
    id: str
    canonical_product_id: str
    field_name: str
    value: Any
    source_document_id: str
    source_row: int
    source_date: str
    authority_class: str
    confidence: str
    status: str
    source_version: str
    approved_at: str
    reviewer_id: str
    reason: str
    change_id: str | None
    product_sku: str | None = None
    source_file: str


class ProductMasterResponse(BaseModel):
    canonical_product_id: str
    model: str
    name: str
    category: str
    supported_attributes: dict[str, Any]
    unsupported_fields: list[str]
    source_document_id: str
    source_row: int
    source_date: str
    authority_class: str
    confidence: str
    status: str
    facts: list[ProductFactResponse]


class ProductHistoryResponse(BaseModel):
    product_id: str
    product_sku: str
    field_name: str | None
    facts: list[ProductFactResponse]
    changes: list[FactChangeResponse]
    conflicts: list[dict[str, Any]]


class SourceSummaryResponse(BaseModel):
    id: str
    filename: str
    source_type: str
    version: str
    source_modified_at: str
    source_date: str | None
    authority_class: str
    confidentiality: str
    version_status: str | None
    is_current: bool | None
    record_count: int
    chunk_count: int
    indexed: bool


class IngestionResponse(BaseModel):
    run_id: str
    source_documents: int
    products: int
    knowledge_records: int
    chunks: int
    qdrant_points: int
    source_hashes_unchanged: bool


class IngestionJobResponse(BaseModel):
    id: str
    status: str
    progress: int
    phase: str
    created_by: str
    created_at: str
    started_at: str | None
    completed_at: str | None
    cancel_requested: bool
    cancellable: bool
    error_message: str | None
    result: IngestionResponse | None


class StagedSourceResponse(BaseModel):
    id: str
    source_document_id: str | None
    original_filename: str
    source_type: str
    sha256: str
    size_bytes: int
    status: str
    findings: list[str]
    preview: dict[str, Any]
    fact_updates: list[dict[str, Any]]
    created_by: str
    created_at: str
    proposed_at: str | None


class StagedProposalResponse(BaseModel):
    source: StagedSourceResponse
    changes: list[FactChangeResponse]
