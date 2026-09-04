"""RAG result models shared by the service and API layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.domain import ProductMatch, RetrievalHit

SupportState = Literal[
    "supported_current", "supported_historical", "conflicting", "unsupported", "ambiguous"
]


@dataclass(frozen=True, slots=True)
class Citation:
    """A user-inspectable pointer to one indexed source fragment."""

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
    authority_class: str = ""
    knowledge_status: str = "authoritative"


@dataclass(slots=True)
class GroundedClaim:
    """Internal claim support record; it exposes evidence, not hidden reasoning."""

    text: str
    supported: bool
    evidence_hits: list[RetrievalHit] = field(default_factory=list)
    claim_type: str = "fact"
    support_state: SupportState | None = None

    def __post_init__(self) -> None:
        if self.support_state is None:
            self.support_state = (
                "unsupported"
                if not self.supported
                else "supported_historical"
                if self.evidence_hits
                and all(
                    hit.chunk.category in {"quotation_evidence", "rfq_market_analytics"}
                    for hit in self.evidence_hits
                )
                else "supported_current"
            )


@dataclass(frozen=True, slots=True)
class AnswerClaim:
    """Public claim with the exact citations that support it."""

    text: str
    supported: bool
    sources: list[Citation]
    claim_type: str = "fact"
    support_state: SupportState | None = None


@dataclass(frozen=True, slots=True)
class AnswerResult:
    """Complete grounded response returned by the application service."""

    answer: str
    sufficient_information: bool
    sources: list[Citation]
    retrieved_context: list[RetrievalHit]
    structured_matches: list[ProductMatch]
    claims: list[AnswerClaim] = field(default_factory=list)
    answer_context_chars: int = 0
    answer_context_chunks: int = 0
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    debug: dict[str, Any] | None = field(default=None)
