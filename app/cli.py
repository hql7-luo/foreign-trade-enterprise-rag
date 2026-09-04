"""Developer CLI for querying and evaluating an ingested knowledge base."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.config import Settings
from app.evaluation.runner import run_evaluation
from app.runtime import build_rag_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Foreign-trade enterprise RAG utilities")
    parser.add_argument("--database", type=Path, help="Override SQLite database path")
    parser.add_argument("--qdrant-path", help="Override local Qdrant storage path")
    parser.add_argument("--qdrant-url", help="Use a running Qdrant server")
    parser.add_argument(
        "--reranker-mode",
        choices=("heuristic", "cross_encoder", "hybrid"),
        help="Override the post-retrieval reranker experiment mode",
    )
    parser.add_argument("--reranker-model", help="Override the local cross-encoder model")
    parser.add_argument(
        "--answer-mode",
        choices=("legacy", "claim_level"),
        help="Override grounded answer synthesis mode",
    )
    parser.add_argument(
        "--chunking-strategy",
        choices=("legacy", "source_aware"),
        help="Expected chunking strategy for the selected index",
    )
    parser.add_argument(
        "--parent-context",
        action="store_true",
        help="Attach a selected child chunk's parent section to answer context",
    )
    parser.add_argument(
        "--diversity-selection",
        action="store_true",
        help="Use MMR-style entity diversity for open-ended product discovery",
    )
    parser.add_argument(
        "--sibling-evidence",
        action="store_true",
        help="Add bounded complementary child evidence for source-aware chunks",
    )
    parser.add_argument(
        "--sibling-max-chunks",
        type=int,
        help="Maximum complementary siblings added to answer evidence",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    query_parser = subparsers.add_parser("query", help="Ask one grounded question")
    query_parser.add_argument("question")
    query_parser.add_argument("--debug", action="store_true")
    query_parser.add_argument("--top-k", type=int, default=8)

    eval_parser = subparsers.add_parser("evaluate", help="Run the governed evaluation set")
    eval_parser.add_argument(
        "--questions",
        type=Path,
        default=Path("evaluation/public_dev_questions.json"),
    )
    eval_parser.add_argument("--top-k", type=int, default=8)
    eval_parser.add_argument("--summary-only", action="store_true")
    eval_parser.add_argument("--output", type=Path)
    return parser


def _settings_from_args(args: argparse.Namespace) -> Settings:
    overrides = {}
    if args.database:
        overrides["database_path"] = args.database
    if args.qdrant_path:
        overrides["qdrant_path"] = args.qdrant_path
    if args.qdrant_url:
        overrides["qdrant_url"] = args.qdrant_url
    if args.reranker_mode:
        overrides["reranker_mode"] = args.reranker_mode
    if args.reranker_model:
        overrides["reranker_model"] = args.reranker_model
    if args.answer_mode:
        overrides["answer_mode"] = args.answer_mode
    if args.chunking_strategy:
        overrides["chunking_strategy"] = args.chunking_strategy
    if args.parent_context:
        overrides["parent_context_enabled"] = True
    if args.diversity_selection:
        overrides["diversity_selection_enabled"] = True
    if args.sibling_evidence:
        overrides["sibling_evidence_enabled"] = True
    if args.sibling_max_chunks is not None:
        overrides["sibling_max_chunks"] = args.sibling_max_chunks
    return Settings(**overrides)


def main() -> None:
    args = build_parser().parse_args()
    service = build_rag_service(_settings_from_args(args))
    try:
        if args.command == "query":
            result = service.query(args.question, debug=args.debug, limit=args.top_k)
            output = {
                "answer": result.answer,
                "sufficient_information": result.sufficient_information,
                "sources": [asdict(source) for source in result.sources],
                "claims": [asdict(claim) for claim in result.claims],
                "answer_context_chars": result.answer_context_chars,
                "answer_context_chunks": result.answer_context_chunks,
                "retrieved_context": [
                    {
                        "chunk_id": hit.chunk.id,
                        "source_file": hit.chunk.source_file,
                        "section": hit.chunk.section,
                        "row_number": hit.chunk.row_start,
                        "product_sku": hit.chunk.model,
                        "dense_score": hit.dense_score,
                        "bm25_score": hit.bm25_score,
                        "rrf_score": hit.fused_score,
                        "heuristic_score": hit.heuristic_score,
                        "cross_encoder_score": hit.cross_encoder_score,
                        "reranker_score": hit.reranker_score,
                    }
                    for hit in result.retrieved_context
                ],
                "conflicts": result.conflicts,
                "debug": result.debug,
            }
        else:
            output = run_evaluation(service, args.questions, top_k=args.top_k).to_dict()
            if args.summary_only:
                output.pop("items", None)
        rendered = json.dumps(output, ensure_ascii=False, indent=2)
        if getattr(args, "output", None):
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
    finally:
        service.retrieval.vector_store.close()


if __name__ == "__main__":
    main()
