# Synthetic Public Demo Benchmark

All questions and labels were newly authored from the fictional Northstar source files.
No private questions, metrics, identifiers or answer dumps are included.

Splits: development 30, held-out 20, blind-named 20. Each split was authored before
running any of them. Because the same development agent authored the corpus and
questions, **the blind-named split is an internal frozen holdback, not an independent
human-blind or real-world benchmark**. No claim of generalization from this small corpus.

`definition.json` freezes question/source/implementation SHA-256 hashes. First-run
outputs are write-once. Do not edit labels or tune on failures to improve the score.
The output contains review fields initially set to `unreviewed`; a human must supply
their own decisions. No model-generated review is presented as human approval.

## Grading

- Recall@K: macro-average fraction of all labeled relevant chunks retrieved per question.
  Multi-source questions require all relevant chunks for full recall; MRR uses the first.
- Answer correctness: all expected supported claim substrings appear in supported claims,
  sufficiency matches the label, and no forbidden unsupported field is asserted.
- Citation correctness: every expected claim is associated with its labeled source.
  Questions with no expected supported claims are vacuously citation-correct. Inspect the
  category breakdown; this is not an independent semantic entailment judgment.
- Claim coverage: supported expected claims matched / all expected supported claims.
- Multi-fact completeness: all expected claims covered on cases with at least two claims.
- Unsupported hallucination: a listed unsupported field is marked supported. This narrow
  automatic test does not detect every possible semantic hallucination or misleading wording.
- Median/P95 latency: warm local query time; excludes model download, startup and ingestion.

The offline demo runs deterministic 384-dimensional feature hashing plus BM25 in Qdrant.
It is **not neural semantic retrieval**. Multilingual MiniLM is a separately configurable
FastEmbed provider (384 dimensions); report its provider explicitly if benchmarking it.

Run each split into a new output path, for example:

```bash
uv run python -m scripts.public_benchmark --split dev --output evaluation/results/dev_first_run.json
uv run python -m scripts.public_benchmark --split held_out --output evaluation/results/held_out_first_run.json
uv run python -m scripts.public_benchmark --split blind --output evaluation/results/blind_first_run.json
```

Review JSON outputs include each question, expected claims, actual answer, source citations,
retrieved evidence, automatic grades, human pass/fail, and reviewer notes. If a label is
objectively wrong, document a separate correction without overwriting the first-run result.
