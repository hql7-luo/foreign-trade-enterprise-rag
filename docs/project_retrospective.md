# Portfolio-safe retrospective

The goal was not just document search: an employee should see what evidence supports an answer,
whether it is current, and who approved a change. The public edition demonstrates that loop
without exposing the business records that originally motivated the architecture.

The hardest boundary was between relevance and authority. Historical terms can be relevant
without being current truth. Source-backed values can still answer the wrong question.
An approval must update structured knowledge, retrieval state and the citation, not merely UI text.

Evaluation is another boundary. Developer-authored templates can overstate usefulness. The new
synthetic holdback still exposes partial-identifier and historical-scope failures. Reporting
those failures is more credible than adjusting labels or rules until a tiny dataset is perfect.
The public tests and scores are synthetic only; no private benchmark is reproduced here.

Keeping a small, inspectable architecture made the approval lifecycle and evidence chain easier
to test. It also leaves real limits: a rule-based planner, single-worker operations, narrow
automatic grading and no independent security or human benchmark review.

For a real enterprise deployment, the next priorities would be independent task evaluation,
identity integration, explicit document ownership, online migration/recovery procedures and
query-scope validation. They are future requirements, not claims made by this portfolio release.
