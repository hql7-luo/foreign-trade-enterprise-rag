"""Persistent, single-worker background orchestration for governed ingestion."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from app.database import KnowledgeDatabase
from app.ingestion.pipeline import IngestionCancelled
from app.knowledge_admin import KnowledgeAdminService
from app.observability import count, event


class IngestionJobService:
    """Run one ingestion at a time while keeping status durable in SQLite."""

    def __init__(
        self,
        database: KnowledgeDatabase,
        admin_service: KnowledgeAdminService,
        *,
        recover_interrupted: bool = True,
    ) -> None:
        self.database = database
        self.admin_service = admin_service
        self._create_lock = threading.Lock()
        if recover_interrupted:
            self.database.recover_interrupted_ingestion_jobs(recovered_at=self._now())

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def create(self, *, actor: str) -> dict[str, Any]:
        with self._create_lock:
            return self.database.create_ingestion_job(
                job_id=str(uuid.uuid4()),
                actor=actor,
                created_at=self._now(),
            )

    def run(self, job_id: str) -> None:
        if not self.database.start_ingestion_job(job_id, started_at=self._now()):
            return
        event("ingestion_started", job_id=job_id)
        try:
            result = self.admin_service.ingest_configured_source(
                progress_callback=lambda progress, phase: self.database.update_ingestion_job(
                    job_id, progress=progress, phase=phase
                ),
                cancellation_requested=lambda: self.database.ingestion_job_cancel_requested(job_id),
            )
        except IngestionCancelled:
            event("ingestion_cancelled", job_id=job_id)
            self.database.mark_ingestion_job_cancelled(job_id, completed_at=self._now())
            return
        except Exception as exc:  # Background boundary: persist a safe public failure.
            event("ingestion_failed", job_id=job_id, error_type=type(exc).__name__)
            count("ingestion_failed_total")
            self.database.fail_ingestion_job(
                job_id,
                error=self._public_error(exc),
                completed_at=self._now(),
            )
            return
        self.database.complete_ingestion_job(
            job_id,
            result=result,
            completed_at=self._now(),
        )
        count("ingestion_completed_total")
        event("ingestion_completed", job_id=job_id)

    def list(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.database.list_ingestion_jobs(limit=limit)

    def get(self, job_id: str) -> dict[str, Any]:
        item = self.database.get_ingestion_job(job_id)
        if item is None:
            raise KeyError(job_id)
        return item

    def cancel(self, job_id: str) -> dict[str, Any]:
        return self.database.request_ingestion_job_cancel(
            job_id,
            completed_at=self._now(),
        )

    @staticmethod
    def _public_error(error: Exception) -> str:
        message = str(error).casefold()
        if isinstance(error, ConnectionError) or "qdrant" in message or "connection" in message:
            return "Qdrant is unavailable. Verify the vector service and retry."
        if "embedding" in message or "model" in message or "fastembed" in message:
            return "The embedding model is unavailable. Verify model configuration and retry."
        if "database" in message or "sqlite" in message or "readonly" in message:
            return "The knowledge database is unavailable or not writable."
        if isinstance(error, ValueError):
            return "Source validation failed. Verify the approved demo source configuration."
        return "Ingestion failed. Review the private backend logs and retry."
