from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient, models

from app.domain import Chunk
from app.retrieval.bm25 import SparseVectorData


@dataclass(frozen=True)
class VectorPoint:
    chunk: Chunk
    dense_vector: list[float]
    sparse_vector: SparseVectorData


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_id: str
    score: float


class QdrantVectorStore:
    def __init__(
        self,
        *,
        collection: str,
        dimension: int,
        path: str | None = None,
        url: str | None = None,
        client: QdrantClient | None = None,
        api_key: str | None = None,
    ) -> None:
        self.collection = collection
        self.dimension = dimension
        if client is not None:
            self.client = client
        elif url:
            self.client = QdrantClient(url=url, api_key=api_key, timeout=5)
        else:
            storage_path = Path(path or "data/private/qdrant")
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(storage_path))

    def rebuild(self, points: list[VectorPoint]) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config={
                "dense": models.VectorParams(
                    size=self.dimension,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                "bm25": models.SparseVectorParams(index=models.SparseIndexParams(on_disk=False))
            },
        )
        batch_size = 64
        for start in range(0, len(points), batch_size):
            batch = points[start : start + batch_size]
            self.client.upsert(
                collection_name=self.collection,
                wait=True,
                points=[
                    models.PointStruct(
                        id=point.chunk.id,
                        vector={
                            "dense": point.dense_vector,
                            "bm25": models.SparseVector(
                                indices=point.sparse_vector.indices,
                                values=point.sparse_vector.values,
                            ),
                        },
                        payload={
                            "source_file": point.chunk.source_file,
                            "source_type": point.chunk.source_type,
                            "category": point.chunk.category,
                            "authority_class": point.chunk.authority_class,
                            "confidentiality": point.chunk.confidentiality,
                            "product_id": point.chunk.product_id,
                            "model": point.chunk.model,
                            "section": point.chunk.section,
                            "row_start": point.chunk.row_start,
                        },
                    )
                    for point in batch
                ],
            )

    @staticmethod
    def _category_filter(categories: set[str] | None):
        if not categories:
            return None
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="category",
                    match=models.MatchAny(any=sorted(categories)),
                )
            ]
        )

    def search_dense(
        self,
        vector: list[float],
        *,
        limit: int,
        categories: set[str] | None = None,
    ) -> list[VectorSearchResult]:
        response = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            using="dense",
            query_filter=self._category_filter(categories),
            limit=limit,
            with_payload=False,
        )
        return [
            VectorSearchResult(chunk_id=str(point.id), score=float(point.score))
            for point in response.points
        ]

    def search_sparse(
        self,
        vector: SparseVectorData,
        *,
        limit: int,
        categories: set[str] | None = None,
    ) -> list[VectorSearchResult]:
        if not vector.indices:
            return []
        response = self.client.query_points(
            collection_name=self.collection,
            query=models.SparseVector(indices=vector.indices, values=vector.values),
            using="bm25",
            query_filter=self._category_filter(categories),
            limit=limit,
            with_payload=False,
        )
        return [
            VectorSearchResult(chunk_id=str(point.id), score=float(point.score))
            for point in response.points
        ]

    def count(self) -> int:
        result = self.client.count(collection_name=self.collection, exact=True)
        return int(result.count)

    def close(self) -> None:
        self.client.close()
