---
created: 2026-07-21
updated: 2026-07-23
status: completed
completed:
  - T1
  - T2
  - T3
  - T4
  - T5
  - T6
  - T7
---

# Plan: Rebuild the Onramp Host and Migrate Menos Directly to PostgreSQL

## Context

VM 112 exhausted the Proxmox `local-lvm` thin pool during the attempted Menos C2 SurrealDB import. QEMU entered `io-error`, the guest recorded EXT4 write failures, and the VM required incident recovery. The current VM is healthy again on a temporary 128 GB `vmstorage` root disk, but that filesystem must not become the long-term base.

The SurrealDB import also exposed database-specific restore friction: legacy schema definitions conflicted with the current schema, record references and datetimes required rewriting, duplicate relationships violated new constraints, managed migration history had to be excluded, and baseline seed rows conflicted with imported data.

Menos fits PostgreSQL well. Its authoritative data is relational, its graph is shallow, and its current corpus has about 45,932 1,024-dimensional chunk embeddings. PostgreSQL with pgvector, built-in full-text search, and pg_trgm can cover the current access patterns without a graph extension. PostgreSQL also provides mature logical dump, restore, constraint, migration, and recovery tooling.

The operator has decided not to import the legacy data into the new SurrealDB stack and then migrate it again. The new-stack C2 destination will be PostgreSQL only. The legacy source remains unchanged until cutover, and its data will be exported to a portable, validated interchange format and loaded directly into PostgreSQL. A disposable PostgreSQL preflight is still required before the single production import.

## Objective

Replace VM 112 with a clean two-disk apphost, convert Menos from SurrealDB to PostgreSQL without changing its external API behavior, export the legacy dataset to a portable format, prove the complete import and restore path in disposable PostgreSQL, then perform one production PostgreSQL import with exact data, object, search, readiness, and backup parity.

## Boundaries and Assumptions

- Tracked source remains generic and public-safe. Site-specific configuration, addresses, credentials, service state, manifests, and checksums remain in `values/`. Bulk data artifacts (typed NDJSON export, MinIO mirrors, PostgreSQL dumps) stay in untracked private staging and are never committed to `values/`; a recurring bulk-data backup system is deferred to a later plan.
- Recovery model: back up data, not VMs. OpenTofu and Ansible must be able to recreate the host on any PVE node; `values/` plus the data-restore path recreate service state. The legacy PVE server remains the authoritative Menos data fallback until a separate decommission plan.
- The root disk is 32 GB on `local-lvm`. A 512 GB data disk is on `vmstorage`.
- Guest LVM allocates 96 GB to `/var`, 352 GB to `/srv`, and leaves approximately 64 GB unallocated.
- Rootless Podman graphroot is `/srv/podman/anvil`; application state is `/srv/onramp`.
- PostgreSQL replaces SurrealDB in the new Menos app definition. No new-stack SurrealDB data volume, image, credential, readiness check, or backup path remains after migration.
- Use pgvector for `vector(1024)`, built-in PostgreSQL full-text search with GIN, and pg_trgm where fuzzy matching is already required. Do not add Apache AGE, pg_cron, or another extension without measured need.
- MinIO remains the object store. Ollama, SearXNG, Docling, Caddy, and the signed Menos API contract remain unchanged unless PostgreSQL integration requires a documented internal dependency change.
- Preserve public HTTP response shapes, record IDs, signed-request behavior, authorization keys, content semantics, and search filters.
- Do not import legacy `_migrations` rows into PostgreSQL. PostgreSQL schema migrations own their own fresh history.
- The legacy source is frozen: no ingest, edits, or deletions occur between plan approval and the production import, so the exact counts and checksums in T5 and T7 are authoritative gates.
- The old VM is not deleted until a fresh Onclave service-state backup and the validated portable Menos export exist. Rollback is recreate-from-source plus data restore into MinIO and PostgreSQL; no VM-level backup is created or restored in this plan.
- Restore stateful services sequentially. No consumer cutover, C3 ingest, legacy stop, soak, or legacy deletion is part of this plan.

## Architecture Decisions

- Use normalized PostgreSQL tables for `content`, `chunk`, `entity`, `content_entity`, `link`, `pipeline_job`, `llm_usage`, `tag_alias`, and `llm_pricing_snapshot`.
- Preserve current external IDs as text primary keys during migration. Enforce foreign keys and explicit uniqueness constraints instead of Surreal record references.
- Run the latest stable PostgreSQL major version available in the official pgvector container image, pinned by digest. pgvector is the only extension that constrains image choice; full-text search and pg_trgm ship with core PostgreSQL.
- Store chunk embeddings as `vector(1024)`. Begin with exact cosine queries; add or tune an HNSW index only after the existing retrieval evaluation proves the measured benefit and filtered-query behavior.
- Store metadata as `jsonb`, tags and hierarchy as text arrays, and timestamps as `timestamptz`.
- Add a generated or maintained `tsvector` over searchable chunk/content text with a GIN index. Fuse lexical and vector result lists in the existing application RRF/reranking layer rather than hiding ranking policy in a database extension.
- Use ordinary relational joins and recursive CTEs for graph endpoints. The current relationship workload does not justify a graph extension.
- Replace direct database-client access in routers, services, and scripts with repository methods. Database-specific SQL stays behind the repository boundary.
- Export legacy SurrealDB rows from the authorized source as typed NDJSON plus a manifest. Do not stage them in a destination or transitional SurrealDB instance.
- Use `pg_dump --format=custom` plus MinIO inventory and service configuration as the sole recovery contract for Menos data. Service-state archives cover configuration and keys only; they exclude bulk PostgreSQL and MinIO payloads.

## Executable Tasks

- [x] **T1 - Add the two-disk OpenTofu and guest-storage contract**
  - Files: `infra/opentofu/onramp-host.tf`, `infra/opentofu/variables.tf`, `infra/services.json`, `scaffold/terraform.tfvars`, `scripts/migrate-values.py`, private `values/terraform.tfvars`, and focused tests.
  - Action: retain `scsi0` as a 32 GB root disk on `local-lvm`; add a 512 GB `scsi1` data disk on `vmstorage`; expose deterministic guest layout values through dynamic inventory; allocate 96 GB `/var` and 352 GB `/srv` LVs with reserve.
  - Acceptance: OpenTofu declares exactly two disks; private and scaffold values agree with migration defaults; layout validation rejects missing devices, non-positive sizes, and insufficient reserve.
  - Verify: focused OpenTofu, inventory, and values-migration tests plus saved-plan inspection.
  - Result: two-disk and guest-layout contracts are in source and private values; `just validate` passed.

- [x] **T2 - Establish `/var`, `/srv`, and Podman graphroot before app installation**
  - Depends on: T1.
  - Files: `infra/ansible/roles/onramp_host/`, all rootless onramp service templates, and focused Ansible safety tests.
  - Action: fail closed unless the configured unused data device is present and unmounted; create the PV/VG/LVs and ext4 filesystems; copy the fresh VM's `/var` once; write UUID-backed `/etc/fstab`; reboot once; verify mounts before installing Podman or Caddy. Configure `/srv/podman/<deploy-user>` in managed `storage.conf`, keep app state under `/srv/onramp`, and add `RequiresMountsFor=/srv/podman/<deploy-user> /srv/onramp` to rootless units.
  - Acceptance: reruns are idempotent; mount failure cannot start app services; `podman info` reports the `/srv` graphroot; at least 10 percent of the guest VG remains free.
  - Verify: syntax/lint, ordering tests, and direct `findmnt`, `pvs`, `vgs`, `lvs`, `df`, and `podman info` checks after rebuild.
  - Result: fail-closed storage preparation, mount-gated units, and graphroot configuration pass `just validate`; direct host checks remain part of T6 after rebuild.

- [x] **T3 - Replace the Menos SurrealDB implementation with PostgreSQL**
  - Depends on: none; may proceed in parallel with T1-T2 in the separate Onclave repository.
  - Repository: `../onclave`, branch `feature/v2-broker-core` based on current published source.
  - Files: `services/menos/pyproject.toml`, lockfile, `menos/config.py`, `menos/models.py`, `menos/services/storage.py`, `menos/services/di.py`, `menos/services/migrator.py`, `menos/main.py`, `menos/routers/health.py`, all production call sites that access `repo.db` directly, database migrations, tests, `deploy/app/menos/compose.yaml`, environment examples/contracts, and Menos deployment/restore documentation.
  - Action: replace the Surreal client with a maintained PostgreSQL driver and explicit repository interface; move all raw database access behind repository methods; write one initial transactional SQL migration that creates the final normalized schema, constraints, pgvector, full-text GIN, and pg_trgm (do not port the legacy `.surql` history; new migrations accrete from this baseline); convert CRUD, jobs, metering, pricing, graph, vector search, lexical search, filtering, ordering, pagination, and purge behavior; configure a PostgreSQL service and healthcheck in Compose; rename settings and readiness output from SurrealDB to PostgreSQL. Add focused PostgreSQL integration tests for 1,024-dimensional cosine search, lexical GIN search, tag/type/tier filters, RRF input ordering, graph joins, uniqueness, foreign keys, transactions, and query limits. Add a logical backup helper that produces a custom-format `pg_dump`, manifest, and checksum without exposing credentials, plus a restore test into a fresh empty PostgreSQL volume.
  - Acceptance: no production Python imports `surrealdb`, calls `repo.db`, or executes SurrealQL; no deployment file starts SurrealDB; API contracts and IDs remain stable; startup migration failure is fatal rather than allowing the app to run against an unknown schema; PostgreSQL credentials never appear in argv or logs. A restored database passes migrations, readiness, and signed content/list/search requests; search evaluation does not materially regress against the accepted Menos baseline; any index added has supporting `EXPLAIN` evidence.
  - Verify: Menos unit/integration tests, Ruff, dependency lock validation, Compose config validation, API image build, clean-schema migration, second-run migration idempotency, direct API smoke tests against PostgreSQL, `pg_restore --list`, retrieval evaluation, and a dump/restore drill.
  - Result: PostgreSQL source, schema, Compose, and backup/restore contracts are implemented; 808 tests plus 2 live PostgreSQL contract tests, Ruff, lock, Compose, image build, migration idempotency, API startup, and dump/restore passed. Dataset-backed MinIO/Ollama and retrieval parity remain T5 preflight gates.

- [x] **T4 - Update homelab deployment, values, state, and documentation for PostgreSQL**
  - Depends on: T3 source contract.
  - Files: `infra/ansible/roles/menos_onramp/`, Menos playbooks, service-state catalog, scaffold/private environment and inventory, `scripts/migrate-values.py`, `scripts/import-menos-values.py`, `scripts/parse-env.py`, affected docs, and focused tests.
  - Action: consume the immutable PostgreSQL Menos Compose definition and API image; replace the Surreal image/password/namespace/database contract with digest-pinned PostgreSQL image, database/user/password settings, and `./data/postgres` persistence; keep database ports internal; require `/ready.checks.postgres == ok`; keep logical dump artifacts host-local under the managed backup boundary with only manifests and checksums recorded in `values/`; migrate existing private secret names without printing values.
  - Acceptance: no new-stack role, scaffold, private inventory, docs, backup definition, or test expects SurrealDB. Only the legacy export workflow may still reference SurrealDB. Existing unrelated service behavior remains unchanged.
  - Verify: focused role/scaffold/values tests, Ansible syntax/lint, public-safety checks, and `just validate`.
  - Result: homelab roles, scaffold/private values, migration helpers, service-state boundaries, and docs now consume PostgreSQL. Onclave commit `6641377f4ee173d92bb471a7c5e6ebf8876e6341`, its Compose checksum, and the published Menos API image digest were verified; Onclave CI and `just validate` passed.

- [x] **T5 - Export the legacy dataset and preflight the direct PostgreSQL import**
  - Depends on: T3 schema contract.
  - Files: one exporter script, one importer script, focused tests, and untracked private migration staging only for generated artifacts (never committed to `values/`).
  - Action: the exporter queries the authorized legacy SurrealDB source read-only and writes deterministic per-table NDJSON plus a manifest. Normalize record IDs to plain stable IDs, timestamps to RFC 3339 UTC, every present vector to exactly 1,024 finite floats, enums to strings, metadata to JSON, and references to explicit foreign-key fields. Exclude legacy schema definitions, `_migrations`, `test_table`, and managed PostgreSQL seed rows. Deduplicate `content_entity` by `(content_id, entity_id, edge_type)` using the already-approved highest-confidence, earliest-timestamp, lowest-ID rule and emit an audit report. Drop and audit exactly the 60 source chunks that share one missing parent content row and the one failed pipeline job that references a different missing parent; reject any other unresolved reference rather than synthesizing data. Package the NDJSON, MinIO files, manifest, and checksums without credentials. The importer loads the NDJSON into a clean PostgreSQL database in one transaction, preserves IDs, loads parent tables before foreign-key dependents, retains the managed migration history and pricing seed, mirrors MinIO with exact inventory verification, and analyzes after bulk load. Validation is assertions inside the two scripts, not a separate validator suite. Preflight: run exporter and importer against a disposable local Compose stack (PostgreSQL plus MinIO) on the workstation, start the Menos API against it, and run all parity gates.
  - Acceptance: every exported row is schema-valid and references resolve; the audit records the 60 dropped orphan chunks and one dropped orphan failed job for their two absent parents, and the 26 known duplicate relationships reduce 253 legacy rows to 227; the manifest records source revision, raw and imported table counts, vector dimensions, MinIO count/bytes/key hash, and file checksums. Imported counts are content 1,337; chunk 45,872; link 0; content_entity 227; entity 209; pipeline_job 28; llm_usage 0; tag_alias 6. `llm_pricing_snapshot:active` maps to exactly one managed PostgreSQL seed row. MinIO has 3,967 objects and 28,897,635 bytes with the expected sorted-key hash. Every non-null embedding has dimension 1,024; the 71 source chunks without embeddings remain null rather than receiving synthesized vectors; foreign keys and uniqueness constraints validate; `/health`, `/ready`, signed content/list/search, graph, and semantic-search checks pass. The source remains unchanged.
  - Failure action: the production host is never involved. Correct the scripts and rerun the complete disposable preflight.
  - Result: a fresh checksum-validated portable export and archive passed exact source/import counts, the approved 60-chunk and one-job drop audits, 26 relationship deduplications, and MinIO parity. Disposable PostgreSQL preserved 45,801 valid 1,024-dimensional vectors plus 71 source nulls. Health, readiness, signed authentication, content/list/download, graph, known-document byte parity, and three semantic ranking comparisons passed; ordered IDs and snippets matched legacy with maximum score drift of 0.0001. PostgreSQL returned exported title/type metadata where the legacy search lookup returned its known `unknown`/null fallback. A custom-format logical dump restored into a fresh disposable PostgreSQL target with exact counts, constraints, vectors, and API readiness. Focused quality checks and `just validate` passed.

- [x] **T6 - Capture rollback artifacts, then rebuild VM 112 with the empty PostgreSQL stack**
  - Depends on: T1-T5 and full source validation.
  - Action: create a fresh Onclave service-state backup; verify the legacy portable export and MinIO checksums; verify and privately record the data-restore commands for Onclave state and the Menos MinIO/PostgreSQL import; run `just plan` and summarize exact actions. After the manual gate: stop and remove only VM 112; rerun `just plan`; apply `onramp_host`; verify storage after the controlled reboot; deploy Caddy/SearXNG and restore Onclave; then deploy Menos with a clean migrated PostgreSQL schema and empty MinIO bucket. Do not restore the old empty Surreal baseline into the new stack.
  - Manual gate: obtain explicit approval of the exact destructive VM replacement plan before removing VM 112. If OpenTofu does not produce the intended clean two-disk create, revise source rather than forcing state.
  - Acceptance: fresh Onclave backup and portable Menos export are readable and checksum-clean; the plan targets only VM 112 and its declared disks, with no unrelated replacement. Root is 32 GB on `local-lvm`; `/var` and `/srv` are on `vmstorage`; Podman graphroot is under `/srv`; local-lvm remains below 75 percent; Onclave passes state/restart checks; Menos reports PostgreSQL, S3, and Ollama ready with only managed seed data and exactly one authorized principal.
  - Failure action: stop broad orchestration. Recreate the VM from reviewed source and restore Onclave state; do not import legacy data. Rollback is recreate-from-source plus data restore; no VM-level backup is created.
  - Result: the reviewed targeted plan replaced only VM 112, creating a 32 GB root disk on `local-lvm` and a 512 GB data disk on `vmstorage`; the full post-canary plan reported no remaining infrastructure changes. Verified VM host-key refresh, stable `scsi1` device identity, UUID-backed `/var` and `/srv`, VG reserve, reboot persistence, and rootless Podman graphroot all passed. SearXNG recovered, Onclave restored from its validated archive and passed an idempotent restart check, and Menos passed source-revision, HTTPS, PostgreSQL, S3, and Ollama readiness. The clean Menos stack contains no domain rows, one schema migration row, one managed pricing seed row, an existing MinIO bucket with zero objects, and exactly one authorized principal.

- [x] **T7 - Perform the single production PostgreSQL import and post-import backup**
  - Depends on: T6 and unchanged T5 inputs.
  - Action: revalidate source SHA, image digests, export checksums, schema migration revision, and importer revision. Run the managed importer once against production PostgreSQL and MinIO. Do not reboot or overlap another mutation. Run exact parity and service checks, then produce and restore-test a checksum-protected PostgreSQL logical backup and a Menos service-state backup that excludes bulk PostgreSQL and MinIO payloads; bulk artifacts stay host-local per the recovery model.
  - Acceptance: all T5 row, object, vector, constraint, API, readiness, authorization, graph, and search gates pass; Onclave, SearXNG, and Caddy remain healthy; a clean disposable restore of the post-import `pg_dump` reaches Menos readiness and exact counts.
  - Failure action: keep consumers on legacy and stop the new Menos API when import state is unsafe. Recreate PostgreSQL and MinIO only after a failure that mutated target state or left the mutation boundary unknown. A failure proven to occur before target connection needs only the targeted correction and clean-target verification. After importer success, preserve imported data and resume only the failed post-import check.
  - Result: the production importer verified the approved PostgreSQL row counts, 45,801 valid vectors plus 71 null embeddings, constraints, and exact MinIO inventory. Health, readiness, unsigned rejection, signed authentication, content/list/download, graph, known-document parity, and three semantic rankings passed. Rootless Podman now binds the authorization file explicitly and manages a resident, dimension-checked Ollama embedding model. Onclave commit `7c620a088755a3dab99741f7d8bde54bce8d85db` supplies the bounded production embedding timeout through an immutable published image. The checksum-protected production dump restored into a fresh isolated target with exact counts, vectors, constraints, extensions, and API readiness. A refreshed Menos configuration-state backup completed; Onclave, SearXNG, Caddy, and Menos remained healthy; and the final infrastructure plan reported no changes.

## Validation

1. `../onclave`: Menos tests, Ruff, dependency lock, Compose config, API image build, SQL migration idempotency, PostgreSQL integration tests, retrieval evaluation, and logical backup/restore all pass.
2. `homelab-infra`: focused Python/Ansible/OpenTofu tests, `git diff --check`, and `just validate` pass with public-safety and lint clean.
3. Legacy export: deterministic typed NDJSON, resolved references, exact deduplication audit, MinIO inventory, and checksums pass without changing source data.
4. Disposable preflight: the complete dataset imports into a clean local PostgreSQL/MinIO Compose stack and passes exact counts, vectors, constraints, API behavior, search, readiness, restart, dump, and restore.
5. Replacement plan: only VM 112 and its two disks change; explicit approval exists before destruction.
6. New host: separate `/`, `/var`, and `/srv`; Podman graphroot on `/srv`; VG and Proxmox storage thresholds pass.
7. Production: direct PostgreSQL import passes all parity gates, post-import logical restore succeeds, and final `just plan` reports no infrastructure changes.

## Archive and Resume State

Archive only after T1-T7 and all validation gates pass. Move to `.specs/archive/rebuild-onramp-host-storage-layout/plan.md` without overwriting another artifact.

Final state before archival:

- T1-T7 are complete, and the tracked/private migration implementation and production state have passed their targeted gates.
- VM 112 runs the verified two-disk layout with PostgreSQL Menos data and MinIO objects on the managed data disk.
- The legacy Menos source remains unchanged, reachable, and authoritative for rollback; consumers remain on legacy until the separate cutover plan is approved and executed.
- The production PostgreSQL backup, disposable restore evidence, API parity evidence, and refreshed configuration-state backup are retained in their private managed locations.
- The final OpenTofu plan reports zero creates, updates, replacements, or deletes.
- The one final `just validate` passed after all implementation and live work completed; this plan is ready for archival.
