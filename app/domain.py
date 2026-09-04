from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceDocument:
    id: str
    filename: str
    relative_path: str
    source_type: str
    sha256: str
    source_modified_at: str
    source_date: str | None
    authority_class: str
    confidentiality: str


@dataclass(frozen=True)
class ProductRecord:
    product_id: str
    title: str
    model: str
    product_group: str
    product_type: str
    product_tier: str
    price_min_usd: float
    price_max_usd: float
    unit: str
    last_updated: str
    quality_score: float
    review_status: str
    listing_status: str
    country_controlled: bool
    optimized: bool
    showcase: bool
    monthly_exposure: int
    snapshot_date: str
    source_document_id: str
    source_row: int


@dataclass(frozen=True)
class KnowledgeRecord:
    id: str
    category: str
    title: str
    content: str
    authority_class: str
    confidentiality: str
    source_document_id: str
    section: str
    row_start: int | None = None
    row_end: int | None = None
    model: str | None = None


@dataclass(frozen=True)
class Chunk:
    id: str
    record_type: str
    record_id: str
    content: str
    content_hash: str
    source_document_id: str
    source_file: str
    source_type: str
    source_modified_at: str
    source_date: str | None
    authority_class: str
    confidentiality: str
    category: str
    section: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    sheet: str | None = None
    product_id: str | None = None
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductMatch:
    product: ProductRecord
    score: float
    reason: str


@dataclass
class RetrievalHit:
    chunk: Chunk
    dense_score: float | None = None
    bm25_score: float | None = None
    dense_rank: int | None = None
    bm25_rank: int | None = None
    fused_score: float = 0.0
    fused_rank: int | None = None
    structured_score: float = 0.0
    heuristic_score: float = 0.0
    cross_encoder_score: float | None = None
    reranker_score: float = 0.0
    final_rank: int | None = None


@dataclass(frozen=True)
class ProductMasterRecord:
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


@dataclass(frozen=True)
class ProductFact:
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
    change_id: str | None = None


@dataclass(frozen=True)
class ProductFactChange:
    id: str
    canonical_product_id: str
    product_sku: str
    field_name: str
    proposed_value: Any
    existing_value: Any
    source_document_id: str
    source_file: str
    source_version: str
    source_row: int | None
    evidence: dict[str, Any]
    status: str
    created_at: str
    decided_at: str | None = None
    reviewer_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class KnowledgeVersion:
    source_document_id: str
    version_date: str | None
    authority_class: str
    status: str
    is_current: bool


@dataclass(frozen=True)
class ConflictRecord:
    id: str
    entity_type: str
    entity_key: str
    field_name: str
    conflict_type: str
    values: list[dict[str, Any]]
    source_document_ids: list[str]
    evidence_chunk_ids: list[str]
    resolution_policy: str
    status: str


@dataclass(frozen=True)
class GovernanceBundle:
    product_master: list[ProductMasterRecord]
    product_facts: list[ProductFact]
    knowledge_versions: list[KnowledgeVersion]
    conflicts: list[ConflictRecord]
    fact_changes: list[ProductFactChange] = field(default_factory=list)


@dataclass(frozen=True)
class IngestionBundle:
    sources: list[SourceDocument]
    products: list[ProductRecord]
    knowledge_records: list[KnowledgeRecord]
    chunks: list[Chunk]
    source_hashes: dict[str, str]
