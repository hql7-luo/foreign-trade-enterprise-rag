# Foreign Trade Enterprise RAG

An enterprise knowledge desk that combines evidence-grounded product answers with governed
fact approval and role-separated workflows.

## Resume bullets

- Built a FastAPI/React knowledge assistant using SQLite, Qdrant, configurable multilingual
  embeddings, BM25/RRF retrieval and claim-level evidence citations.
- Implemented source-version tracking, pending/approved/rejected/superseded product facts,
  Employee/Reviewer/Admin permissions, quarantined uploads and auditable reindex workflows.
- Created 70 fully synthetic evaluation cases and preserved first-run results; the 20-case
  internal frozen holdback reached 92.5% Recall@5 and 85% automated answer correctness, with
  explicit disclosure that it is not independently human-authored blind validation.

## Stack

Python, FastAPI, SQLite, Qdrant, FastEmbed/ONNX, React, TypeScript, Vite, pytest, Vitest,
axe-core, Ruff, Docker Compose and GitHub Actions.

## Why it is more than a basic chatbot

It distinguishes historical evidence from current approved facts, shows field-level gaps,
requires review before authority changes and lets users inspect the exact evidence used.
The public corpus is fully synthetic and has no private repository history.

## Limits

Small internal synthetic benchmark; no paid production deployment, no large-scale load test,
limited abbreviated-SKU handling and rule-based answer planning. Neural embeddings are
optional; reported public scores use the explicitly labeled deterministic fallback.
