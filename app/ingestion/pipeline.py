from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.approval import reconcile_approved_facts
from app.database import KnowledgeDatabase
from app.governance import build_governance
from app.ingestion.loaders import (
    APPROVED_SOURCES,
    CHUNKING_STRATEGIES,
    file_sha256,
    load_approved_sources,
)
from app.retrieval.bm25 import BM25Encoder
from app.retrieval.embedding import EmbeddingProvider
from app.retrieval.qdrant_store import QdrantVectorStore, VectorPoint


@dataclass(frozen=True)
class IngestionResult:
    run_id: str
    source_documents: int
    products: int
    knowledge_records: int
    chunks: int
    qdrant_points: int
    source_hashes_unchanged: bool


class IngestionCancelled(RuntimeError):
    """Raised only at a safe checkpoint before the index rebuild begins."""


class IngestionPipeline:
    def __init__(
        self,
        database: KnowledgeDatabase,
        vector_store: QdrantVectorStore,
        embedder: EmbeddingProvider,
        *,
        chunking_strategy: str = "legacy",
    ) -> None:
        if chunking_strategy not in CHUNKING_STRATEGIES:
            raise ValueError(f"Unsupported chunking strategy: {chunking_strategy}")
        self.database = database
        self.vector_store = vector_store
        self.embedder = embedder
        self.chunking_strategy = chunking_strategy

    def run(
        self,
        source_root: Path,
        *,
        progress_callback: Callable[[int, str], None] | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> IngestionResult:
        def checkpoint(progress: int, phase: str) -> None:
            if progress_callback:
                progress_callback(progress, phase)
            if cancellation_requested and cancellation_requested():
                raise IngestionCancelled("Ingestion cancelled before index rebuild")

        source_root = source_root.resolve()
        run_id = str(uuid.uuid4())
        root_hash = hashlib.sha256(str(source_root).encode("utf-8")).hexdigest()
        self.database.begin_ingestion_run(run_id, root_hash)
        try:
            checkpoint(8, "loading_sources")
            bundle = load_approved_sources(
                source_root,
                chunking_strategy=self.chunking_strategy,
            )
            candidate_governance = build_governance(bundle)
            checkpoint(25, "validating_governance")
            approved_snapshot = self.database.list_current_product_facts()
            bundle, governance = reconcile_approved_facts(
                bundle,
                candidate_governance,
                approved_snapshot,
            )
            self._verify_source_hashes(source_root, bundle.source_hashes)
            checkpoint(35, "preparing_retrieval")
            bm25 = BM25Encoder.fit([chunk.content for chunk in bundle.chunks])
            checkpoint(45, "embedding_chunks")
            dense_vectors = self.embedder.embed_documents(
                [chunk.content for chunk in bundle.chunks]
            )
            points = [
                VectorPoint(
                    chunk=chunk,
                    dense_vector=dense_vector,
                    sparse_vector=bm25.encode_document(chunk.content),
                )
                for chunk, dense_vector in zip(bundle.chunks, dense_vectors, strict=True)
            ]
            checkpoint(65, "ready_to_rebuild")
            if progress_callback:
                progress_callback(70, "rebuilding_vector_index")
            self.vector_store.rebuild(points)
            if progress_callback:
                progress_callback(85, "writing_governed_metadata")
            self.database.rebuild(
                bundle,
                governance=governance,
                run_id=run_id,
                retrieval_state={
                    "bm25": bm25.to_dict(),
                    "embedding": {
                        "provider": self.embedder.provider_name,
                        "model": self.embedder.model_name,
                        "implementation_version": self.embedder.implementation_version,
                        "dimension": self.embedder.dimension,
                        "fingerprint": self.embedder.fingerprint,
                        "collection": self.vector_store.collection,
                    },
                    "approved_sources": list(APPROVED_SOURCES),
                    "chunking": {
                        "strategy": self.chunking_strategy,
                        "version": (
                            "source-aware-v1"
                            if self.chunking_strategy == "source_aware"
                            else "legacy-v1"
                        ),
                    },
                },
            )
            self._verify_source_hashes(source_root, bundle.source_hashes)
            if progress_callback:
                progress_callback(98, "verifying_index")
        except Exception as error:
            self.database.fail_ingestion_run(run_id, str(error))
            raise
        return IngestionResult(
            run_id=run_id,
            source_documents=len(bundle.sources),
            products=len(bundle.products),
            knowledge_records=len(bundle.knowledge_records),
            chunks=len(bundle.chunks),
            qdrant_points=self.vector_store.count(),
            source_hashes_unchanged=True,
        )

    @staticmethod
    def _verify_source_hashes(source_root: Path, expected: dict[str, str]) -> None:
        actual = {
            relative_path: file_sha256(source_root / relative_path) for relative_path in expected
        }
        if actual != expected:
            raise RuntimeError("Approved source files changed during ingestion")
