# Foreign Trade Enterprise RAG

**Trustworthy answers need trustworthy knowledge updates.**

Foreign-trade employees often have to connect product records, procedures and expired
quotations. This portfolio project makes evidence, uncertainty and approval status visible.

The solution combines hybrid retrieval with an internal knowledge desk: Employee chat,
interactive citations, a governed Product Master, Reviewer decisions and Admin ingestion jobs.
New facts remain proposals until approved, and historical terms do not become current policy.

**Technology:** FastAPI, React/TypeScript, SQLite, Qdrant, multilingual MiniLM option,
BM25, RRF, Docker and automated tests.

**Evaluation:** 70 newly authored synthetic cases. The 20-case internal frozen holdback
achieved 92.5% Recall@5, 85% automated answer correctness and 95% citation correctness.
This is not a real-company benchmark or independently human-authored blind evaluation.

**Images:** `03-grounded-product.png`, `04-evidence.png`, `08-pending-conflict.png`
under `docs/demo/screenshots/`. Show the governed update in the demo video.

**GitHub CTA:** View the source repository after publication; no URL is invented here.
**Video CTA:** Watch the local 2–3 minute workflow after attaching the verified MP4 to a release.

All business information belongs to fictional Northstar Trading. No paid production site
is running. Current limitations include abbreviation handling, ambiguous prose and the small
synthetic validation set.
