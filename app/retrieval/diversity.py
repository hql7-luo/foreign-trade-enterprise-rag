"""Bounded diversity selection for inherently open-ended product discovery."""

from __future__ import annotations

from app.domain import ProductMatch, RetrievalHit
from app.text import meaningful_terms, normalize_text

OPEN_DISCOVERY_CUES = {
    "options",
    "choices",
    "shortlist",
    "short_list",
    "few",
    "several",
    "multiple",
    "recommend",
    "recommendation",
    "recommendations",
    "different",
    "two",
    "几个",
    "几款",
    "两个",
    "不同",
    "选择",
    "推荐",
    "哪些",
}
COMPARISON_CUES = {"compare", "comparison", "versus", "separate", "分别", "对比", "比较"}


def is_open_product_discovery(
    question: str,
    matches: list[ProductMatch],
    *,
    knowledge_intent: bool = False,
) -> bool:
    """Return true only when a product query reasonably calls for several entities."""

    if knowledge_intent:
        return False
    normalized = normalize_text(question)
    terms = meaningful_terms(question)
    exact = [match for match in matches if "exact " in match.reason]
    comparison = bool(terms.intersection(COMPARISON_CUES)) or any(
        cue in normalized for cue in (" vs ", "one ", "另一个", "分别", "两条", "two records")
    )
    if exact and not comparison:
        return False
    cue_match = bool(terms.intersection(OPEN_DISCOVERY_CUES | COMPARISON_CUES)) or any(
        cue in normalized
        for cue in (
            "short list",
            "active options",
            "what active options",
            "give me a few",
            "给两个",
            "给几个",
            "几类货",
        )
    )
    product_signal = bool(matches)
    return cue_match and product_signal


def desired_product_count(question: str) -> int:
    normalized = normalize_text(question)
    if any(cue in normalized for cue in ("two", "两个", "两款", "one ", "另一个")):
        return 2
    if any(cue in normalized for cue in ("few", "several", "short list", "几个", "几款")):
        return 4
    return 3


def diversify_product_hits(
    question: str,
    hits: list[RetrievalHit],
    matches: list[ProductMatch],
    *,
    limit: int,
) -> tuple[list[RetrievalHit], dict[str, object]]:
    """Use a small MMR-style pass while retaining the original candidate scores."""

    match_scores = {match.product.product_id: match.score for match in matches}
    product_hits = [
        hit
        for hit in hits
        if hit.chunk.category == "current_product_listing" and hit.chunk.product_id
    ]
    desired = min(desired_product_count(question), len(product_hits), limit)
    if desired < 2:
        final = hits[:limit]
        _reset_final_ranks(final)
        return final, {"applied": False, "selected_product_ids": []}

    query_terms = meaningful_terms(question)
    rank_by_id = {hit.chunk.id: rank for rank, hit in enumerate(hits, start=1)}
    feature_terms = {
        hit.chunk.id: meaningful_terms(
            f"{hit.chunk.content} {hit.chunk.metadata.get('product_group', '')}"
        )
        for hit in product_hits
    }

    def relevance(hit: RetrievalHit) -> float:
        rank_score = 1.0 - ((rank_by_id[hit.chunk.id] - 1) / max(len(hits), 1))
        structured = min(match_scores.get(hit.chunk.product_id or "", 0.0) / 100.0, 1.0)
        overlap = min(len(query_terms.intersection(feature_terms[hit.chunk.id])) / 6.0, 1.0)
        return 0.55 * rank_score + 0.3 * structured + 0.15 * overlap

    selected: list[RetrievalHit] = []
    remaining = list(product_hits)
    while remaining and len(selected) < desired:

        def mmr(hit: RetrievalHit) -> tuple[float, float, str]:
            redundancy = max(
                (
                    _jaccard(feature_terms[hit.chunk.id], feature_terms[item.chunk.id])
                    for item in selected
                ),
                default=0.0,
            )
            if any(hit.chunk.model == item.chunk.model for item in selected):
                redundancy = max(redundancy, 1.0)
            score = 0.82 * relevance(hit) - 0.18 * redundancy
            return score, relevance(hit), hit.chunk.id

        winner = max(remaining, key=mmr)
        selected.append(winner)
        remaining.remove(winner)

    selected_ids = {hit.chunk.id for hit in selected}
    final = selected + [hit for hit in hits if hit.chunk.id not in selected_ids]
    final = final[:limit]
    _reset_final_ranks(final)
    return final, {
        "applied": True,
        "requested_count": desired,
        "selected_product_ids": [hit.chunk.product_id for hit in selected],
        "selected_models": [hit.chunk.model for hit in selected],
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _reset_final_ranks(hits: list[RetrievalHit]) -> None:
    for rank, hit in enumerate(hits, start=1):
        hit.final_rank = rank
