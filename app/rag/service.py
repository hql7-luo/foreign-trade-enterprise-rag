"""Application service coordinating retrieval and grounded answer generation."""

from __future__ import annotations

from time import perf_counter

import httpx

from app.domain import Chunk
from app.observability import count, event, timing
from app.rag.answerer import (
    ConservativeAnswerer,
    OpenAICompatibleAnswerer,
    build_context,
    citation_from_hit,
)
from app.rag.claim_answerer import ClaimLevelAnswerer
from app.rag.evidence_assembly import assemble_complementary_siblings
from app.rag.models import AnswerClaim, AnswerResult, GroundedClaim
from app.retrieval.service import RetrievalService
from app.text import meaningful_terms


class RagService:
    """Retrieve, answer, and retain full traceability for one question."""

    def __init__(
        self,
        retrieval: RetrievalService,
        *,
        llm_answerer: OpenAICompatibleAnswerer | None = None,
        answer_mode: str = "legacy",
        parent_context_enabled: bool = False,
        diversity_selection_enabled: bool = False,
        sibling_evidence_enabled: bool = False,
        sibling_max_chunks: int = 3,
    ) -> None:
        if answer_mode not in {"legacy", "claim_level"}:
            raise ValueError(f"Unsupported answer mode: {answer_mode}")
        self.retrieval = retrieval
        self.conservative_answerer = ConservativeAnswerer()
        self.answerer = (
            ClaimLevelAnswerer(
                self.conservative_answerer,
                diversity_selection_enabled=diversity_selection_enabled,
                concept_completion_enabled=sibling_evidence_enabled,
            )
            if answer_mode == "claim_level"
            else self.conservative_answerer
        )
        self.llm_answerer = llm_answerer
        self.answer_mode = answer_mode
        self.parent_context_enabled = parent_context_enabled
        self.diversity_selection_enabled = diversity_selection_enabled
        self.sibling_evidence_enabled = sibling_evidence_enabled
        self.sibling_max_chunks = sibling_max_chunks

    def query(self, question: str, *, debug: bool = False, limit: int = 8) -> AnswerResult:
        started = perf_counter()
        retrieval_result = self.retrieval.search(question, limit=limit)
        retrieved_at = perf_counter()
        timing("retrieval", retrieved_at - started)
        answer_hits = retrieval_result.hits
        sibling_debug: dict[str, object] = {
            "enabled": self.sibling_evidence_enabled,
            "added_count": 0,
            "unresolved_concepts": [],
            "added": [],
        }
        if self.sibling_evidence_enabled:
            answer_hits, sibling_debug = assemble_complementary_siblings(
                question,
                retrieval_result.hits,
                self.retrieval.database,
                max_siblings=self.sibling_max_chunks,
            )
        extractive = self.answerer.answer(
            question,
            retrieval_result.structured_matches,
            answer_hits,
            retrieval_result.conflicts,
        )
        self._append_conflict_notices(
            question,
            extractive,
            answer_hits,
            retrieval_result.conflicts,
        )

        context_hits = extractive.used_hits or retrieval_result.hits[:6]
        parent_chunks = self._parent_chunks(context_hits)
        context = build_context(question, context_hits, parent_chunks=parent_chunks)
        answer_text = extractive.text
        provider = "conservative_extractive"
        llm_fallback_reason: str | None = None

        if self.llm_answerer and extractive.sufficient and extractive.used_hits:
            try:
                llm_text = self.llm_answerer.answer(
                    question,
                    context,
                    citation_count=len(extractive.used_hits),
                )
                if llm_text:
                    answer_text = llm_text
                    provider = "openai_compatible"
                else:
                    llm_fallback_reason = "provider output did not contain valid citations"
            except (httpx.HTTPError, KeyError, TypeError, ValueError, OSError) as exc:
                llm_fallback_reason = f"provider failure: {type(exc).__name__}"

        sources = [
            citation_from_hit(hit, index) for index, hit in enumerate(extractive.used_hits, start=1)
        ]
        citation_by_chunk = {source.chunk_id: source for source in sources}
        claims = [
            AnswerClaim(
                text=claim.text,
                supported=claim.supported,
                sources=[
                    citation_by_chunk[hit.chunk.id]
                    for hit in claim.evidence_hits
                    if hit.chunk.id in citation_by_chunk
                ],
                claim_type=claim.claim_type,
                support_state=claim.support_state,
            )
            for claim in extractive.claims
        ]
        debug_payload = None
        if debug:
            debug_payload = {
                "answer_provider": provider,
                "answer_mode": self.answer_mode,
                "diversity_selection": retrieval_result.selection_debug,
                "sibling_evidence_assembly": sibling_debug,
                "llm_fallback_reason": llm_fallback_reason,
                "structured_matches": [
                    {
                        "product_id": match.product.product_id,
                        "model": match.product.model,
                        "match_reason": match.reason,
                        "match_score": match.score,
                    }
                    for match in retrieval_result.structured_matches
                ],
                "ranking": [
                    {
                        "chunk_id": hit.chunk.id,
                        "dense_score": hit.dense_score,
                        "bm25_score": hit.bm25_score,
                        "rrf_score": hit.fused_score,
                        "structured_boost": hit.structured_score,
                        "heuristic_score": hit.heuristic_score,
                        "cross_encoder_score": hit.cross_encoder_score,
                        "reranker_score": hit.reranker_score,
                        "dense_rank": hit.dense_rank,
                        "bm25_rank": hit.bm25_rank,
                    }
                    for hit in retrieval_result.hits
                ],
                "reranker": {
                    "mode": self.retrieval.reranker_mode,
                    "model": (
                        self.retrieval.cross_encoder.model_name
                        if self.retrieval.cross_encoder is not None
                        else None
                    ),
                    "candidate_limit": self.retrieval.reranker_candidate_limit,
                },
                "context_sent_to_answerer": context,
                "answer_context_chars": len(context),
                "answer_context_chunks": len(context_hits) + len(parent_chunks),
                "claim_plan": [
                    {
                        "claim_type": claim.claim_type,
                        "supported": claim.supported,
                        "support_state": claim.support_state,
                        "source_chunk_ids": [source.chunk_id for source in claim.sources],
                    }
                    for claim in claims
                ],
                "context_transmitted_to_external_llm": provider == "openai_compatible",
                "knowledge_conflicts": retrieval_result.conflicts,
            }

        timing("answer_generation", perf_counter() - retrieved_at)
        timing("query", perf_counter() - started)
        count("queries_total")
        event("query_completed", duration_ms=round((perf_counter() - started) * 1000, 2))
        return AnswerResult(
            answer=answer_text,
            sufficient_information=extractive.sufficient,
            sources=sources,
            retrieved_context=retrieval_result.hits,
            structured_matches=retrieval_result.structured_matches,
            claims=claims,
            answer_context_chars=len(context),
            answer_context_chunks=len(context_hits) + len(parent_chunks),
            conflicts=retrieval_result.conflicts,
            debug=debug_payload,
        )

    def _parent_chunks(self, hits) -> dict[str, Chunk]:
        if not self.parent_context_enabled:
            return {}
        parent_ids = {
            str(parent_id)
            for hit in hits
            if (parent_id := hit.chunk.metadata.get("parent_chunk_id"))
        }
        return self.retrieval.database.get_chunks(parent_ids)

    @staticmethod
    def _append_conflict_notices(question, extractive, hits, conflicts) -> None:
        if not extractive.sufficient or not conflicts:
            return
        question_terms = meaningful_terms(question)
        hit_by_id = {hit.chunk.id: hit for hit in hits}
        for conflict in conflicts:
            conflict_type = conflict["conflict_type"]
            should_show = conflict_type == "ambiguous_identifier" or (
                conflict_type == "historical_current_scope_collision"
                and question_terms.intersection(
                    {"domain_price", "quotation", "quote", "historical", "history", "报价", "历史"}
                )
            )
            if not should_show:
                continue
            evidence = [
                hit_by_id[chunk_id]
                for chunk_id in conflict["evidence_chunk_ids"]
                if chunk_id in hit_by_id
            ]
            for hit in evidence:
                if hit not in extractive.used_hits:
                    extractive.used_hits.append(hit)
            citations = [
                str(extractive.used_hits.index(hit) + 1)
                for hit in evidence
                if hit in extractive.used_hits
            ]
            suffix = " ".join(f"[{number}]" for number in citations)
            if conflict_type == "ambiguous_identifier":
                claim_text = (
                    "\nConflict notice: this model maps to multiple active product IDs; "
                    "the model alone is not a unique identifier."
                )
            else:
                claim_text = (
                    "\nGovernance note: the dated platform reference and historical quotation "
                    "are different evidence types; neither is a verified current customer "
                    "quotation."
                )
            extractive.text += f"{claim_text} {suffix}"
            extractive.claims.append(
                GroundedClaim(
                    text=claim_text.strip(),
                    supported=True,
                    evidence_hits=evidence,
                    claim_type="conflict_notice",
                )
            )
