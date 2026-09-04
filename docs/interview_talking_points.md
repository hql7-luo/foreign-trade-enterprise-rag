# Interview talking points

**Why build this?** Retrieval alone does not tell an employee whether a product fact is
current, historical, approved or missing. I wanted the evidence and update workflow to be visible.

**Why RAG rather than fine-tuning?** Product facts change. Keeping them outside model weights
makes source updates, deletion, traceability and approvals more manageable.

**Why hybrid retrieval?** Exact identifiers need structured lookup; wording differences benefit
from multilingual embeddings, while BM25 retains literal terms. RRF combines their rankings.

**Why Qdrant and SQLite?** Qdrant supports dense and sparse retrieval. SQLite makes the
single-instance demo easy to reproduce while preserving structured facts and audit events.
Neither choice proves readiness for a high-concurrency deployment.

**How are hallucinations controlled?** Claims require explicit field evidence. The public
answerer is extractive; unknown fields are not filled by an LLM. Narrow unsupported-field
tests passed, but that is not a guarantee of zero semantic errors.

**How did you evaluate it?** I froze 70 newly authored synthetic questions, sources and code
hashes, saved immutable first-run outputs and ran regression checks. I disclose the grading
rules and category failures. The internal holdback is not external human-blind validation.

**Why do scores vary between splits?** Short identifiers and less predictable wording exposed
ranking and claim-planning limits that simple exact questions missed. I reported failures
instead of repeatedly adjusting labels or rules to maximize the benchmark.

**How do approvals work?** A validated upload proposes a field value. Reviewers compare it
with the current value, inspect its version/evidence and provide a note. Approval updates the
master; controlled reindexing updates future answers. Superseded values remain in history.

**How is company data protected?** This edition uses newly invented data and starts with
independent Git history. Raw records are never served by URL; uploaded evidence is bounded,
scanned and quarantined; all runtime state and credentials stay outside tracked assets.

**What would you improve?** Independent human-written evaluation, better abbreviated-identifier
handling, more precise multi-claim planning and atomic rebuilds. These are not hidden claims
that the current version already solves them.

**What changes for a real deployment?** Real authority ownership, SSO/RBAC policy review,
threat modeling, encryption/backup operations, monitoring, workload testing and an appropriate
database/index strategy. The repository contains deployment configuration, not a live paid site.
