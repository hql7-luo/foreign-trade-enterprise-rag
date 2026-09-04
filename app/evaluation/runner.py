"""Transparent synthetic claim/source grading; no source-specific answer labels in code."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from time import perf_counter


def matches_source(chunk, selector):
    return all(getattr(chunk, key, None) == value for key, value in selector.items())


def _percentile(values, quantile):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * quantile))]


@dataclass
class EvaluationResult:
    summary: dict
    items: list[dict]

    def to_dict(self):
        return asdict(self)


def run_evaluation(service, questions, *, top_k=8):
    if isinstance(questions, Path):
        questions = json.loads(questions.read_text())
    if isinstance(questions, dict):
        questions = questions["questions"]
    with service.retrieval.database.connect() as connection:
        identifiers = [row[0] for row in connection.execute("SELECT id FROM indexed_chunks")]
    corpus = service.retrieval.database.get_chunks(identifiers)
    rows = []
    for case in questions:
        relevant = {
            chunk.id
            for chunk in corpus.values()
            if any(matches_source(chunk, selector) for selector in case["relevance"])
        }
        if not relevant:
            raise ValueError(f"No grounded source matches evaluation case {case['id']}")
        for claim in case["claims"]:
            if not any(
                matches_source(chunk, claim["source"])
                and all(term.casefold() in chunk.content.casefold() for term in claim["contains"])
                for chunk in corpus.values()
            ):
                raise ValueError(f"Expected claim is not source-grounded: {case['id']}")
        started = perf_counter()
        result = service.query(case["question"], limit=top_k, debug=True)
        latency = (perf_counter() - started) * 1000
        ranks = [
            i
            for i, hit in enumerate(result.retrieved_context, 1)
            if any(matches_source(hit.chunk, selector) for selector in case["relevance"])
        ]
        correct_claims, correct_citations = 0, 0
        for expected in case["claims"]:
            supporting = [
                claim
                for claim in result.claims
                if claim.supported
                and all(term.casefold() in claim.text.casefold() for term in expected["contains"])
            ]
            if supporting:
                correct_claims += 1
                cited = service.retrieval.database.get_chunks(
                    [source.chunk_id for claim in supporting for source in claim.sources]
                )
                if any(matches_source(chunk, expected["source"]) for chunk in cited.values()):
                    correct_citations += 1
        sufficiency = result.sufficient_information == case["expected_sufficient"]
        covered = correct_claims == len(case["claims"])
        # Field-specific unsupported claims must not appear as supported facts.
        hallucination = any(
            c.supported and c.claim_type in case.get("unsupported_fields", [])
            for c in result.claims
        )
        rows.append(
            {
                "id": case["id"],
                "category": case["category"],
                "question": case["question"],
                "expected_claims": case["claims"],
                "expected_sufficient": case["expected_sufficient"],
                "ranks": ranks,
                "relevant_count": len(relevant),
                "answer_correct": covered and sufficiency and not hallucination,
                "citation_correct": correct_citations == len(case["claims"]),
                "sufficiency_correct": sufficiency,
                "hallucination": hallucination,
                "unsupported_question": bool(case.get("unsupported_fields")),
                "required_claims": len(case["claims"]),
                "covered_claims": correct_claims,
                "latency_ms": latency,
                "answer": result.answer,
                "sources": [asdict(source) for source in result.sources],
                "retrieved_evidence": [
                    {
                        "source_file": h.chunk.source_file,
                        "product_id": h.chunk.product_id,
                        "section": h.chunk.section,
                        "row": h.chunk.row_start,
                        "content": h.chunk.content,
                        "dense": h.dense_score,
                        "bm25": h.bm25_score,
                        "rrf": h.fused_score,
                        "reranker": h.reranker_score,
                    }
                    for h in result.retrieved_context
                ],
                "context_chars": result.answer_context_chars,
                "context_chunks": result.answer_context_chunks,
                "human_pass_fail": "unreviewed",
                "reviewer_notes": "",
            }
        )
    summary = summarize(rows)
    summary["by_category"] = {
        category: summarize([row for row in rows if row["category"] == category])
        for category in sorted({row["category"] for row in rows})
    }
    return EvaluationResult(summary, rows)


def summarize(rows):
    count = len(rows)
    claims = sum(row["required_claims"] for row in rows)
    unsupported = [row for row in rows if row["unsupported_question"]]
    multif = [row for row in rows if row["required_claims"] >= 2]
    return {
        "n": count,
        **{
            f"recall_at_{k}": sum(
                sum(rank <= k for rank in r["ranks"]) / r["relevant_count"] for r in rows
            )
            / count
            for k in (1, 3, 5, 8)
        },
        "mrr": sum(1 / min(r["ranks"]) if r["ranks"] else 0 for r in rows) / count,
        "answer_correctness": sum(r["answer_correct"] for r in rows) / count,
        "citation_correctness": sum(r["citation_correct"] for r in rows) / count,
        "sufficiency_correctness": sum(r["sufficiency_correct"] for r in rows) / count,
        "claim_coverage": sum(r["covered_claims"] for r in rows) / claims if claims else None,
        "multi_fact_completeness": sum(r["covered_claims"] == r["required_claims"] for r in multif)
        / len(multif)
        if multif
        else None,
        "unsupported_questions": len(unsupported),
        "unsupported_hallucination_rate": sum(r["hallucination"] for r in unsupported)
        / len(unsupported)
        if unsupported
        else None,
        "median_latency_ms": median(r["latency_ms"] for r in rows),
        "p95_latency_ms": _percentile([r["latency_ms"] for r in rows], 0.95),
        "mean_context_chars": sum(r["context_chars"] for r in rows) / count,
        "mean_context_chunks": sum(r["context_chunks"] for r in rows) / count,
    }
