"""Allowlisted synthetic sources with row/section provenance and explicit fact schemas.

Only the packaged catalog is an initially approved master. Uploaded files are
handled separately by the quarantined proposal workflow, never by this loader.
"""

from __future__ import annotations

import csv
import hashlib
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.domain import Chunk, IngestionBundle, KnowledgeRecord, ProductRecord, SourceDocument
from app.security.filter import ensure_safe_for_general_index

NOTICE = "This file contains fully synthetic data created for portfolio demonstration purposes."
SOURCE_POLICIES = {
    "northstar-products.csv": ("current_product_listing", "A", True),
    "northstar-company-knowledge.md": ("company_knowledge", "B", True),
    "northstar-historical-rfqs.md": ("quotation_evidence", "C", False),
    "northstar-production-sop.md": ("operational_knowledge", "B", True),
    "northstar-rfq-demand-summary.csv": ("rfq_market_analytics", "D", False),
}
APPROVED_SOURCES = tuple(SOURCE_POLICIES)
LISTING_FIELDS = {
    "product_type",
    "product_tier",
    "quality_score",
    "review_status",
    "listing_status",
    "country_controlled",
    "optimized",
    "showcase",
    "monthly_exposure",
}
CHUNKING_STRATEGIES = {"legacy", "source_aware"}
IDENTITY_FIELDS = {
    "product_id",
    "sku",
    "name",
    "category",
    "date",
    "reference_min_usd",
    "reference_max_usd",
    "unit",
    "notice",
}
ATTRIBUTE_FIELDS = {
    "material",
    "dimensions",
    "packaging",
    "moq",
    "lead_time",
    "certificates",
    "logistics_or_freight",
    "capacity",
    "color",
    "current_price",
}


def stable_id(namespace: str, value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"northstar-public:{namespace}:{value}"))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(path: Path, date: str) -> SourceDocument:
    _, authority, _ = SOURCE_POLICIES[path.name]
    return SourceDocument(
        stable_id("source", path.name),
        path.name,
        path.name,
        path.suffix.lstrip("."),
        file_sha256(path),
        datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
        date,
        authority,
        "synthetic_public",
    )


def _chunk(
    source: SourceDocument,
    record_id: str,
    content: str,
    category: str,
    *,
    row: int,
    end: int | None = None,
    section: str | None = None,
    product_id: str | None = None,
    sku: str | None = None,
    record_type: str = "knowledge",
    metadata: dict | None = None,
) -> Chunk:
    return Chunk(
        id=stable_id("chunk", f"{source.filename}:{record_id}:{row}"),
        record_type=record_type,
        record_id=record_id,
        content=content,
        content_hash=content_hash(content),
        source_document_id=source.id,
        source_file=source.filename,
        source_type=source.source_type,
        source_modified_at=source.source_modified_at,
        source_date=source.source_date,
        authority_class=source.authority_class,
        confidentiality=source.confidentiality,
        category=category,
        section=section,
        row_start=row,
        row_end=end or row,
        product_id=product_id,
        model=sku,
        metadata={"source_version": source.sha256, **(metadata or {})},
    )


def product_fields(product: ProductRecord) -> dict:
    return {
        "canonical_product_id": product.product_id,
        "model": product.model,
        "name": product.title,
        "category": product.product_group,
        "platform_reference_price_min_usd": product.price_min_usd,
        "platform_reference_price_max_usd": product.price_max_usd,
        "unit": product.unit,
    }


def product_chunk(product: ProductRecord, source: SourceDocument) -> Chunk:
    fields = product_fields(product)
    return _chunk(
        source,
        product.product_id,
        "\n".join(f"{key}: {value}" for key, value in fields.items()),
        "current_product_listing",
        row=product.source_row,
        product_id=product.product_id,
        sku=product.model,
        record_type="product",
        metadata={"fields": fields, "governance_status": "approved"},
    )


def load_products(path: Path) -> tuple[SourceDocument, list[ProductRecord], list[Chunk]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if set(reader.fieldnames or []) != IDENTITY_FIELDS | ATTRIBUTE_FIELDS | LISTING_FIELDS:
            raise ValueError("Synthetic catalog schema mismatch")
        rows = list(reader)
    if not rows or len({row["date"] for row in rows}) != 1:
        raise ValueError("Catalog requires records from one explicit version date")
    source = _source(path, rows[0]["date"])
    products, chunks, seen = [], [], set()
    for row_number, row in enumerate(rows, start=2):
        if row["notice"] != NOTICE or not row["product_id"] or row["product_id"] in seen:
            raise ValueError(f"Invalid synthetic notice or duplicate identity at row {row_number}")
        seen.add(row["product_id"])
        minimum, maximum = float(row["reference_min_usd"]), float(row["reference_max_usd"])
        if not (0 < minimum <= maximum):
            raise ValueError("Invalid catalog reference price range")
        product = ProductRecord(
            product_id=row["product_id"],
            title=row["name"],
            model=row["sku"],
            product_group=row["category"],
            product_type=row["product_type"],
            product_tier=row["product_tier"],
            price_min_usd=minimum,
            price_max_usd=maximum,
            unit=row["unit"],
            last_updated=row["date"],
            quality_score=float(row["quality_score"]),
            review_status=row["review_status"],
            listing_status=row["listing_status"],
            country_controlled=row["country_controlled"] == "true",
            optimized=row["optimized"] == "true",
            showcase=row["showcase"] == "true",
            monthly_exposure=int(row["monthly_exposure"]),
            snapshot_date=row["date"],
            source_document_id=source.id,
            source_row=row_number,
        )
        fields = {
            **product_fields(product),
            **{key: row[key] for key in ATTRIBUTE_FIELDS if row[key].strip()},
        }
        content = "\n".join(f"{key}: {value}" for key, value in fields.items())
        chunks.append(
            _chunk(
                source,
                product.product_id,
                content,
                "current_product_listing",
                row=row_number,
                product_id=product.product_id,
                sku=product.model,
                record_type="product",
                metadata={"fields": fields, "governance_status": "approved"},
            )
        )
        products.append(product)
    return source, products, chunks


def _documents(
    path: Path, category: str
) -> tuple[SourceDocument, list[KnowledgeRecord], list[Chunk]]:
    text = path.read_text(encoding="utf-8")
    date = re.search(r"^Version date: (\d{4}-\d{2}-\d{2})$", text, re.M)
    if not date:
        raise ValueError("Documents require an explicit version date")
    source = _source(path, date.group(1))
    lines, headings, sections, start = text.splitlines(), [], [], None
    for number, line in enumerate(lines, start=1):
        heading = re.match(r"^(#{1,6}) (.+)$", line)
        if not heading:
            continue
        if start is not None:
            sections.append((" / ".join(headings), start, number - 1))
        level = len(heading.group(1))
        headings = headings[: level - 1] + [heading.group(2)]
        start = number
    if start is not None:
        sections.append((" / ".join(headings), start, len(lines)))
    records, chunks = [], []
    for section, first, last in sections:
        content = "\n".join(lines[first:last]).strip()
        # Preamble is never business evidence; semantic heading blocks stay intact.
        if not content or NOTICE in content:
            continue
        fields = {}
        for line in content.splitlines():
            key, separator, value = line.partition(": ")
            if separator:
                fields[key.strip().casefold().replace(" ", "_")] = value.strip()
        record_id = stable_id("record", f"{path.name}:{section}")
        records.append(
            KnowledgeRecord(
                record_id,
                category,
                section,
                content,
                source.authority_class,
                source.confidentiality,
                source.id,
                section,
                first + 1,
                last,
                fields.get("sku"),
            )
        )
        chunks.append(
            _chunk(
                source,
                record_id,
                content,
                category,
                row=first + 1,
                end=last,
                section=section,
                product_id=fields.get("product_id"),
                sku=fields.get("sku"),
                metadata={
                    "fields": fields,
                    "heading_path": section.split(" / "),
                    "chunk_role": "section",
                    "parent_section": section.rpartition(" / ")[0],
                },
            )
        )
    return source, records, chunks


def load_approved_sources(
    root: Path, *, chunking_strategy: str = "source_aware"
) -> IngestionBundle:
    if chunking_strategy not in CHUNKING_STRATEGIES:
        raise ValueError("Unknown chunking strategy")
    sources, products, records, chunks = [], [], [], []
    for name in APPROVED_SOURCES:
        path = root / name
        if path.is_symlink() or path.resolve().parent != root.resolve():
            raise ValueError("Source paths must remain inside the configured directory")
        text = path.read_text(encoding="utf-8")
        if NOTICE not in text:
            raise ValueError("Missing synthetic source notice")
        ensure_safe_for_general_index(text, source_file=name)
        category = SOURCE_POLICIES[name][0]
        if category == "current_product_listing":
            source, products, product_chunks = load_products(path)
            chunks.extend(product_chunks)
        elif path.suffix == ".md":
            source, new_records, new_chunks = _documents(path, category)
            records.extend(new_records)
            chunks.extend(new_chunks)
        else:
            with path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            source = _source(path, rows[0]["date"])
            for index, row in enumerate(rows, start=2):
                if row.pop("notice", "") != NOTICE:
                    raise ValueError("Missing synthetic analytics notice")
                record_id = stable_id("analytics", f"{name}:{index}")
                content = "\n".join(f"{key}: {value}" for key, value in row.items())
                records.append(
                    KnowledgeRecord(
                        record_id,
                        category,
                        row["category"],
                        content,
                        source.authority_class,
                        source.confidentiality,
                        source.id,
                        row["category"],
                        index,
                        index,
                    )
                )
                chunks.append(
                    _chunk(
                        source,
                        record_id,
                        content,
                        category,
                        row=index,
                        section=row["category"],
                        metadata={"fields": row},
                    )
                )
        sources.append(source)
    return IngestionBundle(
        sources, products, records, chunks, {source.filename: source.sha256 for source in sources}
    )
