from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.config import Settings
from app.database import KnowledgeDatabase
from app.ingestion.loaders import CHUNKING_STRATEGIES
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.embedding import build_embedding_provider, physical_collection_name
from app.retrieval.qdrant_store import QdrantVectorStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest approved Northstar demo knowledge")
    parser.add_argument("--source", type=Path, required=True, help="Read-only source directory")
    parser.add_argument("--database", type=Path, help="Override SQLite database path")
    parser.add_argument("--qdrant-path", help="Override local Qdrant storage path")
    parser.add_argument("--qdrant-url", help="Use a running Qdrant server instead of local mode")
    parser.add_argument("--embedding-provider", choices=("fastembed", "domain_hash"))
    parser.add_argument("--embedding-model")
    parser.add_argument("--no-embedding-fallback", action="store_true")
    parser.add_argument(
        "--chunking-strategy",
        choices=tuple(sorted(CHUNKING_STRATEGIES)),
        help="Override governed Markdown chunking strategy",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings()
    database = KnowledgeDatabase(args.database or settings.database_path)
    embedder = build_embedding_provider(
        provider=args.embedding_provider or settings.embedding_provider,
        model_name=args.embedding_model or settings.embedding_model,
        dimension=settings.embedding_dim,
        cache_dir=settings.embedding_cache_path,
        allow_hash_fallback=(
            settings.embedding_allow_hash_fallback and not args.no_embedding_fallback
        ),
    )
    vector_store = QdrantVectorStore(
        collection=physical_collection_name(settings.qdrant_collection, embedder),
        dimension=embedder.dimension,
        path=args.qdrant_path or settings.qdrant_path,
        url=args.qdrant_url or settings.qdrant_url,
    )
    try:
        result = IngestionPipeline(
            database,
            vector_store,
            embedder,
            chunking_strategy=args.chunking_strategy or settings.chunking_strategy,
        ).run(args.source)
    finally:
        vector_store.close()
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
