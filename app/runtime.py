"""Composition root shared by the API and command-line tools."""

from __future__ import annotations

from app.config import Settings
from app.database import KnowledgeDatabase
from app.rag.answerer import OpenAICompatibleAnswerer
from app.rag.service import RagService
from app.retrieval.embedding import build_embedding_provider, physical_collection_name
from app.retrieval.qdrant_store import QdrantVectorStore
from app.retrieval.reranker import FastEmbedCrossEncoder
from app.retrieval.service import RetrievalService


def build_rag_service(settings: Settings) -> RagService:
    database = KnowledgeDatabase(settings.database_path)
    database.initialize()
    embedder = build_embedding_provider(
        provider=settings.embedding_provider,
        model_name=settings.embedding_model,
        dimension=settings.embedding_dim,
        cache_dir=settings.embedding_cache_path,
        allow_hash_fallback=settings.embedding_allow_hash_fallback,
    )
    vector_store = QdrantVectorStore(
        collection=physical_collection_name(settings.qdrant_collection, embedder),
        dimension=embedder.dimension,
        path=settings.qdrant_path,
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
    )
    llm_answerer = None
    if settings.llm_api_key and settings.llm_model:
        llm_answerer = OpenAICompatibleAnswerer(
            settings.llm_base_url,
            settings.llm_api_key,
            settings.llm_model,
        )
    cross_encoder = None
    if settings.reranker_mode in {"cross_encoder", "hybrid"}:
        cross_encoder = FastEmbedCrossEncoder(
            settings.reranker_model,
            settings.reranker_cache_path,
        )
    retrieval = RetrievalService(
        database,
        vector_store,
        embedder,
        cross_encoder=cross_encoder,
        reranker_mode=settings.reranker_mode,
        reranker_candidate_limit=settings.reranker_candidate_limit,
        expected_chunking_strategy=settings.chunking_strategy,
        diversity_selection_enabled=settings.diversity_selection_enabled,
    )
    return RagService(
        retrieval,
        llm_answerer=llm_answerer,
        answer_mode=settings.answer_mode,
        parent_context_enabled=settings.parent_context_enabled,
        diversity_selection_enabled=settings.diversity_selection_enabled,
        sibling_evidence_enabled=settings.sibling_evidence_enabled,
        sibling_max_chunks=settings.sibling_max_chunks,
    )
