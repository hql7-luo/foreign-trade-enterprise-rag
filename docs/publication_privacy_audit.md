# Publication privacy audit

Scope: the independent public portfolio edition, not an in-place sanitization of an older
repository. Every business source, fixture, question, expected answer and benchmark result
was authored anew from fictional Northstar data. No private repository objects were imported.

## Assembly policy

Reused and reviewed generic engineering components: FastAPI, SQLite schema, Qdrant/BM25,
embedding provider interfaces, ranking framework, governance lifecycle, roles, sessions,
staging/jobs, React components, privacy controls and deployment tooling.

Source-specific loaders, business aliases, source authority bindings, answer field adapters,
business fixtures, all evaluations and all documentation were rebuilt for this public corpus.
Private catalogs, quotations, SOPs, market text, source-specific metadata and prior benchmark
artifacts were excluded, including transformed or paraphrased private facts. The new data is
not a rename of real records. No old screenshots or video were reused.

## Checks performed

- Candidate text/code, JSON, CSV, tests, environment examples, scripts and documents were
  scanned against a private-only list of 323 known identifiers, titles, source filenames,
  organization terms and old evaluation questions. The list and its private inspection
  helpers remain outside this repository. No matches were found in release content.
- High-confidence key/token patterns, personal paths, email/phone/bank-like content and
  credential assignments were inspected. Example-domain email strings in scanner rejection
  tests are deliberately non-deliverable fixtures, not customer identities or credentials.
  The reserved fictional phone number, zero-pattern account number and bare key header in
  negative tests are also deliberate rejection inputs; no working key material is included.
- Raw SQLite, vector state, downloaded model weights, local auth/session files, logs, coverage,
  dependency/build caches and temporary telemetry files were excluded from the release set.
  `data/private/.gitkeep` is the only permitted tracked entry under `data/private`.
- Runtime-generated source excerpts are present only in the **new synthetic** first-run
  results and screenshots. No private answer dumps or historical private scores are included.
- Docker contexts were reviewed for allowlist exclusions. Frontend source/build assets were
  checked for private paths and identifiers; generated bundles are not committed.
- New media: all 545 browser capture frames received local OCR checks for known private
  identifiers and the generated demo passwords. All fourteen scene checkpoints were visually
  inspected. The final MP4 decodes fully, has no audio and reports zero container metadata items.
  No terminal, personal browser chrome, notification or credential entry is recorded.
- `scripts/audit_public_tree.py` checks tracked content, staged bytes and every local Git
  object for release hygiene and obvious secrets. Fresh Git storage must have no alternates.

Scanners are defense in depth, not proof that arbitrary future uploads are public-safe.
The stronger protection is the new source corpus and independent history boundary.

## Original project preservation

Read-only before/after content manifests verify the original source files, application files,
normal Git history, branch and existing release tag were not changed by this work. The external
business source directory also remained unchanged. The desktop host updated four internal
turn-diff checkpoint references during the task; these are recorded as a host bookkeeping
exception, not described as unchanged bytes. No such references or private commit IDs were
copied into the public repository, and no original history was rewritten.

## Decision

The assembled synthetic content and newly recorded media pass the pre-initialization privacy
review. All 148 staged release files and all newly created Git objects also passed the
independent staged/object scan. No private Git storage or alternates were imported. GitHub
publication remains a separate authenticated action; no remote URL or successful upload is
claimed. Do not publish new content if provenance is uncertain or a later scan raises a finding.
