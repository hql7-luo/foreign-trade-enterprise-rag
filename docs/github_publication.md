# GitHub publication record

Publication date: 2026-09-04. Scope: the independent synthetic-only public portfolio edition.
The original private project was not used as a Git remote and was not modified during publication.

## Repository and release

| Item | Verified value |
|---|---|
| Repository | [hql7-luo/foreign-trade-enterprise-rag](https://github.com/hql7-luo/foreign-trade-enterprise-rag) |
| Visibility | Public |
| Default branch | `main` |
| Origin | `https://github.com/hql7-luo/foreign-trade-enterprise-rag.git` |
| Released implementation commit | `29ec2f8346e44267885eda814395fff59bce68fa` |
| Annotated tag | `v1.0.0` — unchanged, targeting the released implementation commit |
| Tag object | `64b89913ab880610244bac4e5859658cdd25e279` |
| GitHub Release | [v1.0.0 — Foreign Trade Enterprise RAG](https://github.com/hql7-luo/foreign-trade-enterprise-rag/releases/tag/v1.0.0) |

The final publication-documentation commit is the commit containing this record, available in
[its GitHub history](https://github.com/hql7-luo/foreign-trade-enterprise-rag/commits/main/docs/github_publication.md).
Resolve it locally with `git log -1 --format=%H -- docs/github_publication.md`; the file cannot
contain its own content-dependent commit hash. The release tag remains on the implementation
commit above, not on the later documentation commit. No force push or history rewrite was used.

The requested description and twelve relevant topics are configured. No license was chosen
on the author's behalf; public visibility alone does not grant redistribution rights.

## Validation

The [release CI run](https://github.com/hql7-luo/foreign-trade-enterprise-rag/actions/runs/33890245546)
passed all three jobs:

- Backend: pytest, Ruff, compileall, frozen synthetic regression verification and public-tree audit.
- Frontend: tests including automated accessibility checks, TypeScript and production build.
- Docker: Compose configuration, clean build/start/readiness and deployment smoke tests.

No RAG implementation, product behavior, benchmark artifact, evaluation label or threshold was
changed for publication. The benchmark remains **Synthetic Public Demo Benchmark**: development
N=30 (Recall@5 96.67%, answer 96.67%); held-out N=20 (97.5%, 80%); internal frozen holdback
N=20 (92.5%, 85%). These are not real-company results or independent human blind tests.

## Privacy and remote integrity

- Before pushing, the worktree was clean and the release had one independent root commit.
- The release audit passed for 148 tracked files and 181 local Git objects.
- All 148 remote file-object hashes exactly match the audited release tree, covering source
  code, tests, synthetic evaluations, documentation, screenshots and video.
- Only `data/private/.gitkeep` is tracked under the private runtime directory. No runtime
  database, Qdrant state, model cache, credential file or local `.env` is published.
- Lightweight checks found no private source names, personal absolute paths or obvious secrets.
  The earlier provenance and media review remains documented in the [privacy audit](publication_privacy_audit.md).
- GitHub authentication uses the CLI credential store; no token was placed in the repository,
  remote URL, release notes or publication files.

## Presentation and demo

The actual GitHub README loads its main screenshot and both additional screenshots at their
original 1920-pixel width. All sixteen original README relative links resolve to published
files/directories. GitHub-rendered Markdown includes the architecture Mermaid diagram markup,
synthetic benchmark disclosure, privacy statement and explicit no-live-deployment wording.

Video: [docs/demo/enterprise-rag-demo.mp4](https://github.com/hql7-luo/foreign-trade-enterprise-rag/blob/main/docs/demo/enterprise-rag-demo.mp4).
It is a normal Git blob, not an LFS pointer: 3,705,807 bytes, 155.62 seconds, 1920×1080,
silent H.264. The reviewed recording uses only fictional Northstar information.

- Git blob: `ffcd21641dfbfb7a30db62efb4228a63ae141fed`.
- SHA-256: `a63c96a08405374ae33f7a0e24394a983034b4075ed0fe48edd7ee86087e9085`.
- A full download through GitHub's blob API matched this SHA-256 exactly.
- No new media, credentials, private desktop views or source data were recorded for publication.

## Publication-only changes

Added repository/release/CI links, replaced obsolete not-yet-published instructions with actual
remote status, recorded successful Docker CI execution and added this publication record.
The application and frozen synthetic evaluations are unchanged.

GitHub's initially resolved network endpoint timed out from the publication host. A temporary
per-command connection to another GitHub-published address, with normal hostname/TLS checks,
completed the Git pushes. System DNS was not changed, no third-party relay was used and no
address override is committed or required by the application.

**No paid production deployment is currently running.** GitHub publication is not cloud
deployment; production deployment configuration exists, but an internet-facing service is not claimed.
