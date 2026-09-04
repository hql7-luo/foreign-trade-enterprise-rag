from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.database import KnowledgeDatabase
from app.domain import ProductMatch, ProductRecord, RetrievalHit
from app.retrieval.bm25 import BM25Encoder
from app.retrieval.diversity import diversify_product_hits, is_open_product_discovery
from app.retrieval.embedding import EmbeddingProvider
from app.retrieval.qdrant_store import QdrantVectorStore, VectorSearchResult
from app.text import meaningful_terms, normalize_text, tokenize


@dataclass(frozen=True)
class RetrievalResult:
    structured_matches: list[ProductMatch]
    hits: list[RetrievalHit]
    conflicts: list[dict[str, Any]]
    selection_debug: dict[str, object]


class CrossEncoder(Protocol):
    model_name: str
    implementation: str

    def score(self, query: str, documents: list[str]) -> list[float]: ...


class RetrievalService:
    def __init__(
        self,
        database: KnowledgeDatabase,
        vector_store: QdrantVectorStore,
        embedder: EmbeddingProvider,
        *,
        cross_encoder: CrossEncoder | None = None,
        reranker_mode: str = "heuristic",
        reranker_candidate_limit: int = 16,
        expected_chunking_strategy: str = "legacy",
        diversity_selection_enabled: bool = False,
    ) -> None:
        if reranker_mode not in {"heuristic", "cross_encoder", "hybrid"}:
            raise ValueError(f"Unsupported reranker mode: {reranker_mode}")
        if reranker_mode != "heuristic" and cross_encoder is None:
            raise ValueError("A cross encoder is required for this reranker mode")
        if expected_chunking_strategy not in {"legacy", "source_aware"}:
            raise ValueError(f"Unsupported chunking strategy: {expected_chunking_strategy}")
        self.database = database
        self.vector_store = vector_store
        self.embedder = embedder
        self.cross_encoder = cross_encoder
        self.reranker_mode = reranker_mode
        self.reranker_candidate_limit = reranker_candidate_limit
        self.expected_chunking_strategy = expected_chunking_strategy
        self.chunking_strategy = expected_chunking_strategy
        self.diversity_selection_enabled = diversity_selection_enabled

    def search(
        self, question: str, *, limit: int = 8, candidate_limit: int = 30
    ) -> RetrievalResult:
        embedding_state = self.database.get_retrieval_state("embedding")
        chunking_state = self.database.get_retrieval_state("chunking")
        self.chunking_strategy = str(chunking_state["strategy"])
        if self.chunking_strategy != self.expected_chunking_strategy:
            raise RuntimeError(
                "Chunking configuration changed after ingestion; rebuild the knowledge index"
            )
        if (
            embedding_state.get("fingerprint") != self.embedder.fingerprint
            or embedding_state.get("collection") != self.vector_store.collection
        ):
            raise RuntimeError(
                "Embedding configuration changed after ingestion; rebuild the knowledge index"
            )
        structured = self.structured_product_search(question, limit=10)
        intent_categories = self._knowledge_category_intent(question)
        dense_vector = self.embedder.embed_query(question)
        dense_results = self.vector_store.search_dense(dense_vector, limit=candidate_limit)
        bm25 = BM25Encoder.from_dict(self.database.get_retrieval_state("bm25"))
        sparse_vector = bm25.encode_query(question)
        sparse_results = self.vector_store.search_sparse(sparse_vector, limit=candidate_limit)
        if intent_categories:
            dense_results = self._merge_vector_results(
                dense_results,
                self.vector_store.search_dense(
                    dense_vector,
                    limit=12,
                    categories=intent_categories,
                ),
            )
            sparse_results = self._merge_vector_results(
                sparse_results,
                self.vector_store.search_sparse(
                    sparse_vector,
                    limit=12,
                    categories=intent_categories,
                ),
            )
        use_diversity = self.diversity_selection_enabled and is_open_product_discovery(
            question,
            structured,
            knowledge_intent=bool(intent_categories),
        )
        hits = self._fuse_and_rerank(
            question,
            dense_results=dense_results,
            sparse_results=sparse_results,
            structured_matches=structured,
            intent_categories=intent_categories,
            limit=max(limit * 3, 24) if use_diversity else limit,
        )
        selection_debug: dict[str, object] = {
            "enabled": self.diversity_selection_enabled,
            "applied": False,
            "selected_product_ids": [],
        }
        if use_diversity:
            hits, selection_debug = diversify_product_hits(
                question,
                hits,
                structured,
                limit=limit,
            )
            selection_debug["enabled"] = True
        entity_keys = {
            value
            for match in structured
            if match.score >= 80
            for value in (match.product.product_id, match.product.model)
        }
        if {"company", "business", "公司"}.intersection(meaningful_terms(question)):
            entity_keys.add("company")
        conflicts = self.database.get_conflicts(entity_keys)
        return RetrievalResult(
            structured_matches=structured,
            hits=hits,
            conflicts=conflicts,
            selection_debug=selection_debug,
        )

    @staticmethod
    def _merge_vector_results(
        primary: list[VectorSearchResult], scoped: list[VectorSearchResult]
    ) -> list[VectorSearchResult]:
        best = {item.chunk_id: item for item in primary}
        for item in scoped:
            if item.chunk_id not in best or item.score > best[item.chunk_id].score:
                best[item.chunk_id] = item
        return sorted(best.values(), key=lambda item: (-item.score, item.chunk_id))

    def structured_product_search(self, question: str, *, limit: int = 10) -> list[ProductMatch]:
        normalized = normalize_text(question)
        query_terms = meaningful_terms(question)
        category = self._category_intent(normalized)
        matches: list[ProductMatch] = []
        for product in self.database.list_products():
            score, reasons = self._score_product(
                product,
                normalized_question=normalized,
                query_terms=query_terms,
                category=category,
            )
            if score > 0:
                matches.append(
                    ProductMatch(product=product, score=score, reason="; ".join(reasons))
                )
        matches.sort(key=lambda match: (-match.score, match.product.product_id))
        return matches[:limit]

    @staticmethod
    def _category_intent(normalized_question: str) -> str | None:
        return None

    def _knowledge_category_intent(self, question: str) -> set[str]:
        normalized = normalize_text(question)
        terms = meaningful_terms(question)
        categories: set[str] = set()
        if "domain_sop" in normalized or terms.intersection(
            {"procedure", "process", "required", "流程", "规范", "必填"}
        ):
            categories.add("operational_knowledge")
        if terms.intersection(
            {
                "company",
                "business",
                "capability",
                "capabilities",
                "公司",
                "业务",
                "主营",
            }
        ):
            categories.update({"company_knowledge", "product_capability"})
        if terms.intersection({"quotation", "quote", "historical", "报价", "询价"}) or (
            "rfq" in terms and terms.intersection({"historical", "history", "历史"})
        ):
            categories.add("quotation_evidence")
        if terms.intersection(
            {
                "analytics",
                "count",
                "counted",
                "share",
                "signal",
                "bucket",
                "demand",
                "rfq",
                "rfqs",
                "统计",
                "占比",
            }
        ):
            categories.add("rfq_market_analytics")
        if terms.intersection(
            {
                "po",
                "workbook",
                "worksheet",
                "template",
                "merged",
                "supplier",
                "header",
                "instruction",
                "制单",
                "工艺",
            }
        ):
            categories.add("operational_knowledge")
        return categories

    @staticmethod
    def _score_product(
        product: ProductRecord,
        *,
        normalized_question: str,
        query_terms: set[str],
        category: str | None,
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []
        if product.product_id.casefold() in normalized_question:
            score += 120.0
            reasons.append("exact product ID")
        if product.model.casefold() in normalized_question:
            score += 100.0
            reasons.append("exact model")
        elif _confusable_identifier_match(product.model.casefold(), normalized_question):
            score += 85.0
            reasons.append("near model (confusable identifier character)")
        elif _single_edit_match(product.model.casefold(), normalized_question):
            score += 70.0
            reasons.append("near model (single-character edit)")

        product_text = normalize_text(f"{product.title} {product.product_group}")
        if category and category in product_text:
            score += 60.0
            reasons.append("category match")

        overlap = query_terms & meaningful_terms(product_text)
        if len(overlap) >= 2:
            score += min(len(overlap) * 4.0, 24.0)
            reasons.append(f"{len(overlap)} title/group terms")
        return score, reasons

    def _fuse_and_rerank(
        self,
        question: str,
        *,
        dense_results: list[VectorSearchResult],
        sparse_results: list[VectorSearchResult],
        structured_matches: list[ProductMatch],
        intent_categories: set[str],
        limit: int,
    ) -> list[RetrievalHit]:
        candidate_ids = {result.chunk_id for result in dense_results + sparse_results}
        structured_chunks = self.database.get_product_chunks(
            match.product.product_id for match in structured_matches
        )
        candidate_ids.update(chunk.id for chunk in structured_chunks)
        intent_chunks = self.database.get_chunks_by_categories(intent_categories)
        candidate_ids.update(chunk.id for chunk in intent_chunks)
        chunks = self.database.get_chunks(candidate_ids)

        dense_by_id = {result.chunk_id: result for result in dense_results}
        sparse_by_id = {result.chunk_id: result for result in sparse_results}
        dense_rank = {result.chunk_id: rank for rank, result in enumerate(dense_results, start=1)}
        sparse_rank = {result.chunk_id: rank for rank, result in enumerate(sparse_results, start=1)}
        structured_scores = {
            chunk.id: match.score / 120.0
            for match in structured_matches
            for chunk in structured_chunks
            if chunk.product_id == match.product.product_id
        }

        hits: list[RetrievalHit] = []
        for chunk_id in candidate_ids:
            chunk = chunks.get(chunk_id)
            if chunk is None:
                continue
            fused = 0.0
            if chunk_id in dense_rank:
                fused += 1.0 / (60 + dense_rank[chunk_id])
            if chunk_id in sparse_rank:
                fused += 1.0 / (60 + sparse_rank[chunk_id])
            hits.append(
                RetrievalHit(
                    chunk=chunk,
                    dense_score=(
                        dense_by_id.get(chunk_id).score if chunk_id in dense_by_id else None
                    ),
                    bm25_score=(
                        sparse_by_id.get(chunk_id).score if chunk_id in sparse_by_id else None
                    ),
                    dense_rank=dense_rank.get(chunk_id),
                    bm25_rank=sparse_rank.get(chunk_id),
                    fused_score=fused,
                    structured_score=structured_scores.get(chunk_id, 0.0),
                )
            )

        hits.sort(key=lambda hit: (-hit.fused_score, hit.chunk.id))
        for rank, hit in enumerate(hits, start=1):
            hit.fused_rank = rank

        question_terms = meaningful_terms(question)
        normalized_question = normalize_text(question)
        authority_boost = {"A": 0.03, "B": 0.02, "C": 0.01, "D": 0.0}
        for hit in hits:
            overlap = question_terms & meaningful_terms(hit.chunk.content)
            canonical_overlap = {term for term in overlap if term.startswith("domain_")}
            overlap_score = min(len(overlap) * 0.025, 0.2) + len(canonical_overlap) * 0.25
            exact_entity_boost = 0.0
            if hit.chunk.product_id and hit.chunk.product_id.casefold() in normalized_question:
                exact_entity_boost += 0.8
            if hit.chunk.model and hit.chunk.model.casefold() in normalized_question:
                exact_entity_boost += 0.6
            intent_boost = 0.2 if hit.chunk.category in intent_categories else 0.0
            semantic_score = max(hit.dense_score or 0.0, 0.0) * 0.65
            historical_boost = (
                0.2
                if hit.chunk.category == "quotation_evidence"
                and question_terms.intersection(
                    {"historical", "history", "previous", "past", "历史", "过往"}
                )
                else 0.0
            )
            field_heading_boost = 0.0
            if (
                "domain_required" in normalized_question
                and hit.chunk.section
                and (
                    "必填字段" in hit.chunk.section
                    or "required field" in hit.chunk.section.casefold()
                )
            ):
                field_heading_boost = 0.35
            governance_boost = 0.0
            if hit.chunk.record_type == "approved_product_fact":
                field_name = str(hit.chunk.metadata.get("field_name", ""))
                governance_boost = 0.35
                field_terms = {
                    "moq": {"domain_moq"},
                    "lead_time": {"domain_lead_time", "eta"},
                    "dimensions": {"dimension", "dimensions", "尺寸"},
                    "packaging": {"packaging", "packing", "包装"},
                    "certificates": {"domain_certificate"},
                    "logistics_or_freight": {"logistics", "freight", "ship", "shipping"},
                }
                if question_terms.intersection(field_terms.get(field_name, {field_name})):
                    governance_boost = 1.0
            metadata_boost = self._governed_metadata_boost(question, hit)
            hit.heuristic_score = (
                hit.fused_score
                + hit.structured_score * 0.8
                + overlap_score
                + exact_entity_boost
                + intent_boost
                + semantic_score
                + historical_boost
                + field_heading_boost
                + governance_boost
                + metadata_boost
                + authority_boost.get(hit.chunk.authority_class, 0.0)
            )
            hit.reranker_score = hit.heuristic_score

        self._apply_optional_cross_encoder(question, hits, intent_categories)

        hits.sort(key=lambda hit: (-hit.reranker_score, hit.chunk.id))
        final = hits[:limit]
        for rank, hit in enumerate(final, start=1):
            hit.final_rank = rank
        return final

    def _governed_metadata_boost(self, question: str, hit: RetrievalHit) -> float:
        metadata = hit.chunk.metadata
        normalized = normalize_text(question)
        terms = meaningful_terms(question)
        boost = 0.0

        if self.chunking_strategy == "source_aware" and metadata.get("chunk_role") == "child":
            overlap = terms.intersection(meaningful_terms(hit.chunk.content))
            boost += min(len(overlap) * 0.04, 0.16)

        scope = str(metadata.get("scope", ""))
        if "latest" in normalized or "最新" in normalized:
            boost += 0.45 if scope.startswith("latest_") else 0.0
        if any(value in normalized for value in {"5-day", "5 day", "dedup", "去重"}):
            boost += 0.55 if scope.startswith("unique_") else 0.0
        if "recurring" in terms:
            boost += 0.45 if scope.startswith("recurring_") else 0.0

        dimension = str(metadata.get("dimension", ""))
        if (
            terms.intersection({"band", "bucket"}) or "quantity" in normalized
        ) and dimension == "quantity_bucket":
            boost += 0.45
        if "signal" in terms and dimension == "notebook_signal":
            boost += 0.45
        if terms.intersection({"category", "packaging"}) and dimension == "product_category":
            boost += 0.25

        item = str(metadata.get("item", ""))
        item_overlap = {
            value
            for value in meaningful_terms(item).intersection(terms)
            if value.startswith("domain_") or len(value) >= 3
        }
        boost += min(len(item_overlap) * 0.35, 0.7)
        return boost

    def _apply_optional_cross_encoder(
        self,
        question: str,
        hits: list[RetrievalHit],
        intent_categories: set[str],
    ) -> None:
        if self.reranker_mode == "heuristic" or self.cross_encoder is None:
            return
        targeted_categories = {
            "rfq_market_analytics",
            "company_knowledge",
            "product_capability",
            "operational_knowledge",
        }
        if self.reranker_mode == "hybrid" and not intent_categories.intersection(
            targeted_categories
        ):
            return
        pool = sorted(hits, key=lambda hit: (-hit.heuristic_score, hit.chunk.id))[
            : self.reranker_candidate_limit
        ]
        scores = self.cross_encoder.score(question, [hit.chunk.content for hit in pool])
        if len(scores) != len(pool):
            raise RuntimeError("Cross encoder returned an unexpected score count")
        for hit, score in zip(pool, scores, strict=True):
            hit.cross_encoder_score = score

        cross_normalized = _minmax(scores)
        heuristic_normalized = _minmax([hit.heuristic_score for hit in hits])
        heuristic_by_id = {
            hit.chunk.id: score for hit, score in zip(hits, heuristic_normalized, strict=True)
        }
        if self.reranker_mode == "cross_encoder":
            for hit, score in zip(pool, cross_normalized, strict=True):
                hit.reranker_score = 2.0 + score
            for hit in hits:
                if hit.cross_encoder_score is None:
                    hit.reranker_score = heuristic_by_id[hit.chunk.id]
            return

        cross_by_id = {
            hit.chunk.id: score for hit, score in zip(pool, cross_normalized, strict=True)
        }
        for hit in hits:
            hit.reranker_score = 0.55 * heuristic_by_id[hit.chunk.id]
            if hit.chunk.id in cross_by_id:
                hit.reranker_score += 0.45 * cross_by_id[hit.chunk.id]


def _single_edit_match(model: str, normalized_question: str) -> bool:
    candidates = [token for token in tokenize(normalized_question) if len(token) == len(model)]
    return any(
        sum(left != right for left, right in zip(model, token, strict=True)) == 1
        for token in candidates
    )


def _confusable_identifier_match(model: str, normalized_question: str) -> bool:
    translation = str.maketrans({"i": "1", "l": "1", "o": "0"})
    for token in tokenize(normalized_question):
        if len(token) == len(model) and token.translate(translation) == model:
            return True
    return False


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if high == low:
        return [0.5 for _ in values]
    return [(value - low) / (high - low) for value in values]
