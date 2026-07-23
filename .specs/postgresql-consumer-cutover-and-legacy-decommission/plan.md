---
created: 2026-07-23
updated: 2026-07-23
status: planned
completed: []
---

# Plan: Cut Over Menos Consumers and Decommission the Legacy Stack

## Objective

Move each Menos consumer from the frozen legacy SurrealDB-backed endpoint to the PostgreSQL-backed endpoint without changing signed API behavior, prove rollback safety for seven consecutive 24-hour periods, create and restore-verify the final archival backups, and decommission the legacy stack only after explicit approval of the exact live actions.

## Boundaries and Assumptions

- This document is a plan only. Creating it does not approve or execute consumer changes, ingest changes, legacy shutdown, deletion, or infrastructure mutation.
- The PostgreSQL production import and its validated MinIO inventory are the starting state. Do not reimport the legacy snapshot.
- The legacy stack remains frozen, reachable, and unchanged throughout cutover and the complete rollback soak.
- Discover consumer endpoints, signing principals, scheduled jobs, and ingest ownership from authorized configuration and private state. Keep site-specific inventory and evidence under `values/`.
- Cut over one independently rollbackable consumer at a time. Do not batch consumers merely because they share an endpoint.
- Preserve request signing, response shapes, IDs, content bytes, graph behavior, filters, pagination, and semantic ranking behavior.
- Maintain exactly one ingest writer. Do not allow legacy and PostgreSQL-backed ingest to run concurrently.
- A soak day is a complete consecutive 24-hour period after the last successful consumer or writer cutover. Any rollback or failed acceptance gate resets the seven-day clock.
- Archive data, not VMs. Recovery requires PostgreSQL, MinIO, service configuration, signing configuration, and the frozen legacy export.
- Legacy decommission requires a separately reviewed action list and explicit operator approval that names any shutdown, resource deletion, or irreversible data removal.

## Executable Tasks

- [ ] **T1 - Inventory consumers and establish the rollback matrix**
  - Action: derive every read consumer, writer, scheduled job, callback, signing principal, endpoint, owner, and restart mechanism from authorized configuration. Record the private matrix under `values/` with one rollback command and one direct health check per consumer. Identify hidden consumers by reviewing recent legacy access evidence without exposing request data.
  - Acceptance: every observed consumer maps to an owner, current endpoint, target endpoint, signing principal, validation request, and rollback action; unknown traffic blocks cutover.
  - Verify: compare the private inventory against legacy access evidence and configured services; exercise each rollback command in a non-mutating or disposable context where possible.

- [ ] **T2 - Refresh pre-cutover recovery artifacts**
  - Depends on: T1.
  - Action: verify the frozen portable legacy export and MinIO checksums; create a fresh PostgreSQL custom-format dump, PostgreSQL manifest/checksum, exact MinIO inventory, and Menos configuration-state backup. Restore PostgreSQL into a fresh disposable target and verify exact counts, vectors, constraints, extensions, and readiness.
  - Acceptance: both legacy and PostgreSQL recovery paths are readable and checksum-clean; the new backup restore requires no production credentials in argv or logs; direct rollback endpoints are documented privately.
  - Verify: checksum checks, `pg_restore --list`, clean disposable restore, exact database metrics, MinIO inventory comparison, and Menos readiness.

- [ ] **T3 - Cut over one read-only canary consumer**
  - Depends on: T2.
  - Manual gate: approve the named canary, exact configuration change, validation requests, and rollback action.
  - Action: change only the canary endpoint and restart only that consumer. Keep legacy running. Do not change ingest ownership.
  - Acceptance: unsigned requests are rejected; signed identity, content/list/download, graph, filters, pagination, and three established semantic queries retain the accepted contract; no other consumer changes.
  - Failure action: restore the canary's legacy endpoint immediately, verify its original workflow, preserve diagnostics, and stop further cutovers.

- [ ] **T4 - Cut over remaining read consumers sequentially**
  - Depends on: T3.
  - Action: repeat the canary procedure for one consumer at a time. Validate the consumer's exact user workflow before proceeding to the next consumer.
  - Acceptance: each consumer has an individually recorded pass and rollback result; PostgreSQL, MinIO, API, Onclave, SearXNG, and Caddy remain healthy after every step.
  - Failure action: roll back only the affected consumer and stop the sequence until its original workflow passes.

- [ ] **T5 - Transfer ingest ownership to PostgreSQL Menos**
  - Depends on: T4.
  - Manual gate: approve the exact writer, schedule, queue, callback, and legacy-disable actions.
  - Action: stop and verify the legacy writer before enabling the PostgreSQL-backed writer. Submit one bounded canary item, verify its content, chunks, object, job state, and retrieval behavior, then enable normal scheduling.
  - Acceptance: exactly one writer is active; the canary creates one coherent PostgreSQL/MinIO record set; retries do not duplicate content, relationships, jobs, or objects; rollback can disable the new writer and restore the frozen legacy consumer path without data loss.
  - Failure action: disable the new writer, keep consumers on the last healthy endpoint, preserve the canary state for diagnosis, and do not re-enable legacy ingest if doing so could create dual writes.

- [ ] **T6 - Complete the seven-day rollback soak**
  - Depends on: T5.
  - Action: for seven consecutive 24-hour periods, record PostgreSQL/MinIO growth, constraints, backup success, API health/readiness, signed consumer checks, known-document bytes, graph behavior, semantic queries, writer/job health, and legacy rollback reachability. Keep legacy frozen and available.
  - Acceptance: all seven daily records pass with no rollback, unresolved error, missing backup, unexpected duplicate, contract regression, or data-integrity failure. Any failure or rollback resets the clock after recovery.
  - Verify: one private evidence record per complete 24-hour period plus a final summary that identifies the exact soak start and completion instants without exposing credentials or request content.

- [ ] **T7 - Create and restore-verify the archival backup set**
  - Depends on: T6.
  - Action: verify the final frozen legacy export remains byte-identical to its approved checksum; create a fresh PostgreSQL dump, MinIO inventory/archive, and configuration-state backup; package manifests, checksums, source/image revisions, restore commands, and retention location in private storage. Restore the archival PostgreSQL dump and representative MinIO content into an isolated target.
  - Acceptance: the archival set is complete, checksum-clean, encrypted or access-restricted as appropriate, stored outside the service host, and sufficient to recover data and signed API configuration without the legacy VM.
  - Verify: independent checksum verification, `pg_restore --list`, isolated restore, exact database metrics, representative object-byte checks, and API readiness.

- [ ] **T8 - Review and execute the explicitly approved legacy decommission**
  - Depends on: T7.
  - Manual gate: present the exact legacy services/resources, stop actions, deletion actions, backup identifiers, rollback limits, and expected infrastructure plan. Obtain explicit approval that distinguishes reversible shutdown from irreversible deletion.
  - Action: execute only approved actions in the reviewed order. Stop legacy services first, verify all consumer and writer workflows against PostgreSQL, and delete legacy resources only when the approval explicitly includes deletion and the post-stop gates pass.
  - Acceptance: no consumer or writer references legacy; PostgreSQL Menos and all dependencies remain healthy; archival recovery evidence remains available; infrastructure state matches the reviewed plan; no unrelated service changes.
  - Failure action: during reversible shutdown, restore legacy service availability and affected consumers. After approved irreversible deletion, recover only from the validated archival set and stop unrelated work.

## Final Validation

1. Every consumer and writer has an explicit cutover, acceptance, and rollback record.
2. The seven-day soak contains seven consecutive complete 24-hour passes after the final cutover.
3. PostgreSQL and MinIO backups restore into an isolated target with the accepted data and API contracts.
4. The frozen legacy export and final archival package pass independent checksum verification.
5. The reviewed decommission plan contains no unrelated infrastructure action and has explicit operator approval before execution.
6. After all implementation and live work in this follow-up plan is finished, run `just plan` once and `just validate` exactly once as the final gates.
