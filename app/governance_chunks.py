"""Canonical indexed-chunk representations for human-approved knowledge."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from app.domain import Chunk


def approved_fact_chunk_id(fact_id: str) -> str:
    """Return the stable vector/SQLite identifier for an approved fact."""

    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"foreign-trade-rag:approved-fact:{fact_id}"))


def approved_fact_chunk(
    *,
    fact_id: str,
    canonical_product_id: str,
    model: str,
    field_name: str,
    value: Any,
    reason: str,
    source_document_id: str,
    source_file: str,
    source_type: str,
    source_modified_at: str,
    source_date: str,
    source_version: str,
    source_row: int,
    authority_class: str,
    change_id: str,
    approved_at: str,
    reviewer_id: str,
) -> Chunk:
    """Build the single governed representation indexed by SQLite and Qdrant."""

    content = (
        "Approved product fact.\n"
        f"Product ID: {canonical_product_id}\n"
        f"Model: {model}\n"
        f"Approved {field_name}: {json.dumps(value, ensure_ascii=False)}\n"
        f"Approval reason: {reason}"
    )
    return Chunk(
        id=approved_fact_chunk_id(fact_id),
        record_type="approved_product_fact",
        record_id=fact_id,
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        source_document_id=source_document_id,
        source_file=source_file,
        source_type=source_type,
        source_modified_at=source_modified_at,
        source_date=source_date,
        authority_class=authority_class,
        confidentiality="internal",
        category="approved_product_fact",
        section=f"Approved field: {field_name}",
        row_start=source_row,
        row_end=source_row,
        product_id=canonical_product_id,
        model=model,
        metadata={
            "field_name": field_name,
            "source_version": source_version,
            "approval_change_id": change_id,
            "approved_at": approved_at,
            "reviewer_id": reviewer_id,
            "governance_status": "approved",
        },
    )
