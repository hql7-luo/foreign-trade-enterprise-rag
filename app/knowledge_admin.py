"""Product-master views and controlled administrator ingestion workflows."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.approval import ProductFactApprovalService
from app.config import Settings
from app.database import KnowledgeDatabase
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.staging import parse_staged_source
from app.rag.service import RagService
from app.security.filter import blocked_findings


class ProductMasterService:
    def __init__(self, database: KnowledgeDatabase) -> None:
        self.database = database

    def list_products(
        self, *, query: str | None = None, category: str | None = None
    ) -> list[dict[str, Any]]:
        facts = self.database.list_current_product_facts()
        facts_by_product: dict[str, list[dict[str, Any]]] = {}
        for fact in facts:
            facts_by_product.setdefault(fact["canonical_product_id"], []).append(fact)
        normalized_query = (query or "").strip().casefold()
        results = []
        for master in self.database.list_product_master():
            if category and master["category"] != category:
                continue
            searchable = " ".join(
                [master["canonical_product_id"], master["model"], master["name"]]
            ).casefold()
            if normalized_query and normalized_query not in searchable:
                continue
            results.append(
                {
                    **master,
                    "facts": facts_by_product.get(master["canonical_product_id"], []),
                }
            )
        return results

    def get_product(self, product_id: str) -> dict[str, Any]:
        items = self.list_products(query=product_id)
        item = next(
            (product for product in items if product["canonical_product_id"] == product_id),
            None,
        )
        if item is None:
            raise KeyError(product_id)
        return item

    def history(self, product_id: str, *, field_name: str | None = None) -> dict[str, Any]:
        product = self.get_product(product_id)
        facts = self.database.product_fact_history(product_id, field_name=field_name)
        changes = [
            item
            for item in self.database.list_fact_changes(status=None, limit=500)
            if item["canonical_product_id"] == product_id
            and (not field_name or item["field_name"] == field_name)
        ]
        conflicts = self.database.get_conflicts([product_id, product["model"]])
        return {
            "product_id": product_id,
            "product_sku": product["model"],
            "field_name": field_name,
            "facts": facts,
            "changes": changes,
            "conflicts": conflicts,
        }


class KnowledgeAdminService:
    def __init__(
        self,
        database: KnowledgeDatabase,
        rag_service: RagService,
        settings: Settings,
    ) -> None:
        self.database = database
        self.rag_service = rag_service
        self.settings = settings

    def list_sources(self) -> list[dict[str, Any]]:
        return self.database.list_source_summaries()

    def ingest_configured_source(
        self,
        *,
        progress_callback: Callable[[int, str], None] | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        source = self.settings.ingestion_source_path.resolve()
        if not source.is_dir():
            raise ValueError("The configured ingestion source directory does not exist")
        pipeline = IngestionPipeline(
            self.database,
            self.rag_service.retrieval.vector_store,
            self.rag_service.retrieval.embedder,
            chunking_strategy=self.settings.chunking_strategy,
        )
        return asdict(
            pipeline.run(
                source,
                progress_callback=progress_callback,
                cancellation_requested=cancellation_requested,
            )
        )

    def stage_source(self, *, filename: str, data: bytes, actor: str) -> dict[str, Any]:
        safe_name = Path(filename).name
        if not safe_name or safe_name != filename or len(safe_name) > 180:
            raise ValueError("Upload filename is invalid")
        if blocked_findings(safe_name):
            raise ValueError("Upload filename contains a sensitive identifier")
        if not data:
            raise ValueError("Upload is empty")
        if len(data) > self.settings.max_upload_bytes:
            raise ValueError("Upload exceeds the configured size limit")
        digest = hashlib.sha256(data).hexdigest()
        duplicate = next(
            (
                item
                for item in self.database.list_staged_sources(limit=500)
                if item["sha256"] == digest
            ),
            None,
        )
        if duplicate:
            raise ValueError(f"Duplicate source already staged as {duplicate['id']}")

        parsed = parse_staged_source(safe_name, data)
        source_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        extension = Path(safe_name).suffix.casefold().lstrip(".")
        blocked = bool(parsed.findings)
        stored_path: str | None = None
        if not blocked:
            self.settings.staging_path.mkdir(parents=True, exist_ok=True)
            self.settings.staging_path.chmod(0o700)
            path = self.settings.staging_path / f"{source_id}.{extension}"
            path.write_bytes(data)
            path.chmod(0o600)
            stored_path = str(path)
        item = {
            "id": source_id,
            "source_document_id": None,
            "original_filename": safe_name,
            "stored_path": stored_path,
            "source_type": extension,
            "sha256": digest,
            "size_bytes": len(data),
            "status": (
                "blocked"
                if blocked
                else "validated"
                if parsed.fact_updates
                else "unsupported_mapping"
            ),
            "findings_json": json.dumps(parsed.findings),
            "preview_json": json.dumps(parsed.preview, ensure_ascii=False),
            "fact_updates_json": json.dumps(parsed.fact_updates, ensure_ascii=False),
            "created_by": actor,
            "created_at": now,
            "proposed_at": None,
        }
        self.database.insert_staged_source(item)
        return self.database.get_staged_source(source_id) or {}

    def propose_staged_facts(self, source_id: str, *, actor: str) -> dict[str, Any]:
        staged = self.database.get_staged_source(source_id)
        if staged is None:
            raise KeyError(source_id)
        if staged["status"] != "validated" or not staged["fact_updates"]:
            raise ValueError("This staged source has no reviewable product-fact mapping")
        now = datetime.now(UTC).isoformat()
        governed_source_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"foreign-trade-rag:managed-source:{source_id}")
        )
        registered_filename = f"staged-{source_id[:8]}-{staged['original_filename']}"
        self.database.register_managed_source(
            source_id=governed_source_id,
            filename=registered_filename,
            relative_path=f"managed/{source_id}/{registered_filename}",
            source_type=staged["source_type"],
            sha256=staged["sha256"],
            source_modified_at=staged["created_at"],
            source_date=staged["created_at"][:10],
        )
        approval = ProductFactApprovalService(self.database)
        changes = []
        for update in staged["fact_updates"]:
            changes.append(
                approval.propose(
                    product_id=update["product_id"],
                    field_name=update["field_name"],
                    proposed_value=update["proposed_value"],
                    source_file=registered_filename,
                    source_row=update["source_row"],
                    evidence={
                        "staged_source_id": source_id,
                        "original_filename": staged["original_filename"],
                        "source_sha256": staged["sha256"],
                        "statement": (
                            f"{update['field_name']} = "
                            f"{json.dumps(update['proposed_value'], ensure_ascii=False)}"
                        ),
                    },
                    actor=actor,
                    note=update.get("note"),
                )
            )
        self.database.mark_staged_source_proposed(source_id, proposed_at=now)
        return {
            "source": self.database.get_staged_source(source_id),
            "changes": changes,
        }
