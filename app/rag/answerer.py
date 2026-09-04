"""Citation primitives and conservative extractive answer contract."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain import Chunk, RetrievalHit
from app.rag.models import Citation, GroundedClaim


@dataclass
class ExtractiveAnswer:
    text: str
    sufficient: bool
    used_hits: list[RetrievalHit]
    claims: list[GroundedClaim] = field(default_factory=list)


def citation_label(hit: RetrievalHit) -> str:
    chunk = hit.chunk
    parts = [f"Source: {chunk.source_file}"]
    if chunk.sheet:
        parts.append(f"sheet {chunk.sheet}")
    if chunk.row_start:
        parts.append(f"row {chunk.row_start}")
    if chunk.section:
        parts.append(f"section {chunk.section}")
    if chunk.model:
        parts.append(f"SKU {chunk.model}")
    if chunk.product_id:
        parts.append(f"product ID {chunk.product_id}")
    return " → ".join(parts)


def citation_from_hit(hit: RetrievalHit, citation_id: int) -> Citation:
    chunk = hit.chunk
    status = (
        "historical_or_dated"
        if chunk.category in {"quotation_evidence", "rfq_market_analytics"}
        else "current_approved"
        if chunk.record_type in {"product", "approved_product_fact"}
        else "authoritative"
    )
    return Citation(
        citation_id,
        citation_label(hit),
        chunk.source_file,
        chunk.source_type,
        chunk.sheet,
        chunk.row_start,
        chunk.section,
        chunk.model,
        chunk.product_id,
        chunk.source_modified_at,
        chunk.id,
        chunk.metadata.get("source_version"),
        chunk.metadata.get("approval_change_id"),
        chunk.authority_class,
        status,
    )


def build_context(
    question: str,
    hits: list[RetrievalHit],
    limit: int = 16,
    *,
    parent_chunks: dict[str, Chunk] | None = None,
) -> str:
    del parent_chunks
    return (
        "Question: "
        + question
        + "\n"
        + "\n\n".join(
            f"[{index}] {citation_label(hit)}\n{hit.chunk.content}"
            for index, hit in enumerate(hits[:limit], 1)
        )
    )


class ConservativeAnswerer:
    def answer(self, question, matches, hits, conflicts):
        from app.rag.claim_answerer import ClaimLevelAnswerer

        return ClaimLevelAnswerer().answer(question, matches, hits, conflicts)


class OpenAICompatibleAnswerer:
    def __init__(self, *_args, **_kwargs):
        raise ValueError(
            "The public edition uses local extractive synthesis; unset LLM credentials"
        )
