"""Governed product-fact reconciliation and auditable review operations."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from app.database import KnowledgeDatabase
from app.domain import (
    GovernanceBundle,
    IngestionBundle,
    ProductFact,
    ProductFactChange,
    ProductRecord,
)
from app.governance import build_governance
from app.governance_chunks import approved_fact_chunk
from app.ingestion.loaders import content_hash, product_chunk, stable_id
from app.security.filter import ensure_safe_for_general_index

PRODUCT_RECORD_FIELDS = {
    "model",
    "name",
    "category",
    "product_type",
    "product_tier",
    "platform_reference_price_min_usd",
    "platform_reference_price_max_usd",
    "unit",
    "last_updated",
    "quality_score",
    "review_status",
    "listing_status",
    "country_controlled",
    "optimized",
    "showcase",
    "monthly_exposure",
}


def _json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, ensure_ascii=False, sort_keys=True) == json.dumps(
        right, ensure_ascii=False, sort_keys=True
    )


def _fact_from_snapshot(item: dict[str, Any]) -> ProductFact:
    return ProductFact(
        id=item["id"],
        canonical_product_id=item["canonical_product_id"],
        field_name=item["field_name"],
        value=item["value"],
        source_document_id=item["source_document_id"],
        source_row=item["source_row"],
        source_date=item["source_date"],
        authority_class=item["authority_class"],
        confidence=item["confidence"],
        status="approved",
        source_version=item["source_version"],
        approved_at=item["approved_at"],
        reviewer_id=item["reviewer_id"],
        reason=item["reason"],
        change_id=item.get("change_id"),
    )


def _effective_product(
    raw: ProductRecord,
    values: dict[str, ProductFact],
) -> ProductRecord | None:
    if not PRODUCT_RECORD_FIELDS.issubset(values):
        return None
    identity = values.get("canonical_product_id") or values["model"]
    return ProductRecord(
        product_id=raw.product_id,
        title=str(values["name"].value),
        model=str(values["model"].value),
        product_group=str(values["category"].value),
        product_type=str(values["product_type"].value),
        product_tier=str(values["product_tier"].value),
        price_min_usd=float(values["platform_reference_price_min_usd"].value),
        price_max_usd=float(values["platform_reference_price_max_usd"].value),
        unit=str(values["unit"].value),
        last_updated=str(values["last_updated"].value),
        quality_score=float(values["quality_score"].value),
        review_status=str(values["review_status"].value),
        listing_status=str(values["listing_status"].value),
        country_controlled=bool(values["country_controlled"].value),
        optimized=bool(values["optimized"].value),
        showcase=bool(values["showcase"].value),
        monthly_exposure=int(values["monthly_exposure"].value),
        snapshot_date=identity.source_date,
        source_document_id=identity.source_document_id,
        source_row=identity.source_row,
    )


def reconcile_approved_facts(
    bundle: IngestionBundle,
    candidate_governance: GovernanceBundle,
    approved_snapshot: list[dict[str, Any]],
    *,
    occurred_at: str | None = None,
) -> tuple[IngestionBundle, GovernanceBundle]:
    """Keep approved values authoritative and materialize source changes as pending."""

    if not approved_snapshot:
        # First and repeated ingestion expose the same field-provenance shape.
        # Initial facts are still only the explicitly approved authority-A master.
        versions: dict[str, set[str]] = {}
        for fact in candidate_governance.product_facts:
            versions.setdefault(fact.canonical_product_id, set()).add(fact.source_version)
        for chunk in bundle.chunks:
            if chunk.record_type == "product":
                chunk.metadata.update(
                    {
                        "fact_source_versions": sorted(versions.get(chunk.product_id, set())),
                        "pending_fields": [],
                    }
                )
        return bundle, candidate_governance

    occurred_at = occurred_at or datetime.now(UTC).isoformat()
    approved = {
        (item["canonical_product_id"], item["field_name"]): _fact_from_snapshot(item)
        for item in approved_snapshot
    }
    approved_metadata = {item["id"]: item for item in approved_snapshot}
    candidates = {
        (fact.canonical_product_id, fact.field_name): fact
        for fact in candidate_governance.product_facts
    }
    sources = {source.id: source for source in bundle.sources}
    raw_products = {product.product_id: product for product in bundle.products}
    effective_facts: dict[tuple[str, str], ProductFact] = dict(approved)
    changes: list[ProductFactChange] = []

    for key, candidate in candidates.items():
        existing = approved.get(key)
        if existing is not None and _json_equal(existing.value, candidate.value):
            continue
        raw = raw_products[candidate.canonical_product_id]
        source = sources[candidate.source_document_id]
        change_id = stable_id(
            "fact-change",
            ":".join(
                [
                    candidate.canonical_product_id,
                    candidate.field_name,
                    json.dumps(candidate.value, ensure_ascii=False, sort_keys=True),
                    source.sha256,
                ]
            ),
        )
        changes.append(
            ProductFactChange(
                id=change_id,
                canonical_product_id=candidate.canonical_product_id,
                product_sku=raw.model,
                field_name=candidate.field_name,
                proposed_value=candidate.value,
                existing_value=existing.value if existing else None,
                source_document_id=source.id,
                source_file=source.filename,
                source_version=source.sha256,
                source_row=raw.source_row,
                evidence={
                    "authority_class": source.authority_class,
                    "source_date": source.source_date,
                    "source_file": source.filename,
                    "source_row": raw.source_row,
                    "source_version": source.sha256,
                },
                status="pending",
                created_at=occurred_at,
            )
        )
        if existing is None:
            effective_facts.pop(key, None)

    facts_by_product: dict[str, dict[str, ProductFact]] = {}
    for (product_id, field_name), fact in effective_facts.items():
        facts_by_product.setdefault(product_id, {})[field_name] = fact

    effective_products: list[ProductRecord] = []
    effective_chunks = [chunk for chunk in bundle.chunks if chunk.record_type != "product"]
    pending_by_product: dict[str, list[str]] = {}
    for change in changes:
        pending_by_product.setdefault(change.canonical_product_id, []).append(change.field_name)
    for raw in bundle.products:
        values = facts_by_product.get(raw.product_id, {})
        product = _effective_product(raw, values)
        if product is None:
            continue
        effective_products.append(product)
        source = sources[product.source_document_id]
        chunk = product_chunk(product, source)
        fields = {key: fact.value for key, fact in values.items()}
        content = "\n".join(f"{key}: {value}" for key, value in fields.items())
        chunk = replace(
            chunk,
            content=content,
            content_hash=content_hash(content),
            metadata={
                **chunk.metadata,
                "fields": fields,
                "source_version": values["canonical_product_id"].source_version,
                "fact_source_versions": sorted({fact.source_version for fact in values.values()}),
                "pending_fields": sorted(pending_by_product.get(product.product_id, [])),
            },
        )
        effective_chunks.append(chunk)

    for fact in effective_facts.values():
        if fact.change_id is None:
            continue
        metadata = approved_metadata[fact.id]
        values = facts_by_product[fact.canonical_product_id]
        effective_chunks.append(
            approved_fact_chunk(
                fact_id=fact.id,
                canonical_product_id=fact.canonical_product_id,
                model=str(values["model"].value),
                field_name=fact.field_name,
                value=fact.value,
                reason=fact.reason,
                source_document_id=fact.source_document_id,
                source_file=str(metadata["source_file"]),
                source_type=str(metadata["source_type"]),
                source_modified_at=str(metadata["source_modified_at"]),
                source_date=fact.source_date,
                source_version=fact.source_version,
                source_row=fact.source_row,
                authority_class=fact.authority_class,
                change_id=fact.change_id,
                approved_at=fact.approved_at,
                reviewer_id=fact.reviewer_id,
            )
        )

    effective_bundle = replace(
        bundle,
        products=effective_products,
        chunks=effective_chunks,
    )
    governed = build_governance(effective_bundle)
    governed_masters = []
    for master in governed.product_master:
        supported = dict(master.supported_attributes)
        unsupported = list(master.unsupported_fields)
        values = facts_by_product.get(master.canonical_product_id, {})
        for field_name, fact in values.items():
            if field_name in PRODUCT_RECORD_FIELDS or field_name in {
                "canonical_product_id",
                "model",
                "name",
                "category",
            }:
                continue
            supported[field_name] = fact.value
            unsupported = [item for item in unsupported if item != field_name]
        governed_masters.append(
            replace(
                master,
                supported_attributes=supported,
                unsupported_fields=sorted(unsupported),
                confidence=(
                    "human_approved"
                    if any(fact.change_id for fact in values.values())
                    else master.confidence
                ),
            )
        )
    governed = replace(
        governed,
        product_master=governed_masters,
        product_facts=sorted(
            effective_facts.values(),
            key=lambda fact: (fact.canonical_product_id, fact.field_name, fact.id),
        ),
        fact_changes=changes,
    )
    return effective_bundle, governed


class ProductFactApprovalService:
    """Minimal application service for proposed product-fact review."""

    def __init__(self, database: KnowledgeDatabase) -> None:
        self.database = database

    def list_changes(
        self, *, status: str | None = "pending", limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        return self.database.list_fact_changes(status=status, limit=limit, offset=offset)

    def inspect(self, change_id: str) -> dict[str, Any]:
        item = self.database.get_fact_change(change_id)
        if item is None:
            raise KeyError(change_id)
        return item

    def propose(
        self,
        *,
        product_id: str,
        field_name: str,
        proposed_value: Any,
        source_file: str,
        source_row: int,
        evidence: dict[str, Any],
        actor: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", field_name):
            raise ValueError("field_name must be lowercase snake_case")
        if field_name == "canonical_product_id":
            raise ValueError("canonical_product_id cannot be changed through fact approval")
        source = self.database.get_source_by_filename(source_file)
        if source is None:
            raise ValueError("source_file must be an indexed governed source")
        masters = {
            item["canonical_product_id"]: item for item in self.database.list_product_master()
        }
        master = masters.get(product_id)
        if master is None:
            raise ValueError(f"Unknown product ID: {product_id}")
        current = next(
            (
                item
                for item in self.database.list_current_product_facts()
                if item["canonical_product_id"] == product_id and item["field_name"] == field_name
            ),
            None,
        )
        if current is not None and _json_equal(current["value"], proposed_value):
            raise ValueError("The proposed value is already the approved current fact")
        safety_text = json.dumps(
            {"proposed_value": proposed_value, "evidence": evidence},
            ensure_ascii=False,
            sort_keys=True,
        )
        ensure_safe_for_general_index(safety_text, source_file=source_file)
        created_at = datetime.now(UTC).isoformat()
        change = ProductFactChange(
            id=stable_id(
                "fact-change",
                ":".join(
                    [
                        product_id,
                        field_name,
                        json.dumps(proposed_value, ensure_ascii=False, sort_keys=True),
                        source["sha256"],
                    ]
                ),
            ),
            canonical_product_id=product_id,
            product_sku=master["model"],
            field_name=field_name,
            proposed_value=proposed_value,
            existing_value=current["value"] if current else None,
            source_document_id=source["id"],
            source_file=source["filename"],
            source_version=source["sha256"],
            source_row=source_row,
            evidence={**evidence, "note": note} if note else evidence,
            status="pending",
            created_at=created_at,
        )
        self.database.insert_fact_change(change, actor=actor)
        return self.inspect(change.id)

    def approve(self, change_id: str, *, reviewer_id: str, reason: str) -> dict[str, Any]:
        return self.database.approve_fact_change(
            change_id,
            reviewer_id=reviewer_id,
            reason=reason,
            occurred_at=datetime.now(UTC).isoformat(),
        )

    def reject(self, change_id: str, *, reviewer_id: str, reason: str) -> dict[str, Any]:
        return self.database.reject_fact_change(
            change_id,
            reviewer_id=reviewer_id,
            reason=reason,
            occurred_at=datetime.now(UTC).isoformat(),
        )

    def supersede(self, change_id: str, *, reviewer_id: str, reason: str) -> dict[str, Any]:
        return self.database.supersede_fact_change(
            change_id,
            reviewer_id=reviewer_id,
            reason=reason,
            occurred_at=datetime.now(UTC).isoformat(),
        )
