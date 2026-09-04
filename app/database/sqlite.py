from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.domain import (
    Chunk,
    GovernanceBundle,
    IngestionBundle,
    ProductFactChange,
    ProductRecord,
)
from app.governance_chunks import approved_fact_chunk

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    source_root_hash TEXT NOT NULL,
    files_seen INTEGER NOT NULL DEFAULT 0,
    products_indexed INTEGER NOT NULL DEFAULT 0,
    knowledge_records_indexed INTEGER NOT NULL DEFAULT 0,
    chunks_indexed INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK(status IN (
        'pending', 'running', 'completed', 'failed', 'cancelled'
    )),
    progress INTEGER NOT NULL CHECK(progress BETWEEN 0 AND 100),
    phase TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    result_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_created
ON ingestion_jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS source_documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    source_modified_at TEXT NOT NULL,
    source_date TEXT,
    authority_class TEXT NOT NULL,
    confidentiality TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    model TEXT NOT NULL,
    product_group TEXT NOT NULL,
    product_type TEXT NOT NULL,
    product_tier TEXT NOT NULL,
    price_min_usd REAL NOT NULL,
    price_max_usd REAL NOT NULL,
    unit TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    quality_score REAL NOT NULL,
    review_status TEXT NOT NULL,
    listing_status TEXT NOT NULL,
    country_controlled INTEGER NOT NULL,
    optimized INTEGER NOT NULL,
    showcase INTEGER NOT NULL,
    monthly_exposure INTEGER NOT NULL,
    snapshot_date TEXT NOT NULL,
    source_document_id TEXT NOT NULL REFERENCES source_documents(id),
    source_row INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_model ON products(model);
CREATE INDEX IF NOT EXISTS idx_products_group ON products(product_group);

CREATE TABLE IF NOT EXISTS knowledge_records (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    authority_class TEXT NOT NULL,
    confidentiality TEXT NOT NULL,
    source_document_id TEXT NOT NULL REFERENCES source_documents(id),
    section TEXT NOT NULL,
    row_start INTEGER,
    row_end INTEGER,
    model TEXT
);

CREATE INDEX IF NOT EXISTS idx_knowledge_category ON knowledge_records(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_model ON knowledge_records(model);

CREATE TABLE IF NOT EXISTS indexed_chunks (
    id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source_document_id TEXT NOT NULL REFERENCES source_documents(id),
    source_file TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_modified_at TEXT NOT NULL,
    source_date TEXT,
    authority_class TEXT NOT NULL,
    confidentiality TEXT NOT NULL,
    category TEXT NOT NULL,
    section TEXT,
    row_start INTEGER,
    row_end INTEGER,
    sheet TEXT,
    product_id TEXT,
    model TEXT,
    metadata_json TEXT NOT NULL,
    UNIQUE(source_document_id, section, row_start, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_chunks_product_id ON indexed_chunks(product_id);
CREATE INDEX IF NOT EXISTS idx_chunks_model ON indexed_chunks(model);
CREATE INDEX IF NOT EXISTS idx_chunks_category ON indexed_chunks(category);

CREATE TABLE IF NOT EXISTS product_master (
    canonical_product_id TEXT PRIMARY KEY REFERENCES products(product_id),
    model TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    supported_attributes_json TEXT NOT NULL,
    unsupported_fields_json TEXT NOT NULL,
    source_document_id TEXT NOT NULL REFERENCES source_documents(id),
    source_row INTEGER NOT NULL,
    source_date TEXT NOT NULL,
    authority_class TEXT NOT NULL,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_product_master_model ON product_master(model);

CREATE TABLE IF NOT EXISTS current_product_facts (
    id TEXT PRIMARY KEY,
    canonical_product_id TEXT NOT NULL REFERENCES product_master(canonical_product_id),
    field_name TEXT NOT NULL,
    value_json TEXT NOT NULL,
    source_document_id TEXT NOT NULL REFERENCES source_documents(id),
    source_row INTEGER NOT NULL,
    source_date TEXT NOT NULL,
    authority_class TEXT NOT NULL,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL,
    source_version TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    change_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_current_facts_entity_field
ON current_product_facts(canonical_product_id, field_name);

CREATE TABLE IF NOT EXISTS knowledge_versions (
    source_document_id TEXT PRIMARY KEY REFERENCES source_documents(id),
    version_date TEXT,
    authority_class TEXT NOT NULL,
    status TEXT NOT NULL,
    is_current INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_conflicts (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    field_name TEXT NOT NULL,
    conflict_type TEXT NOT NULL,
    values_json TEXT NOT NULL,
    source_document_ids_json TEXT NOT NULL,
    evidence_chunk_ids_json TEXT NOT NULL,
    resolution_policy TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conflicts_entity ON knowledge_conflicts(entity_type, entity_key);

CREATE TABLE IF NOT EXISTS retrieval_state (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS product_fact_changes (
    id TEXT PRIMARY KEY,
    canonical_product_id TEXT NOT NULL,
    product_sku TEXT NOT NULL,
    field_name TEXT NOT NULL,
    proposed_value_json TEXT NOT NULL,
    existing_value_json TEXT,
    source_document_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    evidence_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'superseded')),
    created_at TEXT NOT NULL,
    decided_at TEXT,
    reviewer_id TEXT,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_fact_changes_status
ON product_fact_changes(status, created_at);

CREATE INDEX IF NOT EXISTS idx_fact_changes_entity_field
ON product_fact_changes(canonical_product_id, field_name, status);

CREATE TABLE IF NOT EXISTS product_fact_change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    change_id TEXT NOT NULL REFERENCES product_fact_changes(id),
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT,
    occurred_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fact_change_events_change
ON product_fact_change_events(change_id, id);

CREATE TABLE IF NOT EXISTS staged_sources (
    id TEXT PRIMARY KEY,
    source_document_id TEXT,
    original_filename TEXT NOT NULL,
    stored_path TEXT,
    source_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'blocked', 'validated', 'review_items_created', 'unsupported_mapping'
    )),
    findings_json TEXT NOT NULL,
    preview_json TEXT NOT NULL,
    fact_updates_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    proposed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_staged_sources_created
ON staged_sources(created_at DESC);
"""


class KnowledgeDatabase:
    """Small synchronous SQLite repository used by ingestion and FastAPI threads."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
            self._migrate_current_product_facts(connection)
            connection.commit()
        self.path.chmod(0o600)

    @staticmethod
    def _migrate_current_product_facts(connection: sqlite3.Connection) -> None:
        """Upgrade the legacy fact table while retaining its approved baseline."""

        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(current_product_facts)")
        }
        indexes = connection.execute("PRAGMA index_list(current_product_facts)").fetchall()
        has_legacy_unique = any(row["unique"] and row["origin"] == "u" for row in indexes)
        required = {"source_version", "approved_at", "reviewer_id", "reason", "change_id"}
        if required.issubset(columns) and not has_legacy_unique:
            return

        legacy_columns = columns
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "ALTER TABLE current_product_facts RENAME TO current_product_facts_legacy"
        )
        connection.execute(
            """
            CREATE TABLE current_product_facts (
                id TEXT PRIMARY KEY,
                canonical_product_id TEXT NOT NULL REFERENCES product_master(canonical_product_id),
                field_name TEXT NOT NULL,
                value_json TEXT NOT NULL,
                source_document_id TEXT NOT NULL REFERENCES source_documents(id),
                source_row INTEGER NOT NULL,
                source_date TEXT NOT NULL,
                authority_class TEXT NOT NULL,
                confidence TEXT NOT NULL,
                status TEXT NOT NULL,
                source_version TEXT NOT NULL,
                approved_at TEXT NOT NULL,
                reviewer_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                change_id TEXT
            )
            """
        )
        source_version = (
            "source_version"
            if "source_version" in legacy_columns
            else "COALESCE((SELECT sha256 FROM source_documents s "
            "WHERE s.id = current_product_facts_legacy.source_document_id), 'unknown')"
        )
        approved_at = (
            "approved_at" if "approved_at" in legacy_columns else "source_date || 'T00:00:00+00:00'"
        )
        reviewer_id = (
            "reviewer_id" if "reviewer_id" in legacy_columns else "'system:stage3-migration'"
        )
        reason = (
            "reason"
            if "reason" in legacy_columns
            else "'Migrated from the approved legacy product master'"
        )
        change_id = "change_id" if "change_id" in legacy_columns else "NULL"
        connection.execute(
            f"""
            INSERT INTO current_product_facts(
                id, canonical_product_id, field_name, value_json,
                source_document_id, source_row, source_date, authority_class,
                confidence, status, source_version, approved_at, reviewer_id,
                reason, change_id
            )
            SELECT id, canonical_product_id, field_name, value_json,
                   source_document_id, source_row, source_date, authority_class,
                   confidence,
                   CASE WHEN status = 'current_listing_snapshot' THEN 'approved' ELSE status END,
                   {source_version}, {approved_at}, {reviewer_id}, {reason}, {change_id}
            FROM current_product_facts_legacy
            """
        )
        connection.execute("DROP TABLE current_product_facts_legacy")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_current_facts_entity_field
            ON current_product_facts(canonical_product_id, field_name, status)
            """
        )
        connection.execute("PRAGMA foreign_keys = ON")

    def begin_ingestion_run(self, run_id: str, source_root_hash: str) -> None:
        self.initialize()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO ingestion_runs(id, started_at, status, source_root_hash)
                VALUES (?, ?, 'running', ?)
                """,
                (run_id, datetime.now(UTC).isoformat(), source_root_hash),
            )
            connection.commit()

    def fail_ingestion_run(self, run_id: str, error: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE ingestion_runs
                SET completed_at = ?, status = 'failed', error = ?
                WHERE id = ?
                """,
                (datetime.now(UTC).isoformat(), error[:1000], run_id),
            )
            connection.commit()

    def create_ingestion_job(self, *, job_id: str, actor: str, created_at: str) -> dict[str, Any]:
        self.initialize()
        with self.connect() as connection, connection:
            active = connection.execute(
                "SELECT id FROM ingestion_jobs WHERE status IN ('pending', 'running') LIMIT 1"
            ).fetchone()
            if active:
                raise ValueError(f"Ingestion job {active['id']} is already active")
            connection.execute(
                """
                INSERT INTO ingestion_jobs(
                    id, status, progress, phase, created_by, created_at, cancel_requested
                ) VALUES (?, 'pending', 0, 'queued', ?, ?, 0)
                """,
                (job_id, actor, created_at),
            )
        return self.get_ingestion_job(job_id) or {}

    def start_ingestion_job(self, job_id: str, *, started_at: str) -> bool:
        self.initialize()
        with self.connect() as connection, connection:
            cursor = connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'running', progress = 2, phase = 'starting', started_at = ?
                WHERE id = ? AND status = 'pending' AND cancel_requested = 0
                """,
                (started_at, job_id),
            )
        return bool(cursor.rowcount)

    def update_ingestion_job(self, job_id: str, *, progress: int, phase: str) -> None:
        self.initialize()
        with self.connect() as connection, connection:
            connection.execute(
                """
                UPDATE ingestion_jobs SET progress = ?, phase = ?
                WHERE id = ? AND status = 'running'
                """,
                (progress, phase, job_id),
            )

    def complete_ingestion_job(
        self, job_id: str, *, result: dict[str, Any], completed_at: str
    ) -> None:
        self.initialize()
        with self.connect() as connection, connection:
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'completed', progress = 100, phase = 'complete',
                    completed_at = ?, result_json = ?, error_message = NULL
                WHERE id = ? AND status = 'running'
                """,
                (completed_at, json.dumps(result, ensure_ascii=False, sort_keys=True), job_id),
            )

    def fail_ingestion_job(self, job_id: str, *, error: str, completed_at: str) -> None:
        self.initialize()
        with self.connect() as connection, connection:
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'failed', phase = 'failed', completed_at = ?, error_message = ?
                WHERE id = ? AND status IN ('pending', 'running')
                """,
                (completed_at, error[:500], job_id),
            )

    def request_ingestion_job_cancel(self, job_id: str, *, completed_at: str) -> dict[str, Any]:
        self.initialize()
        with self.connect() as connection, connection:
            row = connection.execute(
                "SELECT status, progress FROM ingestion_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] not in {"pending", "running"}:
                raise ValueError(f"Ingestion job is already {row['status']}")
            if row["progress"] >= 70:
                raise ValueError("Ingestion has passed the safe cancellation point")
            if row["status"] == "pending":
                connection.execute(
                    """
                    UPDATE ingestion_jobs
                    SET status = 'cancelled', phase = 'cancelled', progress = 0,
                        cancel_requested = 1, completed_at = ? WHERE id = ?
                    """,
                    (completed_at, job_id),
                )
            else:
                connection.execute(
                    "UPDATE ingestion_jobs SET cancel_requested = 1 WHERE id = ?",
                    (job_id,),
                )
        return self.get_ingestion_job(job_id) or {}

    def mark_ingestion_job_cancelled(self, job_id: str, *, completed_at: str) -> None:
        self.initialize()
        with self.connect() as connection, connection:
            connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'cancelled', phase = 'cancelled', completed_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (completed_at, job_id),
            )

    def ingestion_job_cancel_requested(self, job_id: str) -> bool:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM ingestion_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def recover_interrupted_ingestion_jobs(self, *, recovered_at: str) -> int:
        self.initialize()
        with self.connect() as connection, connection:
            cursor = connection.execute(
                """
                UPDATE ingestion_jobs
                SET status = 'failed', phase = 'interrupted', completed_at = ?,
                    error_message = 'Backend restarted before this job completed. Start a new job.'
                WHERE status IN ('pending', 'running')
                """,
                (recovered_at,),
            )
        return int(cursor.rowcount)

    def get_ingestion_job(self, job_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._ingestion_job_row(row) if row else None

    def list_ingestion_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM ingestion_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._ingestion_job_row(row) for row in rows]

    @staticmethod
    def _ingestion_job_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["cancel_requested"] = bool(item["cancel_requested"])
        result_json = item.pop("result_json")
        item["result"] = json.loads(result_json) if result_json else None
        item["cancellable"] = item["status"] in {"pending", "running"} and item["progress"] < 70
        return item

    def rebuild(
        self,
        bundle: IngestionBundle,
        *,
        governance: GovernanceBundle,
        run_id: str,
        retrieval_state: dict[str, Any],
    ) -> None:
        self.initialize()
        with self.connect() as connection:
            with connection:
                retained_fact_history = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM current_product_facts WHERE status = 'superseded'"
                    ).fetchall()
                ]
                retained_managed_sources = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM source_documents WHERE relative_path LIKE 'managed/%'"
                    ).fetchall()
                ]
                retained_managed_versions = {
                    row["source_document_id"]: dict(row)
                    for row in connection.execute(
                        """
                        SELECT v.* FROM knowledge_versions v
                        JOIN source_documents s ON s.id = v.source_document_id
                        WHERE s.relative_path LIKE 'managed/%'
                        """
                    ).fetchall()
                }
                connection.execute("DELETE FROM knowledge_conflicts")
                connection.execute("DELETE FROM knowledge_versions")
                connection.execute("DELETE FROM current_product_facts")
                connection.execute("DELETE FROM product_master")
                connection.execute("DELETE FROM indexed_chunks")
                connection.execute("DELETE FROM knowledge_records")
                connection.execute("DELETE FROM products")
                connection.execute("DELETE FROM source_documents")
                connection.execute("DELETE FROM retrieval_state")

                connection.executemany(
                    """
                    INSERT INTO source_documents(
                        id, filename, relative_path, source_type, sha256,
                        source_modified_at, source_date, authority_class, confidentiality
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            source.id,
                            source.filename,
                            source.relative_path,
                            source.source_type,
                            source.sha256,
                            source.source_modified_at,
                            source.source_date,
                            source.authority_class,
                            source.confidentiality,
                        )
                        for source in bundle.sources
                    ],
                )
                bundle_source_ids = {source.id for source in bundle.sources}
                connection.executemany(
                    """
                    INSERT INTO source_documents(
                        id, filename, relative_path, source_type, sha256,
                        source_modified_at, source_date, authority_class, confidentiality
                    ) VALUES (
                        :id, :filename, :relative_path, :source_type, :sha256,
                        :source_modified_at, :source_date, :authority_class, :confidentiality
                    )
                    """,
                    [
                        source
                        for source in retained_managed_sources
                        if source["id"] not in bundle_source_ids
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO products(
                        product_id, title, model, product_group, product_type,
                        product_tier, price_min_usd, price_max_usd, unit,
                        last_updated, quality_score, review_status, listing_status,
                        country_controlled, optimized, showcase, monthly_exposure,
                        snapshot_date, source_document_id, source_row
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item.product_id,
                            item.title,
                            item.model,
                            item.product_group,
                            item.product_type,
                            item.product_tier,
                            item.price_min_usd,
                            item.price_max_usd,
                            item.unit,
                            item.last_updated,
                            item.quality_score,
                            item.review_status,
                            item.listing_status,
                            int(item.country_controlled),
                            int(item.optimized),
                            int(item.showcase),
                            item.monthly_exposure,
                            item.snapshot_date,
                            item.source_document_id,
                            item.source_row,
                        )
                        for item in bundle.products
                    ],
                )
                governance_source_ids = {
                    item.source_document_id for item in governance.knowledge_versions
                }
                connection.executemany(
                    """
                    INSERT INTO knowledge_versions(
                        source_document_id, version_date, authority_class, status, is_current
                    ) VALUES (
                        :source_document_id, :version_date, :authority_class, :status, :is_current
                    )
                    """,
                    [
                        version
                        for source_id, version in retained_managed_versions.items()
                        if source_id not in governance_source_ids
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO knowledge_records(
                        id, category, title, content, authority_class, confidentiality,
                        source_document_id, section, row_start, row_end, model
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item.id,
                            item.category,
                            item.title,
                            item.content,
                            item.authority_class,
                            item.confidentiality,
                            item.source_document_id,
                            item.section,
                            item.row_start,
                            item.row_end,
                            item.model,
                        )
                        for item in bundle.knowledge_records
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO indexed_chunks(
                        id, record_type, record_id, content, content_hash,
                        source_document_id, source_file, source_type,
                        source_modified_at, source_date, authority_class,
                        confidentiality, category, section, row_start, row_end,
                        sheet, product_id, model, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [self._chunk_values(chunk) for chunk in bundle.chunks],
                )
                connection.executemany(
                    """
                    INSERT INTO product_master(
                        canonical_product_id, model, name, category,
                        supported_attributes_json, unsupported_fields_json,
                        source_document_id, source_row, source_date, authority_class,
                        confidence, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item.canonical_product_id,
                            item.model,
                            item.name,
                            item.category,
                            json.dumps(
                                item.supported_attributes, ensure_ascii=False, sort_keys=True
                            ),
                            json.dumps(item.unsupported_fields, ensure_ascii=False),
                            item.source_document_id,
                            item.source_row,
                            item.source_date,
                            item.authority_class,
                            item.confidence,
                            item.status,
                        )
                        for item in governance.product_master
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO current_product_facts(
                        id, canonical_product_id, field_name, value_json,
                        source_document_id, source_row, source_date, authority_class,
                        confidence, status, source_version, approved_at,
                        reviewer_id, reason, change_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item.id,
                            item.canonical_product_id,
                            item.field_name,
                            json.dumps(item.value, ensure_ascii=False, sort_keys=True),
                            item.source_document_id,
                            item.source_row,
                            item.source_date,
                            item.authority_class,
                            item.confidence,
                            item.status,
                            item.source_version,
                            item.approved_at,
                            item.reviewer_id,
                            item.reason,
                            item.change_id,
                        )
                        for item in governance.product_facts
                    ],
                )
                approved_ids = {item.id for item in governance.product_facts}
                retained_fact_history = [
                    row
                    for row in retained_fact_history
                    if row["id"] not in approved_ids
                    and connection.execute(
                        "SELECT 1 FROM product_master WHERE canonical_product_id = ?",
                        (row["canonical_product_id"],),
                    ).fetchone()
                    and connection.execute(
                        "SELECT 1 FROM source_documents WHERE id = ?",
                        (row["source_document_id"],),
                    ).fetchone()
                ]
                connection.executemany(
                    """
                    INSERT INTO current_product_facts(
                        id, canonical_product_id, field_name, value_json,
                        source_document_id, source_row, source_date, authority_class,
                        confidence, status, source_version, approved_at,
                        reviewer_id, reason, change_id
                    ) VALUES (
                        :id, :canonical_product_id, :field_name, :value_json,
                        :source_document_id, :source_row, :source_date, :authority_class,
                        :confidence, :status, :source_version, :approved_at,
                        :reviewer_id, :reason, :change_id
                    )
                    """,
                    retained_fact_history,
                )
                for change in governance.fact_changes:
                    self._insert_fact_change(connection, change, actor="system:ingestion")
                self._rebuild_approved_fact_chunks(connection)
                connection.executemany(
                    """
                    INSERT INTO knowledge_versions(
                        source_document_id, version_date, authority_class, status, is_current
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item.source_document_id,
                            item.version_date,
                            item.authority_class,
                            item.status,
                            int(item.is_current),
                        )
                        for item in governance.knowledge_versions
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO knowledge_conflicts(
                        id, entity_type, entity_key, field_name, conflict_type,
                        values_json, source_document_ids_json, evidence_chunk_ids_json,
                        resolution_policy, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item.id,
                            item.entity_type,
                            item.entity_key,
                            item.field_name,
                            item.conflict_type,
                            json.dumps(item.values, ensure_ascii=False, sort_keys=True),
                            json.dumps(item.source_document_ids, ensure_ascii=False),
                            json.dumps(item.evidence_chunk_ids, ensure_ascii=False),
                            item.resolution_policy,
                            item.status,
                        )
                        for item in governance.conflicts
                    ],
                )
                connection.executemany(
                    "INSERT INTO retrieval_state(key, value_json) VALUES (?, ?)",
                    [
                        (key, json.dumps(value, ensure_ascii=False, sort_keys=True))
                        for key, value in retrieval_state.items()
                    ],
                )
                connection.execute(
                    """
                    UPDATE ingestion_runs
                    SET completed_at = ?, status = 'complete', files_seen = ?,
                        products_indexed = ?, knowledge_records_indexed = ?, chunks_indexed = ?
                    WHERE id = ?
                    """,
                    (
                        datetime.now(UTC).isoformat(),
                        len(bundle.sources),
                        len(bundle.products),
                        len(bundle.knowledge_records),
                        len(bundle.chunks),
                        run_id,
                    ),
                )

    @staticmethod
    def _chunk_values(chunk: Chunk) -> tuple[Any, ...]:
        return (
            chunk.id,
            chunk.record_type,
            chunk.record_id,
            chunk.content,
            chunk.content_hash,
            chunk.source_document_id,
            chunk.source_file,
            chunk.source_type,
            chunk.source_modified_at,
            chunk.source_date,
            chunk.authority_class,
            chunk.confidentiality,
            chunk.category,
            chunk.section,
            chunk.row_start,
            chunk.row_end,
            chunk.sheet,
            chunk.product_id,
            chunk.model,
            json.dumps(chunk.metadata, ensure_ascii=False, sort_keys=True),
        )

    @staticmethod
    def _change_values(change: ProductFactChange) -> tuple[Any, ...]:
        return (
            change.id,
            change.canonical_product_id,
            change.product_sku,
            change.field_name,
            json.dumps(change.proposed_value, ensure_ascii=False, sort_keys=True),
            json.dumps(change.existing_value, ensure_ascii=False, sort_keys=True),
            change.source_document_id,
            change.source_file,
            change.source_version,
            change.source_row,
            json.dumps(change.evidence, ensure_ascii=False, sort_keys=True),
            change.status,
            change.created_at,
            change.decided_at,
            change.reviewer_id,
            change.reason,
        )

    @classmethod
    def _insert_fact_change(
        cls,
        connection: sqlite3.Connection,
        change: ProductFactChange,
        *,
        actor: str,
    ) -> bool:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO product_fact_changes(
                id, canonical_product_id, product_sku, field_name,
                proposed_value_json, existing_value_json, source_document_id,
                source_file, source_version, source_row, evidence_json, status,
                created_at, decided_at, reviewer_id, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            cls._change_values(change),
        )
        if not cursor.rowcount:
            return False
        connection.execute(
            """
            INSERT INTO product_fact_change_events(
                change_id, from_status, to_status, actor, reason, occurred_at, details_json
            ) VALUES (?, NULL, ?, ?, ?, ?, ?)
            """,
            (
                change.id,
                change.status,
                actor,
                "Conflicting or new source-backed fact requires approval",
                change.created_at,
                json.dumps(change.evidence, ensure_ascii=False, sort_keys=True),
            ),
        )
        return True

    @classmethod
    def _rebuild_approved_fact_chunks(cls, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM indexed_chunks WHERE record_type = 'approved_product_fact'")
        rows = connection.execute(
            """
            SELECT f.*, p.model, s.filename, s.source_type, s.source_modified_at
            FROM current_product_facts f
            JOIN products p ON p.product_id = f.canonical_product_id
            JOIN source_documents s ON s.id = f.source_document_id
            WHERE f.status = 'approved' AND f.change_id IS NOT NULL
            ORDER BY f.canonical_product_id, f.field_name
            """
        ).fetchall()
        for row in rows:
            value = json.loads(row["value_json"])
            chunk = approved_fact_chunk(
                fact_id=row["id"],
                canonical_product_id=row["canonical_product_id"],
                model=row["model"],
                field_name=row["field_name"],
                value=value,
                reason=row["reason"],
                source_document_id=row["source_document_id"],
                source_file=row["filename"],
                source_type=row["source_type"],
                source_modified_at=row["source_modified_at"],
                source_date=row["source_date"],
                source_version=row["source_version"],
                source_row=row["source_row"],
                authority_class=row["authority_class"],
                change_id=row["change_id"],
                approved_at=row["approved_at"],
                reviewer_id=row["reviewer_id"],
            )
            connection.execute(
                """
                INSERT INTO indexed_chunks(
                    id, record_type, record_id, content, content_hash,
                    source_document_id, source_file, source_type,
                    source_modified_at, source_date, authority_class,
                    confidentiality, category, section, row_start, row_end,
                    sheet, product_id, model, metadata_json
                ) VALUES (?, 'approved_product_fact', ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'internal', 'approved_product_fact', ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    chunk.id,
                    chunk.record_id,
                    chunk.content,
                    chunk.content_hash,
                    chunk.source_document_id,
                    chunk.source_file,
                    chunk.source_type,
                    chunk.source_modified_at,
                    chunk.source_date,
                    chunk.authority_class,
                    chunk.section,
                    chunk.row_start,
                    chunk.row_end,
                    chunk.product_id,
                    chunk.model,
                    json.dumps(chunk.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )

    def counts(self) -> dict[str, int]:
        self.initialize()
        with self.connect() as connection:
            names = (
                "source_documents",
                "products",
                "knowledge_records",
                "indexed_chunks",
                "product_master",
                "current_product_facts",
                "knowledge_versions",
                "knowledge_conflicts",
                "product_fact_changes",
                "product_fact_change_events",
                "staged_sources",
                "ingestion_jobs",
            )
            return {
                name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in names
            }

    def list_products(self) -> list[ProductRecord]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM products ORDER BY product_id").fetchall()
        return [self._row_to_product(row) for row in rows]

    def get_products(self, product_ids: Iterable[str]) -> list[ProductRecord]:
        ids = list(dict.fromkeys(product_ids))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM products WHERE product_id IN ({placeholders}) ORDER BY product_id",
                ids,
            ).fetchall()
        return [self._row_to_product(row) for row in rows]

    @staticmethod
    def _row_to_product(row: sqlite3.Row) -> ProductRecord:
        return ProductRecord(
            product_id=row["product_id"],
            title=row["title"],
            model=row["model"],
            product_group=row["product_group"],
            product_type=row["product_type"],
            product_tier=row["product_tier"],
            price_min_usd=row["price_min_usd"],
            price_max_usd=row["price_max_usd"],
            unit=row["unit"],
            last_updated=row["last_updated"],
            quality_score=row["quality_score"],
            review_status=row["review_status"],
            listing_status=row["listing_status"],
            country_controlled=bool(row["country_controlled"]),
            optimized=bool(row["optimized"]),
            showcase=bool(row["showcase"]),
            monthly_exposure=row["monthly_exposure"],
            snapshot_date=row["snapshot_date"],
            source_document_id=row["source_document_id"],
            source_row=row["source_row"],
        )

    def get_chunks(self, chunk_ids: Iterable[str]) -> dict[str, Chunk]:
        ids = list(dict.fromkeys(chunk_ids))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM indexed_chunks WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        return {row["id"]: self._row_to_chunk(row) for row in rows}

    def get_product_chunks(self, product_ids: Iterable[str]) -> list[Chunk]:
        ids = list(dict.fromkeys(product_ids))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM indexed_chunks
                WHERE product_id IN ({placeholders})
                  AND record_type IN ('product', 'approved_product_fact')
                ORDER BY product_id, record_type, row_start
                """,
                ids,
            ).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    def get_chunks_by_categories(self, categories: Iterable[str]) -> list[Chunk]:
        values = list(dict.fromkeys(categories))
        if not values:
            return []
        placeholders = ",".join("?" for _ in values)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM indexed_chunks
                WHERE category IN ({placeholders})
                ORDER BY authority_class, source_file, row_start
                """,
                values,
            ).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    def get_sibling_chunks(self, parent_ids: Iterable[str]) -> list[Chunk]:
        """Return source-aware child chunks for the specified stable parent IDs."""

        ids = list(dict.fromkeys(parent_ids))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM indexed_chunks
                WHERE json_extract(metadata_json, '$.chunk_role') = 'child'
                  AND json_extract(metadata_json, '$.parent_chunk_id') IN ({placeholders})
                ORDER BY source_file, section, row_start, id
                """,
                ids,
            ).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> Chunk:
        return Chunk(
            id=row["id"],
            record_type=row["record_type"],
            record_id=row["record_id"],
            content=row["content"],
            content_hash=row["content_hash"],
            source_document_id=row["source_document_id"],
            source_file=row["source_file"],
            source_type=row["source_type"],
            source_modified_at=row["source_modified_at"],
            source_date=row["source_date"],
            authority_class=row["authority_class"],
            confidentiality=row["confidentiality"],
            category=row["category"],
            section=row["section"],
            row_start=row["row_start"],
            row_end=row["row_end"],
            sheet=row["sheet"],
            product_id=row["product_id"],
            model=row["model"],
            metadata=json.loads(row["metadata_json"]),
        )

    def get_retrieval_state(self, key: str) -> Any:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM retrieval_state WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Knowledge base is not ingested; retrieval state is missing")
        return json.loads(row["value_json"])

    def latest_ingestion_run(self) -> dict[str, Any] | None:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM ingestion_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def list_product_master(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM product_master ORDER BY canonical_product_id"
            ).fetchall()
        results = [dict(row) for row in rows]
        for item in results:
            item["supported_attributes"] = json.loads(item.pop("supported_attributes_json"))
            item["unsupported_fields"] = json.loads(item.pop("unsupported_fields_json"))
        return results

    def get_product_master(self, product_id: str) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in self.list_product_master()
                if item["canonical_product_id"] == product_id
            ),
            None,
        )

    def list_current_product_facts(self, *, status: str = "approved") -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT f.*, p.model AS product_sku, s.filename AS source_file,
                       s.source_type, s.source_modified_at
                FROM current_product_facts f
                JOIN product_master p ON p.canonical_product_id = f.canonical_product_id
                JOIN source_documents s ON s.id = f.source_document_id
                WHERE f.status = ?
                ORDER BY f.canonical_product_id, f.field_name, f.approved_at DESC
                """,
                (status,),
            ).fetchall()
        return [self._fact_row(row) for row in rows]

    @staticmethod
    def _fact_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["value"] = json.loads(item.pop("value_json"))
        return item

    def list_fact_changes(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.initialize()
        query = "SELECT * FROM product_fact_changes"
        values: list[Any] = []
        if status is not None:
            query += " WHERE status = ?"
            values.append(status)
        query += " ORDER BY created_at, id LIMIT ? OFFSET ?"
        values.extend([limit, offset])
        with self.connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._change_row(row) for row in rows]

    def get_fact_change(self, change_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM product_fact_changes WHERE id = ?", (change_id,)
            ).fetchone()
            if row is None:
                return None
            events = connection.execute(
                """
                SELECT id, from_status, to_status, actor, reason, occurred_at, details_json
                FROM product_fact_change_events
                WHERE change_id = ? ORDER BY id
                """,
                (change_id,),
            ).fetchall()
        item = self._change_row(row)
        item["events"] = [
            {
                **{key: event[key] for key in event.keys() if key != "details_json"},
                "details": json.loads(event["details_json"]),
            }
            for event in events
        ]
        return item

    @staticmethod
    def _change_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["proposed_value"] = json.loads(item.pop("proposed_value_json"))
        existing = item.pop("existing_value_json")
        item["existing_value"] = json.loads(existing) if existing is not None else None
        item["evidence"] = json.loads(item.pop("evidence_json"))
        return item

    def insert_fact_change(self, change: ProductFactChange, *, actor: str) -> bool:
        self.initialize()
        with self.connect() as connection, connection:
            return self._insert_fact_change(connection, change, actor=actor)

    def get_source_by_filename(self, filename: str) -> dict[str, Any] | None:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM source_documents WHERE filename = ?", (filename,)
            ).fetchone()
        return dict(row) if row else None

    def list_source_summaries(self) -> list[dict[str, Any]]:
        """Return governed source metadata without filesystem paths or raw source content."""

        self.initialize()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.id, s.filename, s.source_type, s.sha256, s.source_modified_at,
                       s.source_date, s.authority_class, s.confidentiality,
                       v.status AS version_status, v.is_current,
                       COUNT(DISTINCT k.id) AS record_count,
                       COUNT(DISTINCT c.id) AS chunk_count
                FROM source_documents s
                LEFT JOIN knowledge_versions v ON v.source_document_id = s.id
                LEFT JOIN knowledge_records k ON k.source_document_id = s.id
                LEFT JOIN indexed_chunks c ON c.source_document_id = s.id
                GROUP BY s.id
                ORDER BY s.authority_class, s.filename
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def register_managed_source(
        self,
        *,
        source_id: str,
        filename: str,
        relative_path: str,
        source_type: str,
        sha256: str,
        source_modified_at: str,
        source_date: str,
    ) -> None:
        """Register a validated source as review evidence, never as automatic current truth."""

        self.initialize()
        with self.connect() as connection, connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO source_documents(
                    id, filename, relative_path, source_type, sha256,
                    source_modified_at, source_date, authority_class, confidentiality
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'C', 'internal')
                """,
                (
                    source_id,
                    filename,
                    relative_path,
                    source_type,
                    sha256,
                    source_modified_at,
                    source_date,
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO knowledge_versions(
                    source_document_id, version_date, authority_class, status, is_current
                ) VALUES (?, ?, 'C', 'reviewable_external_source', 1)
                """,
                (source_id, source_date),
            )

    def insert_staged_source(self, item: dict[str, Any]) -> None:
        self.initialize()
        with self.connect() as connection, connection:
            connection.execute(
                """
                INSERT INTO staged_sources(
                    id, source_document_id, original_filename, stored_path, source_type,
                    sha256, size_bytes, status, findings_json, preview_json,
                    fact_updates_json, created_by, created_at, proposed_at
                ) VALUES (
                    :id, :source_document_id, :original_filename, :stored_path, :source_type,
                    :sha256, :size_bytes, :status, :findings_json, :preview_json,
                    :fact_updates_json, :created_by, :created_at, :proposed_at
                )
                """,
                item,
            )

    def list_staged_sources(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM staged_sources ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._staged_source_row(row) for row in rows]

    def get_staged_source(self, source_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM staged_sources WHERE id = ?", (source_id,)
            ).fetchone()
        return self._staged_source_row(row) if row else None

    @staticmethod
    def _staged_source_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["findings"] = json.loads(item.pop("findings_json"))
        item["preview"] = json.loads(item.pop("preview_json"))
        item["fact_updates"] = json.loads(item.pop("fact_updates_json"))
        item.pop("stored_path", None)
        return item

    def mark_staged_source_proposed(self, source_id: str, *, proposed_at: str) -> None:
        self.initialize()
        with self.connect() as connection, connection:
            connection.execute(
                """
                UPDATE staged_sources
                SET status = 'review_items_created', proposed_at = ?
                WHERE id = ? AND status = 'validated'
                """,
                (proposed_at, source_id),
            )

    def product_fact_history(
        self, product_id: str, *, field_name: str | None = None
    ) -> list[dict[str, Any]]:
        self.initialize()
        query = """
            SELECT f.*, s.filename AS source_file
            FROM current_product_facts f
            JOIN source_documents s ON s.id = f.source_document_id
            WHERE f.canonical_product_id = ?
        """
        values: list[Any] = [product_id]
        if field_name:
            query += " AND f.field_name = ?"
            values.append(field_name)
        query += " ORDER BY f.field_name, f.approved_at DESC"
        with self.connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._fact_row(row) for row in rows]

    def reject_fact_change(
        self, change_id: str, *, reviewer_id: str, reason: str, occurred_at: str
    ) -> dict[str, Any]:
        return self._simple_change_transition(
            change_id,
            expected_status="pending",
            new_status="rejected",
            reviewer_id=reviewer_id,
            reason=reason,
            occurred_at=occurred_at,
        )

    def _simple_change_transition(
        self,
        change_id: str,
        *,
        expected_status: str,
        new_status: str,
        reviewer_id: str,
        reason: str,
        occurred_at: str,
    ) -> dict[str, Any]:
        self.initialize()
        with self.connect() as connection, connection:
            row = connection.execute(
                "SELECT * FROM product_fact_changes WHERE id = ?", (change_id,)
            ).fetchone()
            if row is None:
                raise KeyError(change_id)
            if row["status"] != expected_status:
                raise ValueError(
                    f"Change {change_id} is {row['status']}; expected {expected_status}"
                )
            connection.execute(
                """
                UPDATE product_fact_changes
                SET status = ?, decided_at = ?, reviewer_id = ?, reason = ?
                WHERE id = ?
                """,
                (new_status, occurred_at, reviewer_id, reason, change_id),
            )
            self._insert_change_event(
                connection,
                change_id=change_id,
                from_status=expected_status,
                to_status=new_status,
                actor=reviewer_id,
                reason=reason,
                occurred_at=occurred_at,
            )
        return self.get_fact_change(change_id) or {}

    @staticmethod
    def _insert_change_event(
        connection: sqlite3.Connection,
        *,
        change_id: str,
        from_status: str | None,
        to_status: str,
        actor: str,
        reason: str,
        occurred_at: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO product_fact_change_events(
                change_id, from_status, to_status, actor, reason, occurred_at, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                change_id,
                from_status,
                to_status,
                actor,
                reason,
                occurred_at,
                json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
            ),
        )

    def approve_fact_change(
        self, change_id: str, *, reviewer_id: str, reason: str, occurred_at: str
    ) -> dict[str, Any]:
        self.initialize()
        with self.connect() as connection, connection:
            change = connection.execute(
                "SELECT * FROM product_fact_changes WHERE id = ?", (change_id,)
            ).fetchone()
            if change is None:
                raise KeyError(change_id)
            if change["status"] != "pending":
                raise ValueError(f"Change {change_id} is {change['status']}; expected pending")
            source = connection.execute(
                """
                SELECT s.*, v.status AS version_status, v.is_current
                FROM source_documents s
                JOIN knowledge_versions v ON v.source_document_id = s.id
                WHERE s.id = ?
                """,
                (change["source_document_id"],),
            ).fetchone()
            if source is None:
                raise ValueError("The proposed fact source is not an indexed governed source")
            if not source["is_current"] or "historical" in source["version_status"]:
                raise ValueError("Historical evidence cannot become a current product fact")
            if source["sha256"] != change["source_version"]:
                raise ValueError("The proposed source version is stale; submit a new review item")

            previous = connection.execute(
                """
                SELECT * FROM current_product_facts
                WHERE canonical_product_id = ? AND field_name = ? AND status = 'approved'
                ORDER BY approved_at DESC
                """,
                (change["canonical_product_id"], change["field_name"]),
            ).fetchall()
            for fact in previous:
                connection.execute(
                    "UPDATE current_product_facts SET status = 'superseded' WHERE id = ?",
                    (fact["id"],),
                )
                prior_change_id = fact["change_id"]
                if prior_change_id:
                    connection.execute(
                        """
                        UPDATE product_fact_changes
                        SET status = 'superseded', decided_at = ?, reviewer_id = ?, reason = ?
                        WHERE id = ? AND status = 'approved'
                        """,
                        (occurred_at, reviewer_id, reason, prior_change_id),
                    )
                    if connection.execute("SELECT changes()").fetchone()[0]:
                        self._insert_change_event(
                            connection,
                            change_id=prior_change_id,
                            from_status="approved",
                            to_status="superseded",
                            actor=reviewer_id,
                            reason=f"Superseded by approved change {change_id}: {reason}",
                            occurred_at=occurred_at,
                        )

            value = json.loads(change["proposed_value_json"])
            fact_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"foreign-trade-rag:approved-change:{change_id}")
            )
            connection.execute(
                """
                INSERT INTO current_product_facts(
                    id, canonical_product_id, field_name, value_json,
                    source_document_id, source_row, source_date, authority_class,
                    confidence, status, source_version, approved_at, reviewer_id,
                    reason, change_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'human_approved', 'approved', ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    change["canonical_product_id"],
                    change["field_name"],
                    change["proposed_value_json"],
                    change["source_document_id"],
                    change["source_row"],
                    source["source_date"] or occurred_at[:10],
                    source["authority_class"],
                    change["source_version"],
                    occurred_at,
                    reviewer_id,
                    reason,
                    change_id,
                ),
            )
            self._update_product_projection(
                connection,
                product_id=change["canonical_product_id"],
                field_name=change["field_name"],
                value=value,
            )
            connection.execute(
                """
                UPDATE product_fact_changes
                SET status = 'approved', decided_at = ?, reviewer_id = ?, reason = ?
                WHERE id = ?
                """,
                (occurred_at, reviewer_id, reason, change_id),
            )
            self._insert_change_event(
                connection,
                change_id=change_id,
                from_status="pending",
                to_status="approved",
                actor=reviewer_id,
                reason=reason,
                occurred_at=occurred_at,
                details={"fact_id": fact_id},
            )
            self._rebuild_approved_fact_chunks(connection)
        return self.get_fact_change(change_id) or {}

    @staticmethod
    def _update_product_projection(
        connection: sqlite3.Connection,
        *,
        product_id: str,
        field_name: str,
        value: Any,
    ) -> None:
        core_columns = {
            "model": ("model", "model"),
            "name": ("title", "name"),
            "category": ("product_group", "category"),
        }
        product_columns = {
            "product_type": "product_type",
            "product_tier": "product_tier",
            "platform_reference_price_min_usd": "price_min_usd",
            "platform_reference_price_max_usd": "price_max_usd",
            "unit": "unit",
            "last_updated": "last_updated",
            "quality_score": "quality_score",
            "review_status": "review_status",
            "listing_status": "listing_status",
            "country_controlled": "country_controlled",
            "optimized": "optimized",
            "showcase": "showcase",
            "monthly_exposure": "monthly_exposure",
        }
        if field_name in core_columns:
            product_column, master_column = core_columns[field_name]
            connection.execute(
                f"UPDATE products SET {product_column} = ? WHERE product_id = ?",
                (value, product_id),
            )
            connection.execute(
                f"UPDATE product_master SET {master_column} = ? WHERE canonical_product_id = ?",
                (value, product_id),
            )
            return

        master = connection.execute(
            "SELECT * FROM product_master WHERE canonical_product_id = ?", (product_id,)
        ).fetchone()
        if master is None:
            raise ValueError(f"Unknown product ID: {product_id}")
        supported = json.loads(master["supported_attributes_json"])
        unsupported = json.loads(master["unsupported_fields_json"])
        supported[field_name] = value
        unsupported = [item for item in unsupported if item != field_name]
        connection.execute(
            """
            UPDATE product_master
            SET supported_attributes_json = ?, unsupported_fields_json = ?,
                confidence = 'human_approved', status = 'approved'
            WHERE canonical_product_id = ?
            """,
            (
                json.dumps(supported, ensure_ascii=False, sort_keys=True),
                json.dumps(unsupported, ensure_ascii=False),
                product_id,
            ),
        )
        if field_name in product_columns:
            connection.execute(
                f"UPDATE products SET {product_columns[field_name]} = ? WHERE product_id = ?",
                (int(value) if isinstance(value, bool) else value, product_id),
            )

    def supersede_fact_change(
        self, change_id: str, *, reviewer_id: str, reason: str, occurred_at: str
    ) -> dict[str, Any]:
        self.initialize()
        protected = {
            "canonical_product_id",
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
        with self.connect() as connection, connection:
            change = connection.execute(
                "SELECT * FROM product_fact_changes WHERE id = ?", (change_id,)
            ).fetchone()
            if change is None:
                raise KeyError(change_id)
            if change["status"] != "approved":
                raise ValueError(f"Change {change_id} is {change['status']}; expected approved")
            if change["field_name"] in protected:
                raise ValueError(
                    "Core product fields must be superseded by approving a replacement change"
                )
            connection.execute(
                "UPDATE current_product_facts SET status = 'superseded' WHERE change_id = ?",
                (change_id,),
            )
            connection.execute(
                """
                UPDATE product_fact_changes
                SET status = 'superseded', decided_at = ?, reviewer_id = ?, reason = ?
                WHERE id = ?
                """,
                (occurred_at, reviewer_id, reason, change_id),
            )
            master = connection.execute(
                "SELECT * FROM product_master WHERE canonical_product_id = ?",
                (change["canonical_product_id"],),
            ).fetchone()
            supported = json.loads(master["supported_attributes_json"])
            unsupported = json.loads(master["unsupported_fields_json"])
            supported.pop(change["field_name"], None)
            if change["field_name"] not in unsupported:
                unsupported.append(change["field_name"])
            connection.execute(
                """
                UPDATE product_master
                SET supported_attributes_json = ?, unsupported_fields_json = ?
                WHERE canonical_product_id = ?
                """,
                (
                    json.dumps(supported, ensure_ascii=False, sort_keys=True),
                    json.dumps(sorted(unsupported), ensure_ascii=False),
                    change["canonical_product_id"],
                ),
            )
            self._insert_change_event(
                connection,
                change_id=change_id,
                from_status="approved",
                to_status="superseded",
                actor=reviewer_id,
                reason=reason,
                occurred_at=occurred_at,
            )
            self._rebuild_approved_fact_chunks(connection)
        return self.get_fact_change(change_id) or {}

    def get_conflicts(self, entity_keys: Iterable[str]) -> list[dict[str, Any]]:
        keys = list(dict.fromkeys(entity_keys))
        if not keys:
            return []
        placeholders = ",".join("?" for _ in keys)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM knowledge_conflicts
                WHERE entity_key IN ({placeholders})
                ORDER BY status, entity_type, entity_key, field_name
                """,
                keys,
            ).fetchall()
            source_rows = connection.execute("SELECT id, filename FROM source_documents").fetchall()
        filenames = {row["id"]: row["filename"] for row in source_rows}
        results = [dict(row) for row in rows]
        for item in results:
            item["values"] = json.loads(item.pop("values_json"))
            item["source_document_ids"] = json.loads(item.pop("source_document_ids_json"))
            item["source_files"] = [
                filenames[source_id]
                for source_id in item["source_document_ids"]
                if source_id in filenames
            ]
            item["evidence_chunk_ids"] = json.loads(item.pop("evidence_chunk_ids_json"))
        return results
