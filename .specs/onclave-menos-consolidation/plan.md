---
created: 2026-08-11
status: approved
owners:
  - onclave
  - homelab-infra
  - dotfiles
---

# Plan: Replace Menos with the Unified Single-Language Onclave API (Clean Cutover)

## Outcome

Onclave becomes the sole product, release, deployment, and public API for the current Onclave and Menos capabilities, implemented in one first-party language (TypeScript). Every Menos API behavior with a real consumer, including the `/yt` YouTube transcription workflow, is served by the Onclave API. The standalone Menos deployment, its Python service, its public endpoint, and the public RabbitMQ management hostname are removed. Single-operator service: one clean cutover, no parallel run, no canary, no client compatibility aliases.

## Confirmed Decisions

- **Single language**: All first-party Onclave service code is TypeScript in the existing pnpm workspace. The Python `services/menos/` subproject is deleted once the port passes its parity suite. Dependency containers (PostgreSQL, S3-compatible storage, Ollama, SearXNG, docling-serve, RabbitMQ) are not "language"; they remain pinned containers.
- **Single service**: The content-vault API merges into the existing Onclave core Node service as one process and one image. One HTTP listener, one auth middleware, one combined health/readiness contract (broker state, source revision, dependency checks). This removes the current `/health` collision by construction.
- **Single release**: One versioned Onclave app definition with digest-pinned images. No separately releasable Menos app definition survives.
- **Auth**: Every public route except health/readiness requires RFC 9421 HTTP signatures against the existing approved key identities. No new auth scheme.
- **Broker**: RabbitMQ stays internal. AMQP, credentials, topology, management API, and management UI never appear in the public API or a public hostname. No speculative broker-facing API operations.
- **Clean cutover**: Old and new stacks do not run side by side. Menos stops, state is adopted in place, the unified stack starts against it. The only safety retained is one verified pre-cutover backup (data-loss protection, per repo policy for Menos), not a rollback deployment.
- **Parity scope**: Defined by the frozen inventory from task 1 (real routes plus real client call sites). Routes with no known consumer are ported thin or dropped with explicit confirmation in the artifact.

## Boundaries

- Tasks 1-2 execute in `C:/Projects/Personal/onclave`. Task 3 executes in `homelab-infra`. Task 4 executes in `~/.dotfiles`. Task 5 executes in `homelab-infra` then `~/.dotfiles`. Each repo change stages only files named by its task; the dotfiles worktree and the private `values/` repo contain unrelated uncommitted work that must not be mixed in.
- The dotfiles Onclave submodule is updated only to published commits.
- Hermes, standalone SearXNG, SeaweedFS/OpenTofu state, and all other services are unchanged.
- The pre-cutover backup and stopped Menos data directories are not deleted in this plan; deletion requires separate explicit approval.

## Execution Plan

- [ ] **1. Freeze the parity contract.** (`onclave` repo) From the FastAPI app (`services/menos/menos/main.py`, `routers/`), the served OpenAPI document, and the real client call sites in `~/.dotfiles/tools/menos-youtube/` and `claude/` (commands, `shared/yt-instructions.md`, `hooks/menos-circuit/`), record one inventory: method, path, auth, request/response fields consumers actually read, and error semantics consumers branch on. Mark every route `keep`, `keep-thin`, or `drop-confirmed`; drops need operator confirmation in the artifact. Commit as `docs/menos/parity-contract.md`. Acceptance: every route in the Menos OpenAPI document appears exactly once with a disposition, and every dotfiles client script maps to a kept route. Verification: cross-check against `/openapi.json` and a grep of client scripts; no unmapped call site.

- [ ] **2. Port the content vault into the Onclave core service (TypeScript) and delete the Python service.** (`onclave` repo; after task 1) Implement kept routes inside `services/core/` in seam order: (1) RFC 9421 verification middleware and `authorized_keys` load/reload on all non-health routes; (2) PostgreSQL repository (schema adopted as-is, no redesign) and S3 client; (3) content CRUD/download, annotations, links/backlinks/chunks, tags, stats; (4) chunking, Ollama embeddings, semantic search; (5) ingest: URL detection, YouTube transcript fetch with Webshare proxy support, YouTube Data API metadata, docling-backed web ingestion, S3 layout compatible with existing objects; (6) jobs/pipeline: background LLM processing, reprocess, status, cancel; entities/graph/usage per contract; (7) combined health/readiness. Prove transcript-fetch parity (proxy included) early with a real video, not at the end. Replace `deploy/app/{onclave,menos}/` with one app definition and delete `services/menos/`, Menos-only just targets, and Menos-only CI once the parity suite passes. Acceptance: parity suite exercises every `keep` route with signed requests (auth failure, error semantics, ingest, transcript, job lifecycle, search) against a locally started unified stack on real-shaped data; `just check` passes; no first-party Python remains. Verification: focused Vitest during the port, then `just check`, app-definition validation, one containerized end-to-end smoke test via the unified endpoint only.

- [ ] **3. Cut the deployment over.** (`homelab-infra`; after task 2) Take one PostgreSQL backup plus an S3 object inventory (counts/bytes) and verify the backup is readable. Stop the Menos stack. Update Onclave pins via `just update`; rework `infra/ansible/roles/onclave_onramp/` and `infra/ansible/playbooks/onclave-onramp.yml` to deploy the unified app definition against the existing Menos data directories (PostgreSQL, S3/MinIO, Ollama) adopted in place, with the role health gate updated to the combined health contract in the same change. Move runtime secret families to the Onclave env contract: PostgreSQL credentials, S3 credentials, SearXNG secret, Webshare proxy credentials, YouTube API key, LLM provider keys, callback URL/secret (currently `MENOS_*` in BWS/inventory). Acceptance: unified endpoint healthy with expected revision and dependency readiness; table counts and object counts/bytes match the pre-stop inventory; one signed write/read round trip and one recorded search return expected results; onramp host memory/disk headroom confirmed with the full stack running. Verification: targeted service deployment path and direct endpoint checks only; no global apply. On failure: fix forward; the verified backup exists solely to prevent data loss, not to resurrect the old stack.

- [ ] **4. Cut clients over and prove `/yt`.** (`~/.dotfiles`; after task 3) One wave: point `tools/menos-youtube/` clients, `claude/hooks/menos-circuit/`, and installer-written endpoint config at the Onclave API base, and rename Menos vocabulary in the same change -- `MENOS_*` configuration names, the `tools/menos-youtube/` path, status artifacts, command docs -- to Onclave-owned names with no compatibility aliases. Update the Onclave submodule pin to the published task-2 commit. Prove directly: one real `/yt <youtube-url>` returning content ID, transcript, metadata, searchability, and a completed processing job; plus list, search, transcript, content, annotation, reprocess/status, circuit-probe, and cached-backfill paths. Acceptance: all listed workflows pass against Onclave; no executable file references the Menos hostname or `MENOS_API_BASE`. Verification: focused client pytest for changed modules, then repo `make check`.

- [ ] **5. Retire Menos surfaces.** (`homelab-infra`; after task 4) Remove `menos_onramp` from `infra/services.json`, its role/playbook/templates/tests, service-state entries, Caddy snippet, and DNS record; remove the RabbitMQ management hostname; keep AMQP reachable only from the approved private clients it has today. Do not delete Menos data directories or the task-3 backup. Acceptance: the Onclave hostname is the only public API for the consolidated product; Menos and RabbitMQ management hostnames no longer resolve or serve; `/yt` still passes; no executable file in either repo references retired hostnames. Verification: targeted DNS/Caddy/service checks, then exactly one final `just validate` in `homelab-infra`; `git diff --check` and public-safety/secret scans in each changed repo.
