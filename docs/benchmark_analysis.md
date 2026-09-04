# Synthetic benchmark: results and failures

These are new, fictional Northstar tests, not a reuse of any private evaluation.
The implementation, source manifest and all three question sets were frozen before the
first run. No labels or retrieval/answer rules were changed in response to these results.
The same agent authored the corpus and questions; none of the splits is independent
human-blind evidence. Human review remains uncompleted.

## First-run results

| Metric | Development (30) | Held-out (20) | Internal holdback (20) |
|---|---:|---:|---:|
| Recall@1 | 78.33% | 75% | 75% |
| Recall@3 | 90% | 95% | 90% |
| Recall@5 | 96.67% | 97.5% | 92.5% |
| Recall@8 | 96.67% | 97.5% | 95% |
| MRR | 0.9150 | 0.8875 | 0.8850 |
| Answer correctness | 96.67% | 80% | 85% |
| Citation correctness | 96.67% | 85% | 95% |
| Sufficiency/refusal correctness | 100% | 90% | 90% |
| Claim coverage | 94.74% | 77.27% | 91.30% |
| Multi-fact completeness | 90.91% | 60% | 87.5% |
| Unsupported-field hallucination | 0/5 | 0/3 | 0/5 |
| Median latency | 6.586 ms | 6.415 ms | 6.537 ms |
| P95 latency | 7.689 ms | 7.737 ms | 7.658 ms |
| Mean context characters | 1,364.3 | 1,257.2 | 1,503.5 |
| Mean context chunks | 2.47 | 2.35 | 2.80 |

Configuration: 384-dimensional deterministic hash fallback, BM25, local Qdrant, RRF,
lightweight reranking and extractive claim composition. These are not neural-provider
benchmark results. Warm latency excludes startup, ingestion and model download.
Per-category counts and scores are preserved in each first-run JSON's `summary.by_category`.
Dataset language/category distribution and hashes are in `evaluation/definition.json`.

## Every automatically failed answer

The complete question, labeled claims, retrieval results, answer and citations remain in
the respective immutable first-run artifact. This table summarizes the diagnosis without
changing the labels or treating an automated diagnosis as human review.

| ID | Observed failure | Classification | General future direction, not implemented |
|---|---|---|---|
| PD-017 | A partial vessel model prefix yields no verified exact product, rather than two options. | Partial structured lookup / missing retrieval candidates | Explicit prefix resolution with an ambiguity response |
| PH-004 | Correct inquiry response target, plus a spurious unsupported inquiries claim. | Claim planning / false insufficiency | Separate the requested field from incidental wording |
| PH-006 | An archive request is interpreted as current: current MOQ is returned and old quotation price is omitted. | Historical/current scope and synthesis | Test scope negation independently before any change |
| PH-010 | An abbreviated lantern identifier does not return the two expected options. | Partial structured lookup | Ask for a complete identifier or list unambiguous candidates |
| PH-014 | Dispatch handover selects order-entry handover instructions even though both phases are retrieved. | Evidence selection / wrong procedure phase | Select fields together with their section scope |
| PB-005 | An incomplete tote model prefix is refused instead of showing alternatives. | Partial structured lookup | General identifier completion, not per-question exceptions |
| PB-011 | Three historical terms are correct, but incidental “reply” creates an unsupported response-target claim. | Claim planning / false insufficiency | Distinguish request framing from required business claims |
| PB-018 | The correct exception instruction is accompanied by an unintended packaging claim. | Claim planning / false insufficiency | Handle incidental terminology without adding obligations |

PH-006 is a real scope error: a source-backed value can still answer the wrong question.
The narrow unsupported-field metric does not catch this. Accordingly, **zero detected
unsupported-field hallucinations is not a claim of zero misleading answers**.

The small hard-negative cases (neighboring full identifiers, misleading vocabulary and
unknown exact models) passed their defined checks; this is not evidence of exhaustive
robustness. Partial identifiers remain an explicit weakness. Multi-product and multi-source
recall uses the fraction of all relevant chunks, not simply whether any relevant hit appeared.

## Review workflow

Copy a first-run artifact to an ignored local review location, then fill `human_review`
and `reviewer_notes` per item. Do not overwrite first-run files. Review scope, factual
coverage, claim-to-source attribution and appropriate uncertainty, not only word overlap.
Any objective label correction requires a separate reason and a separately labeled score.
No human approval or label corrections are claimed in this release.
