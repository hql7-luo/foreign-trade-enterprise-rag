"""Authority and ambiguity derived from generic schemas, not document-specific prose."""

from __future__ import annotations

from collections import defaultdict

from app.domain import (
    ConflictRecord,
    GovernanceBundle,
    IngestionBundle,
    KnowledgeVersion,
    ProductFact,
    ProductMasterRecord,
)
from app.ingestion.loaders import ATTRIBUTE_FIELDS, SOURCE_POLICIES, stable_id

UNSUPPORTED_CURRENT_PRODUCT_FIELDS = sorted(
    ATTRIBUTE_FIELDS | {"inventory", "payment_terms", "incoterms"}
)


def _product_attributes(product) -> dict:
    # Compatibility metadata for the listing model; not physical product claims.
    return {
        "product_type": product.product_type,
        "product_tier": product.product_tier,
        "platform_reference_price_min_usd": product.price_min_usd,
        "platform_reference_price_max_usd": product.price_max_usd,
        "unit": product.unit,
        "last_updated": product.last_updated,
        "quality_score": product.quality_score,
        "review_status": product.review_status,
        "listing_status": product.listing_status,
        "country_controlled": product.country_controlled,
        "optimized": product.optimized,
        "showcase": product.showcase,
        "monthly_exposure": product.monthly_exposure,
    }


def build_governance(bundle: IngestionBundle) -> GovernanceBundle:
    sources = {source.id: source for source in bundle.sources}
    chunks = {chunk.product_id: chunk for chunk in bundle.chunks if chunk.record_type == "product"}
    masters, facts, versions, conflicts = [], [], [], []
    models = defaultdict(list)
    for product in bundle.products:
        source, chunk = sources[product.source_document_id], chunks[product.product_id]
        fields = {
            "canonical_product_id": product.product_id,
            "model": product.model,
            "name": product.title,
            "category": product.product_group,
            **_product_attributes(product),
            **chunk.metadata.get("fields", {}),
        }
        attributes = {
            key: value
            for key, value in fields.items()
            if key not in {"canonical_product_id", "model", "name", "category"}
        }
        masters.append(
            ProductMasterRecord(
                product.product_id,
                product.model,
                product.title,
                product.product_group,
                attributes,
                sorted(set(UNSUPPORTED_CURRENT_PRODUCT_FIELDS) - fields.keys()),
                source.id,
                product.source_row,
                source.source_date or "",
                source.authority_class,
                "verified_from_approved_source",
                "approved",
            )
        )
        for field, value in fields.items():
            facts.append(
                ProductFact(
                    stable_id("fact", f"{product.product_id}:{field}:{value}"),
                    product.product_id,
                    field,
                    value,
                    source.id,
                    product.source_row,
                    source.source_date or "",
                    source.authority_class,
                    "verified_from_approved_source",
                    "approved",
                    source.sha256,
                    source.source_modified_at,
                    "system:synthetic-catalog-bootstrap",
                    "Explicitly approved synthetic seed catalog",
                )
            )
        models[product.model].append(product)
    for source in bundle.sources:
        category, _, current = SOURCE_POLICIES[source.filename]
        versions.append(
            KnowledgeVersion(
                source.id, source.source_date, source.authority_class, category, current
            )
        )
    for model, products in models.items():
        if len(products) > 1:
            conflicts.append(
                ConflictRecord(
                    stable_id("conflict", f"model:{model}"),
                    "product_model",
                    model,
                    "canonical_product_id",
                    "ambiguous_identifier",
                    [
                        {
                            "canonical_product_id": p.product_id,
                            "name": p.title,
                            "source_row": p.source_row,
                        }
                        for p in products
                    ],
                    list({p.source_document_id for p in products}),
                    [chunks[p.product_id].id for p in products],
                    "Require canonical product ID; never silently choose a duplicate SKU.",
                    "unresolved",
                )
            )
    return GovernanceBundle(masters, facts, versions, conflicts)
