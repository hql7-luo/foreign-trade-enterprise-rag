# Independent public portfolio release

Display name: **Foreign Trade Enterprise RAG**. Repository name: `foreign-trade-enterprise-rag`.
Workspace directory name: `foreign-trade-enterprise-rag-public`, separate from the private
engineering source. Public version `v1.0.0` belongs only to this independent history.

## Contents

- Generic backend/frontend, retrieval framework, governance, security and operational code
  were reused after inspection. Business-coupled adapters were rebuilt for the public schema.
- Private-derived data, tests, evaluations, docs, media and Git history were not transferred.
- Five new synthetic source files: 10 products, 14 knowledge records and 24 baseline chunks.
  The separate MOQ update creates a pending review item and a 25th chunk after approval/reindex.
- Ten products include a shared model number, overlapping search attributes, supported
  specifications, explicit missing fields, simulated compliance evidence and expired quotes.
- New 30/20/20 question splits with immutable first-run results and recorded implementation
  hashes. No private metrics are reproduced.

## Synthetic Public Demo Benchmark

| Split | N | Recall@5 | Answer correctness | Citation correctness | Claim coverage |
|---|---:|---:|---:|---:|---:|
| Development | 30 | 96.67% | 96.67% | 96.67% | 94.74% |
| Held-out | 20 | 97.5% | 80% | 85% | 77.27% |
| Internal frozen holdback | 20 | 92.5% | 85% | 95% | 91.30% |

Offline hash/BM25 configuration, automatic source/claim checks, developer-authored synthetic
data; not neural-provider results or independently human-blind validation. Narrow unsupported
field checks found 0/5, 0/3 and 0/5 failures, but a historical-scope error remains. Read
[all metrics and failures](benchmark_analysis.md) before interpreting these numbers.

## Validation and assets

Clean-room verification was repeated in the new sibling directory with freshly installed
locked Python and frontend environments, a new SQLite/Qdrant runtime and only packaged sources.
The complete real browser approval/reindex workflow passed again from that directory.
No runtime access to the private project was required. Local Git author metadata intentionally
uses a generic portfolio maintainer and a non-deliverable example-domain address.

Backend: 42 tests passed, Ruff and compile checks passed. Frontend: 13 tests passed,
TypeScript and production build passed; tests include axe checks with contrast excluded.
All 70 frozen synthetic regressions passed. Optional multilingual MiniLM downloaded into an
ignored cache and produced two 384-dimensional Chinese/English vectors; it was not benchmarked.

The real browser sequence verified Employee citations and refusal, Admin staging, Reviewer
approval, Product Master history, completed reindex and the final approved-value citation.
The new 155.62-second 1080p silent MP4 and fourteen reviewed screenshots contain only Northstar
data. See [recording runbook](demo/recording_runbook.md) and [privacy audit](publication_privacy_audit.md).

README, architecture diagrams, demo script/checklist, portfolio page, resume bullets,
interview notes and a portfolio-safe retrospective are included.

## Publication status and remaining manual actions

Local release: one independent initial release commit on `main`, with the public `v1.0.0`
tag. Resolve its exact object with `git rev-parse 'v1.0.0^{commit}'`; this tag is unrelated to
any private repository's release. All 148 release files passed staged-content and Git-object
checks. Only `data/private/.gitkeep` is tracked under the private runtime path.

GitHub CLI is not installed on the validation host. No remote repository, hosted release,
video upload or paid cloud deployment has been created. Docker is also unavailable locally;
configuration and a clean-stack CI job are provided, but Docker execution and remote CI success
are not claimed. No open-source license has been selected.
Compose/CI YAML, declared services, persistent-volume definitions and required build inputs
were checked locally; this is not a substitute for executing Docker.

After installing GitHub CLI, run these commands **from this independent public directory only**.
First inspect authentication and whether a repository already exists; do not create a duplicate.

```bash
gh auth login
gh auth status
git status --short
git log --oneline --all
git tag --list
uv run python -m scripts.audit_public_tree
gh repo view foreign-trade-enterprise-rag
```

If no such repository exists:

```bash
gh repo create foreign-trade-enterprise-rag --public --source=. --remote=origin --push
git push origin v1.0.0
gh repo edit --description 'Enterprise RAG knowledge assistant for foreign-trade workflows with multilingual hybrid retrieval, claim-level citations, governed fact approval, RBAC, and reproducible evaluation.'
gh repo edit --add-topic rag --add-topic qdrant --add-topic fastapi --add-topic react --add-topic hybrid-search --add-topic knowledge-management --add-topic multilingual --add-topic enterprise-ai
gh release create v1.0.0 --verify-tag --title 'v1.0.0 — Foreign Trade Enterprise RAG' --notes-file docs/release_notes.md
gh release upload v1.0.0 docs/demo/enterprise-rag-demo.mp4
```

If it exists, verify ownership and its history first, then configure/use its remote without
force-pushing or replacing unrelated content. Confirm the remote branch, tag, release, README
images and CI results after publication. The MP4 is already small enough to be tracked normally;
the release upload is optional. Production exposure still requires real Docker/HTTPS validation.

## Remaining limitations

Partial identifiers, incidental words adding unsupported claims, historical/current scope and
SOP phase selection remain imperfect. Single-worker operations and manifest-bound maintenance
are intentional limits. See the README for precise model, security and backup boundaries.
Future work is optional; no retrieval tuning or paid deployment was performed for publication.
