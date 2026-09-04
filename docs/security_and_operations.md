# Security and local operations

This is an operator-controlled portfolio demo, not a security-certified service.
All packaged business data is fictional Northstar data. There is no paid cloud deployment.

## Boundaries checked

- FastAPI enforces Employee / Reviewer / Admin access on the server, not just navigation.
- Reviewer cannot invoke Admin staging or reindex operations. Employee cannot decide facts.
- Evidence is returned by indexed chunk identifier, with a confidentiality allowlist and a
  bounded excerpt. No route serves arbitrary source paths or a raw private data directory.
- Uploads receive filename/path checks, size and extension/MIME validation, parsing limits,
  and sensitivity scanning before quarantine. Only the controlled CSV fact format creates
  review proposals. Other permitted formats are previews, never automatic authority.
- Generated passwords use Argon2. Persistent sessions store token digests, not raw tokens.
  The React client retains its bearer token in memory only; a page reload requires login.
  Because authentication is not cookie-based, automatic cookie/CSRF assumptions do not apply.
- Environment examples contain no working credentials. Production configuration rejects
  unsafe or incomplete settings; browser origins, hosts and request limits are explicit.
- Structured operational logs omit passwords, raw tokens, source content and question text.
  Unexpected API failures use bounded messages instead of stack traces.
- Public read-only mode blocks mutation. The local operator launcher enables mutation only
  on loopback so the proposal/review workflow can be demonstrated.

Automated tests cover these boundaries, sessions across service recreation, request limits,
background job state, rejection/supersede history, and approval with a newly cited value.
They are not a substitute for independent penetration testing or enterprise authorization review.

## Startup and health

`uv run python -m scripts.local_demo` verifies the packaged source hashes, creates an isolated
`public-demo-runtime`, generates local credentials and ingests the seed catalog. Existing
unrecognized runtime/source paths fail closed. The local default needs no network model or
paid API; optional FastEmbed multilingual MiniLM requires a first-time model download.

`/live` reports process health. `/ready` (also `/api/health/ready`) checks the metadata and
retrieval state. An unready database/index should be repaired by an operator, not hidden by
substituting fabricated answers. Health details and diagnostics must not expose source text.

## Docker and CI

Compose defines a backend, built React frontend and Qdrant. Named volumes retain SQLite,
sessions and vector state; loopback-only published ports are for local demonstration.
Images use restricted privileges and read-only application filesystems where practical.
The Docker build context uses an allowlist and includes only `data/demo`, never runtime data.

GitHub Actions is configured for Python tests/Ruff/compile/frozen synthetic regressions,
frontend tests/TypeScript/build, and a clean Docker stack plus API smoke test.
Docker and GitHub CLI were unavailable on the validation host: **Docker execution and a
remote CI run are not claimed**. Execute the configured job before exposing an online demo.

## Backup, restore and reset

SQLite is the durable record of approved facts and audit events. Qdrant is derived and can
be rebuilt. Operator tooling in `scripts/demo_ops.py` validates an explicit demo marker,
exact source manifest, confined paths, checksums and SQLite integrity. Stop the backend first.
Restore preserves a recovery copy; sessions/uploads are cleared at reset/restore boundaries.

The maintenance tool intentionally rejects databases containing source families outside the
packaged manifest, including managed proposal uploads. Its baseline backup/restore/reset
path is tested; it is **not a general backup system for arbitrary uploaded sources**.
For a new demo recording after approval, preserve the previous runtime and start a new one:

```bash
uv run python -m scripts.local_demo --runtime runtime/second-take/public-demo-runtime
```

Do not use broad directory deletion to reset a demonstration. Never mount a real company
directory into this public demo. Multi-worker coordination, online migration, production
backups and HTTPS/domain management remain outside the portfolio release.

## Accessibility

Frontend tests exercise named controls, labels, errors, role navigation, evidence drawer
Escape/focus behavior and axe checks across the main role pages. Automated contrast checking
is disabled in the DOM test environment. The recorded browser flow was also visually reviewed;
this is not a full WCAG certification or a substitute for assistive-technology user testing.
