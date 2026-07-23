---
created: 2026-07-23
updated: 2026-07-23
status: in_progress
completed:
  - T1
  - T2
  - V0
  - T3
---

# Plan: Cut Over Menos Consumers and Decommission the Legacy Stack

## Context and Planning Evidence

The completed rebuild and migration plan is archived at `.specs/archive/rebuild-onramp-host-storage-layout/plan.md`. It established the PostgreSQL-backed Menos service, imported the approved legacy snapshot directly into PostgreSQL and MinIO, passed exact data and API parity, restored a production dump into an isolated target, and ended with no OpenTofu drift. It deliberately did not change consumers, enable new ingest, stop legacy Menos, or delete legacy resources.

Read-only planning investigation established the current consumer shape:

- Pi `/yt` delegates its default, list, search, content, transcript, and ingest workflows to `~/.dotfiles/claude/commands/yt/`. Pi owns only the channel-listing client under `pi/skills/workflow/yt/`.
- Pi and Claude session-start hooks both launch the same detached backfill worker under `claude/hooks/menos-circuit/`. The worker writes through `POST /api/v1/ingest`, polls content completion, and uses per-video filesystem locks.
- The local command clients use `MENOS_API_BASE`. The backfill worker accepts `MENOS_API_BASE`, then `MENOS_BASE_URL`. Operator-only Onclave scripts use `API_BASE_URL` and are not scheduled by tracked configuration.
- No Onclave runtime service was found that consumes Menos. Onclave owns the application source and image; homelab-infra owns the deployed PostgreSQL service.
- No process, user, machine, or dotfiles private environment override currently defines the Menos endpoint or disables the backfill circuit. The active clients therefore use their embedded legacy default.
- The new deployment has one managed authorized principal, and it matches the default client public key. Read-only checks confirmed that both APIs are healthy and ready, reject unsigned content reads, and accept signed reads from that principal.
- Signed pagination returned the same visible content count from legacy and PostgreSQL. The visible job count differs by one; this is consistent with the approved orphan-job drop but must be reconciled against the T7 audit before it becomes a soak baseline.
- No local backfill, ingest, delete, reprocess, or metadata-maintenance process remained active after excluding the diagnostic process itself. This is point-in-time evidence, not proof that another host or future session hook cannot write.
- One local cache directory is currently eligible for backfill, the circuit is enabled, and the existing backfill log contains repeated timeout history. Persistent endpoint changes must therefore disable backfill first.
- The legacy repo exposes API writes, direct datastore/object-store maintenance scripts, startup writes, in-process pipeline jobs, callbacks, and a backup implementation whose current object-store assumptions require runtime verification. Repository inspection alone cannot prove single-writer ownership or a restorable final legacy archive.
- Legacy Menos is not represented by homelab OpenTofu. Decommission cannot be inferred from a homelab plan and requires a separately reviewed direct action list.

These findings replace the generic assumption that every entrypoint can be cut over independently. The local Pi, Claude, and backfill entrypoints share one endpoint configuration domain. Read behavior can be canaried per process, but the persistent workstation switch is one rollback unit.

## Objective

Move the known Menos consumer configuration domain and ingest ownership from the legacy SurrealDB-backed API to the PostgreSQL-backed API without changing signed API behavior, prove the new route for seven consecutive complete 24-hour periods, create and restore-verify final archival backups, and decommission legacy resources only after explicit approval of the exact reversible and irreversible actions.

## Scope Boundaries

### In scope

- Private inventory of every observed Menos consumer, principal, writer, callback, schedule, endpoint source, restart mechanism, and rollback action.
- Process-local read canaries against PostgreSQL Menos.
- One persistent workstation endpoint switch after approval.
- Controlled transfer of external ingest to PostgreSQL Menos after separate approval.
- Removal of embedded legacy endpoint fallbacks from the actual consumer paths after the persistent target is proven.
- Seven consecutive complete 24-hour soak periods with daily evidence.
- Final PostgreSQL, MinIO, service-configuration, and portable legacy archival evidence.
- Explicitly approved legacy shutdown and, only when separately named in that approval, deletion.

### Out of scope

- Reimporting or merging the legacy dataset into PostgreSQL.
- Schema, API, embedding, storage-topology, signing-protocol, or retrieval redesign.
- Executing the broader `~/.dotfiles/.specs/pi-yt-onclave-consumer-migration/plan.md` ownership refactor. This cutover uses the current client entrypoints. T5 supersedes only that plan's endpoint-default removal requirement and records the scoped supersession there during execution; script ownership, porting, and other work remain separate.
- General Claude cleanup, a shared Menos SDK, new monitoring infrastructure, router/firewall changes, or unrelated Onramp services.
- Changing authorized principals unless investigation proves a named consumer is missing. Any such addition requires a revised reviewed scope.
- Archiving or deleting a source repository unless the decommission approval explicitly names it as a separate action.

## Hard Safety Rules

- Creating or reviewing this plan does not authorize consumer routing, ingest, restart, shutdown, deletion, or infrastructure mutation.
- Do not modify `.env`, SSH private keys, or credential files. Use process-local environment for canaries and an approved private OS-level endpoint setting for the persistent switch.
- Do not print endpoint values, key identifiers, signatures, credentials, content bodies, or site-specific host details. Store private evidence under `values/migration-staging/menos/cutover/`.
- Do not run the importer again. Unexpected legacy drift blocks cutover and requires a revised migration decision; it does not authorize an automatic merge or second import.
- Disable the backfill circuit and prove no external writer process is active before changing the persistent endpoint.
- Maintain one data destination for external ingest. Legacy and PostgreSQL-backed ingest must never be enabled concurrently.
- Keep legacy services running and available through reader cutover only. Before the first PostgreSQL-only durable write, G2 must quiesce and stop every legacy application, worker, callback, scheduler, and direct writer while preserving the complete stack and restart procedure. The stopped legacy stack remains an isolated recovery standby throughout the soak, not a post-write consumer rollback target.
- If a safe reversible legacy stop cannot be approved and verified, G2 is blocked. A monitored but writable legacy stack is not an acceptable write fence.
- Cut over only the known workstation configuration domain. Unknown identities, unexplained routes, callbacks, direct datastore clients, or another host block the persistent switch.
- Use targeted service deployment or direct diagnostics for Menos recovery. Do not run a broad apply to repair a service-only failure.
- The first failed live mutation stops later waves. Recover only the affected consumer or Menos service and re-establish its original workflow before continuing.
- The reversible legacy application/writer stop occurs only under the approved G2 section of the private cutover packet and before the first PostgreSQL-only write. Permanent retirement and deletion occur only after the soak and archival gates under G3. Deletion requires explicit approval that names each resource and its validated recovery artifact.

## Risk and Approval Gates

- **Risk level:** high because the plan changes production consumer routing and later removes a stateful legacy service.
- **Pre-write reader rollback:** before the first PostgreSQL-only durable write, restore the explicit legacy endpoint, restart only Pi/Claude processes, and verify the original signed workflow.
- **Post-write recovery:** immediately after the first verified PostgreSQL-only durable write, record the immutable `postgresql_write_committed` phase marker. From that point, disable failed ingest and recover PostgreSQL Menos from its service or validated backups. Do not route readers or writers to stale legacy unless a new reviewed data-equivalence gate proves that legacy contains every accepted PostgreSQL write.
- **Service recovery:** use the validated PostgreSQL dump, complete MinIO archive, and Menos configuration-state backup. Do not treat service-state archives as bulk-data backups.
- **Legacy standby recovery:** before G2 commits a PostgreSQL-only write, the exact legacy stack may be restarted through its tested procedure. After the phase marker, legacy may be started only in isolation for recovery investigation unless data equivalence and consumer rollback receive explicit approval.
- **Post-deletion recovery:** recover only from the validated archival set.

Manual gates:

1. **G1 - Persistent reader cutover:** approve the private consumer matrix, process restart list, target-setting action, validation commands, and explicit legacy rollback action.
2. **G2 - Legacy write fence and writer transfer:** approve the exact legacy quiesce/stop actions, one canary input, expected PostgreSQL/MinIO mutations, the conditional automatic-ingest enable action, all eligible queued/cache inputs, and phase-specific containment/recovery actions.
3. **G3 - Legacy decommission:** after seven soak days and archival restore proof, approve credential disposition and permanent retirement separately from every exact irreversible deletion.

G1 and G2 approvals reference named sections of one private `cutover-packet.json`; G3 references one private `decommission-packet.json`. Each packet records the gate, approver, UTC timestamp, exact commands, resources, archive identifiers, and conditional actions, and is identified by its private Git commit. Execution verifies the file is byte-identical to the approved commit immediately before mutation and fails closed on any difference. One approval remains valid for its named packet section while target, scope, intended outcome, and destructive impact remain unchanged.

## Approach Decisions

| Decision | Selected approach | Rejected approach and reason |
| --- | --- | --- |
| Consumer unit | Treat Pi, Claude, and session backfill on this workstation as one persistent endpoint configuration domain | Pretend shared environment consumers can be persistently switched one at a time |
| Reader canary | Use process-local `MENOS_API_BASE` with existing signed client entrypoints | Change DNS or the persistent user environment before proving the client workflow |
| Channel client | Validate it after primary signed content/search checks | Use it as primary canary; its YouTube fallback can mask a Menos failure |
| Writer containment | Set `MENOS_CIRCUIT_DISABLED`, verify no writer process, then run one named writer canary | Allow session-start hooks to choose the target implicitly |
| Endpoint persistence | Use a private OS user-level `MENOS_API_BASE` setting inherited by newly launched Pi/Claude processes | Modify `.env`, hardcode the private PostgreSQL endpoint, or rely on an unset fallback |
| Legacy fallback | Remove embedded legacy defaults only after the new persistent endpoint passes; retain explicit legacy routing only for pre-write rollback and isolated recovery metadata after the phase marker | Execute the broader Pi client-ownership refactor as part of infrastructure cutover |
| Legacy write fence | After reader cutover, drain and stop the complete legacy writer stack before the first PostgreSQL-only write; preserve a tested restart path | Keep a writable legacy API online and rely on monitoring to detect divergence |
| Legacy during soak | Keep the complete legacy stack stopped, intact, and restartable; use existing access, firewall, process, scheduler, and client evidence to detect missed consumers | Run legacy writers or build a temporary listener/proxy solely for soak monitoring without a revised decision |
| Discovery claim | Prove no unmatched activity within a closed, bounded inventory whose authorized sources and time bounds are recorded | Claim universal absence or broaden into machine/network discovery outside known systems |
| Data drift | Require every difference to match an approved transformation or prove PostgreSQL equivalence; otherwise stop | Automatically reimport, merge, or label legacy-only records accepted |
| Approval binding | Use one privately committed cutover packet for G1/G2 and one decommission packet for G3; verify the exact Git versions before execution | Maintain separate packet/sidecar sets for every gate or apply approval to mutable notes |
| Soak evidence | Use seven exact contiguous UTC windows, lightweight daily checks, and full parity only at the start and end | Seven spaced snapshots, full daily migration parity, or a new observability platform |
| Decommission | Direct reviewed legacy action list plus an exact zero-action homelab plan | Assume homelab OpenTofu owns the unmanaged legacy stack |

## Private Cutover Packet

T1 must create `values/migration-staging/menos/cutover/consumer-matrix.json` and a companion redacted operator summary. The private matrix is the execution source of truth and must contain one record per configuration domain or independent external consumer:

- stable consumer name and owner;
- host/process and entrypoint;
- read routes and write routes used;
- endpoint variable and current source;
- signing principal fingerprint or private identifier;
- schedule, callback, and direct-datastore capability;
- restart/reload action;
- process-local canary command;
- persistent cutover action;
- exact rollback action;
- legacy access-log identity and expected traffic;
- status: confirmed, blocked, or explicitly excluded with evidence.

It must also contain the named writer owner, the legacy and PostgreSQL backup identifiers, expected orphan/deduplication transformations, and the exact soak start timestamp once established.

T1 must also create `coverage-manifest.json`. It defines the closed discovery universe: every in-scope host, principal, API replica, process manager, container, scheduler, callback, direct datastore/object-store credential, configuration root, access/audit log, retention bound, maximum trigger interval, and covered-through UTC timestamp. A source is complete only when its evidence covers the declared interval. Missing coverage blocks V0; conclusions are phrased as no unmatched activity within the covered universe.

Before G1, create `values/artifacts/menos-cutover/cutover-packet.json` with separate G1 and G2 sections and commit it with the reusable gate tools and a hash index of ignored generated evidence to the private values repository. G1 and G2 remain separate approvals, each referencing its section and the exact private Git commit; update and recommit the same packet only when later evidence changes G2 details. Before G3, create and privately commit `values/artifacts/menos-cutover/decommission-packet.json`. The phase marker also belongs under this tracked private artifact directory. Do not create redundant SHA sidecars for the packet JSON files; private Git identity and byte-for-byte verification are the approval boundary. No private values are copied into the tracked plan.

## Automation Plan

| Operation | Execution boundary | Credentials/private data | Required evidence |
| --- | --- | --- | --- |
| Consumer discovery | Closed coverage manifest spanning known homelab, Onclave, dotfiles, legacy deployment, private values, hosts, schedulers, credentials, processes, replicas, callbacks, and access/audit logs | Read locally; redact values | Every source has a time bound and covered-through timestamp; no unmatched activity within the fully covered universe |
| Drift reconciliation | Read-only legacy datastore/object inventory versus T7 audit and PostgreSQL evidence | Existing authorized local state | Every difference matches an approved transformation or proves PostgreSQL equivalence; otherwise stop |
| Cutover checker | One focused private script under the cutover evidence directory; no framework, service, listener, or new public `just` recipe | Reads private endpoints and signer path without printing them | Focused redaction, missing-evidence, and interval tests plus redacted JSON result |
| Recovery verification | Existing PostgreSQL backup helper, `scripts/service-state.sh backup menos_onramp`, portable legacy checksums, and archived T7 restore evidence | Existing service/private credentials through managed paths | Fresh dump checksum/manifest/list; reuse prior restore when inputs match; replacement restore only after material change; final full restore reserved for T7 |
| Reader canary | Existing current client scripts with process-local target and circuit disabled | Current signer and private target in process environment | Signed route results and actual Pi `/yt` read workflow |
| Persistent reader switch | Approved private OS user environment setting; restart only Pi/Claude processes | Private target value | New processes inherit target; read workflows pass; legacy log has no corresponding business traffic |
| Legacy fence and writer canary | Drain and stop the approved legacy stack, verify the fence, then run one named PostgreSQL ingest entrypoint while automatic backfill remains disabled | Current signer and one approved input | Stopped legacy state, no surviving writer surface, one coherent content/job/object result, idempotency check, and phase marker |
| Soak | Run lightweight checks for seven contiguous non-overlapping UTC windows; run full API parity at the start and end | Read-only PostgreSQL service plus existing legacy access/process/scheduler/client evidence | Seven window-complete JSON records covering at least 168 hours, with no gap or new monitoring infrastructure |
| Decommission | Direct legacy credential-retirement and resource actions from the privately committed decommission packet | Legacy service and credential management access | Shared/recovery credentials preserved, legacy-only credentials revoked, deletion only if separately approved |
| Infrastructure closeout | `just plan`, then one final `just validate` after all tracked/live work | Existing managed private values | Exactly zero OpenTofu actions and passing validation |

## Execution Checklist

Checked means the task and its verification passed. An unchecked task is pending, in progress, blocked, or invalidated.

### Wave 0 - Evidence and recovery

- [x] T1: Complete the private consumer, writer, drift, and decommission inventory
  - Status: complete
  - Evidence: the private consumer matrix and bounded coverage manifest map the workstation domain, all local principals, both API replicas, schedules, callbacks, direct maintenance surfaces, legacy resources, and recovery references. Current legacy database and MinIO aggregates exactly match the approved source boundary with no unmatched activity in the covered universe.
- [x] T2: Build the focused checker and verify recovery inputs
  - Status: complete
  - Evidence: the private checker passed six focused tests, Ruff, redaction, and full three-query parity. The targeted Podman healthcheck normalization is deployed and healthy. A fresh custom-format dump passed checksum, manifest, and catalog verification; the refreshed configuration-state archive passed its repository contract and excludes bulk data. Restore-affecting inputs are unchanged, so the validated T7 full restore remains applicable and was not duplicated.
- [x] V0: Evidence and recovery gate passes
  - Status: complete
  - Evidence: the bounded inventory has no unmatched activity or drift; both deployments have one healthy API replica; the recovery inputs and fence/status helpers pass; and the exact G1/G2 packet, reusable tools, evidence index, and configuration-state backup are committed and pushed in the private values repository.

### Wave 1 - Reader cutover

- [x] T3: Pass process-local reader canaries
  - Status: complete
  - Evidence: with the backfill circuit disabled in the child environment, the exact shared Pi/Claude list and search entrypoints, Claude YouTube-ID resolution, known-content JSON, transcript-only retrieval, and Pi-native channel listing all passed against PostgreSQL Menos. Channel listing reported Menos as its source, and the persistent user endpoint remained unset before and after.
- [ ] G1: Approve and execute the persistent reader cutover
  - Status: in progress
  - Evidence: explicit G1 approval and a passing full pre-mutation check are recorded privately. No active writer was found, and the future-process backfill circuit is persistently disabled. The endpoint switch is intentionally deferred until all active Pi/Claude processes are closed so the reader domain cannot split across inherited environments.
- [ ] V1: Reader workflows and rollback boundary pass
  - Status: pending
  - Evidence: --

### Wave 2 - Writer transfer

- [ ] G2: Approve and execute the single writer canary
  - Status: pending
  - Evidence: --
- [ ] T4: Quiesce legacy, commit the PostgreSQL writer boundary, and enable automatic ingest
  - Status: pending
  - Evidence: --
- [ ] V2: Writer integrity and single-destination gate passes
  - Status: pending
  - Evidence: --

### Wave 3 - Endpoint hardening and soak

- [ ] T5: Remove embedded legacy endpoint fallbacks from active consumer paths
  - Status: pending
  - Evidence: --
- [ ] T6: Complete seven consecutive 24-hour soak records
  - Status: pending
  - Evidence: --
- [ ] V3: Soak gate passes with seven contiguous evidence-complete windows and no legacy connection attempt or write
  - Status: pending
  - Evidence: --

### Wave 4 - Archive and decommission

- [ ] T7: Create and restore-verify the final archival set
  - Status: pending
  - Evidence: --
- [ ] G3: Review and explicitly approve legacy credential retirement and any deletion
  - Status: pending
  - Evidence: --
- [ ] T8: Execute only the approved legacy decommission actions
  - Status: pending
  - Evidence: --
- [ ] V4: Post-decommission workflows and infrastructure state pass
  - Status: pending
  - Evidence: --

### Final gates

- [ ] F1: All task and wave checks pass
  - Status: pending
  - Evidence: --
- [ ] F2: Actual Pi `/yt`, Claude client, and session-backfill workflows pass against PostgreSQL Menos
  - Status: pending
  - Evidence: --
- [ ] F3: Seven complete soak days and archival restore evidence are present
  - Status: pending
  - Evidence: --
- [ ] F4: `just plan` reports exactly zero actions and final repository validation passes
  - Status: pending
  - Evidence: --
- [ ] F5: Private evidence is complete, non-secret tracked prose is current, and the plan is archive-ready
  - Status: pending
  - Evidence: --

## Task Breakdown and Acceptance Criteria

### T1 - Complete private inventory and reconcile drift

**Read-only scope:** known local repositories and private values, current local processes, direct legacy and PostgreSQL endpoints, deployed service definitions, existing access logs, and legacy service schedules. Do not scan unrelated user data or make service changes.

Required work:

1. Create the closed `coverage-manifest.json` and enumerate every in-scope host, principal, API replica, process manager, container, Windows Task Scheduler entry, cron/systemd timer, callback, direct SurrealDB client, direct object-store client/credential, configuration root, and access/audit log.
2. For every source, record retention start, covered-through UTC timestamp, maximum configured trigger interval, collection command, and result. The evidence window must cover at least one complete maximum trigger interval for every scheduled source. Event-driven/manual surfaces require full configuration, process, credential, and available audit coverage rather than a guessed interval.
3. Reconcile every configured endpoint reference with observed request identities, methods, and routes within that covered universe. Map the approved new principal to exact executable/module paths, source revisions, parent/child processes, and restart behavior.
4. Confirm the actual API replica count and all in-process pending/running jobs. Inventory every callback retry and direct maintenance entrypoint.
5. Compare current legacy record and complete object inventories with the approved T7 source audit. Reconcile the one-job API visibility difference against the approved orphan-job drop. Every difference must match an approved transformation or prove byte/record equivalence in PostgreSQL. Any other drift blocks cutover and does not authorize acceptance, abandonment, merge, or a second import.
6. Inventory the exact legacy Compose project, API, datastore, object store, models, authorized-key file, callback configuration, backup cron, data directories, DNS records, credentials, and source revision. Determine whether the deployed object store is MinIO-compatible Garage or another implementation and name its tested recovery method.
7. Record the restart and rollback action for the workstation configuration domain and every other confirmed consumer. Record how legacy connection attempts will remain observable after its writer stack stops.

Acceptance:

- The coverage manifest is closed, time-bounded, and complete for every declared source.
- The private matrix has no unmatched activity within the fully covered universe.
- Current legacy data matches the approved migration boundary except transformations or records proven equivalent in PostgreSQL.
- Legacy shutdown and deletion resources are named separately, including every credential and connection-evidence source.
- If access/audit logs, process/replica inventory, credential ownership, maximum trigger intervals, or direct runtime inventory are unavailable or insufficiently retained, T1 is blocked rather than inferred from source code.

### T2 - Build the focused checker and verify recovery inputs

Required work:

1. Create one small private `values/artifacts/menos-cutover/check-cutover.py` and keep its generated outputs under ignored `values/migration-staging/menos/cutover/`. It accepts optional UTC window boundaries and a `--full` boundary-check flag, reads endpoint and signer locations from private configuration, and never prints endpoint values, signatures, key identifiers, or response bodies. Do not add plugins, a service, a listener/proxy, or a public `just` recipe.
2. Every invocation records health/readiness, unsigned rejection, one signed representative content read, job/backup state, PostgreSQL constraint/duplicate summary, database row-growth summary, MinIO key-count/total-bytes/keyset-hash summary, expected legacy phase/process state, and coverage from existing access/firewall/scheduler/client evidence.
3. `--full` additionally runs the accepted known-document, graph, filter/pagination, and three-semantic-query parity suite. Run it at the soak start and end, not daily.
4. Window validation derives seven exact contiguous non-overlapping `[start, end)` UTC intervals, rejects clock regression, overlaps, gaps, missing source coverage, and late collection beyond the cutover-packet tolerance, and requires the final boundary to be at least 168 hours after start.
5. Add focused local tests only for redaction, missing-evidence failure, result shape, and interval calculations.
6. Verify the frozen portable legacy export, complete object checksums, and the currently deployed legacy object-store recovery method. Stale MinIO-only instructions do not satisfy a Garage deployment.
7. Compare current source/image/schema/backup-helper revisions and backup format with the archived successful T7 production restore evidence. If they are unchanged, reuse that isolated restore result and verify a fresh pre-cutover dump with checksum, manifest, and `pg_restore --list`; do not repeat the full restore. If any material input changed, run one full pre-cutover restore.
8. Reserve the mandatory complete PostgreSQL/MinIO archive restore and independent private Git provenance for T7 after the soak.

Acceptance:

- Focused checker tests and one redacted `--full` preflight pass.
- Portable legacy recovery inputs are checksum-clean and match the deployed storage implementation.
- Existing T7 restore evidence is demonstrably applicable, or one replacement pre-cutover restore passes because a material input changed.
- No checker framework, temporary monitoring service, or duplicate full restore is introduced.

### V0 - Evidence and recovery gate

Blocked by T1 and T2.

Pass only when:

- the closed coverage manifest has no missing source or coverage gap and contains no unmatched activity within its declared universe;
- no unexplained legacy drift exists;
- both endpoint and principal mappings are bound to exact executable revisions and process owners;
- automatic backfill and every other external/direct writer can be disabled and the legacy stack can be reversibly stopped before the first PostgreSQL write;
- recovery artifacts and phase-specific rollback actions are current;
- the G1 and G2 sections of `values/artifacts/menos-cutover/cutover-packet.json` can be privately committed and verified byte-for-byte without exposing values.

### T3 - Process-local reader canaries

Run with `MENOS_CIRCUIT_DISABLED=1` and a process-local PostgreSQL target. Do not change user or machine environment.

Required checks:

1. Unsigned content request is rejected.
2. Signed identity, content list, known content metadata and bytes, graph, filters, pagination, and the three established semantic queries pass.
3. Current Claude-owned `/yt` list, search, content, and transcript scripts pass against the process-local target.
4. Pi `/yt` read workflows pass through their current command paths.
5. Pi-native channel listing is checked only after the primary checks and must report Menos as its source; fallback does not count as success.
6. Legacy remains healthy and receives no mutation.

Acceptance:

- Actual current client entrypoints pass without source edits, fallback, or persistent routing changes.
- Any route or response mismatch stops before G1.

### G1 and V1 - Persistent reader cutover

The G1 section of the privately committed `values/artifacts/menos-cutover/cutover-packet.json` must name:

- the private user-level target-setting action;
- the exact executable/module paths, revisions, parent processes, and Pi/Claude processes that must be restarted to inherit it;
- the backfill-disable action performed first;
- redacted inherited-variable evidence and PostgreSQL/legacy request-correlation evidence for every workflow;
- the exact read workflow checks;
- the explicit legacy endpoint rollback action;
- the exact private Git commit used for approval.

Execution order:

1. Set the user-level backfill circuit disabled flag.
2. Close or wait for only the known Pi/Claude/backfill processes; verify no backfill or maintenance writer remains.
3. Set the user-level Menos endpoint to PostgreSQL without printing it.
4. Start fresh Pi and Claude processes so they inherit the setting. Do not restart unrelated services.
5. Run the T3 read workflows through those fresh processes.
6. Confirm legacy logs show no corresponding business traffic from the switched domain.

Rollback:

- Restore the explicit legacy endpoint, keep backfill disabled, restart only the affected client processes, and verify the original read workflow.

Acceptance:

- Every read workflow uses PostgreSQL Menos.
- Legacy receives only named diagnostic probes.
- No writer has been enabled and no unrelated local or homelab configuration changed.

### G2, T4, and V2 - Fence legacy and transfer writer ownership

The G2 section of the privately committed `values/artifacts/menos-cutover/cutover-packet.json` must name the exact legacy quiesce/stop actions, every process/replica/job/schedule/callback/direct credential covered by the fence, one canary input, expected database/object/job effects, idempotency request, conditional automatic-ingest enable action, eligible queued/cache inputs, existing connection-evidence sources, phase marker action, and pre-write/post-write recovery commands. Its exact private Git commit is part of approval.

Preconditions:

- V1 passed and `values/artifacts/menos-cutover/cutover-packet.json` is byte-identical to the approved private Git commit immediately before execution.
- Backfill circuit remains disabled.
- The coverage manifest accounts for all backfill, manual ingest, delete, reprocess, metadata-maintenance, API replica, direct datastore/object-store, scheduler, callback, and retry surfaces.
- Legacy and PostgreSQL pending/in-progress jobs are understood and stable.
- The legacy restart procedure is proven by the T2 disposable restore/read drill or equivalent current evidence. Do not restart production merely to test it before quiescence.

Execution order:

1. Drain or explicitly disposition every legacy in-flight job and callback retry. Disable all external/direct legacy writer triggers and credentials named by the G2 packet.
2. Reconcile final legacy database/object state with the accepted boundary and record the pre-write recovery marker.
3. Stop the complete legacy application/writer stack through the approved reversible command. Preserve its source, configuration, datastore, object storage, and restart artifacts. Use only existing approved access, firewall, process, scheduler, and client evidence; do not introduce a temporary listener/proxy without revising the plan and obtaining approval.
4. Verify all legacy application/worker containers and processes are stopped, restart policy cannot reactivate them, network write routes are unavailable, direct writer credentials/triggers are disabled, and the final stopped-state manifests remain unchanged. An approved negative probe must fail at the stopped network boundary or a dedicated non-mutating deny/log listener before application parsing and must not change state.
5. Run exactly one current ingest entrypoint in one process against PostgreSQL Menos.
6. Verify one coherent content, job, chunk, relationship, and object result, or an idempotent existing-content response. Immediately after the first PostgreSQL-only durable write, record and hash the `postgresql_write_committed` marker.
7. Repeat only the approved idempotency request and prove no duplicate content, relationship, job, or object was created.
8. If the packet condition is satisfied, remove the user-level circuit-disable flag, restart fresh Pi/Claude processes, and verify their detached backfill inherits the PostgreSQL target. This conditional enable is part of G2, not an implicit follow-on approval.
9. Confirm every eligible local cache item is either safely processed once or remains deliberately held with a documented reason.

Failure action:

- Before `postgresql_write_committed`: keep automatic ingest disabled, restart legacy only through the tested procedure if reader rollback is required, restore the explicit legacy endpoint, and verify the original workflow.
- After `postgresql_write_committed`: keep legacy stopped, disable new automatic ingest, preserve the canary state, and recover PostgreSQL Menos. Do not route readers or writers to legacy unless a separately approved data-equivalence gate proves it current.

Acceptance:

- The legacy writer stack is stopped and cannot restart automatically.
- All external ingest resolves to PostgreSQL Menos within the fully covered universe.
- No legacy write or connection attempt occurred after the fence except approved negative probes.
- No duplicate or stranded canary state exists.
- The phase marker and conditional automatic-ingest action match the approved G2 section and private Git commit.
- The session-start backfill path is observed against the new target without relying on a hardcoded default.

### T5 - Remove embedded legacy endpoint fallbacks

After V2, update only the active endpoint-resolution paths and their tests in the dotfiles repository:

- `claude/commands/yt/api_config.py`;
- `pi/skills/workflow/yt/api_config.py`;
- `claude/hooks/menos-circuit/lib.py`;
- focused tests that own missing-variable and precedence behavior.

Required behavior:

- `MENOS_API_BASE` is required for current clients.
- The backfill worker does not fall back to an embedded legacy endpoint. Retain `MENOS_BASE_URL` only if current compatibility evidence requires it; otherwise remove the duplicate knob.
- Missing configuration fails explicitly for interactive commands and safely skips backfill without writing a misleading availability status.
- Private endpoint values remain outside tracked source.
- The broader Pi script-ownership plan remains separate. T5 records that it supersedes only the endpoint-default requirement in `~/.dotfiles/.specs/pi-yt-onclave-consumer-migration/plan.md` so later execution does not repeat this work.

Verification:

- Focused Python tests and Ruff pass for the changed client paths.
- Pi prompt/extension tests pass where endpoint behavior crosses the session hook.
- A source scan finds no legacy endpoint literal in active consumer code.
- Explicit legacy routing remains valid only before `postgresql_write_committed`. After the phase marker, the legacy endpoint is retained as isolated recovery metadata and is not an executable consumer rollback target without a separately approved data-equivalence gate.

### T6 and V3 - Seven-day rollback soak

The soak starts only after V2 and T5 pass. Record a trusted UTC `start`, seven exact contiguous non-overlapping `[start + n*24h, start + (n+1)*24h)` windows, approved maximum collection lag, and existing evidence-source coverage requirements in `soak-state.json` under the private evidence directory.

Boundary checks:

1. At the soak start, run `values/artifacts/menos-cutover/check-cutover.py --full` and record actual Pi `/yt`, Claude read, known-document, graph, filter/pagination, and three-semantic-query parity.
2. After the seventh window, run the same full suite before V3 passes.

For each daily window:

1. Run the lightweight checker after the window closes and within the approved collection lag. It must prove each existing log, backup, job, process, scheduler, client, and connection-evidence source covers the complete window.
2. Verify PostgreSQL/MinIO health and readiness, one attributed signed representative read, job/backup state, constraints/duplicates, row growth, and MinIO key-count/total-bytes/keyset hash.
3. Verify automatic backfill has no duplicate or stranded jobs.
4. Verify the complete legacy writer stack remained stopped and could not auto-restart. Existing evidence must show no unplanned attempt to reach legacy.
5. Verify the explicit pre-write legacy recovery artifacts remain intact without starting legacy or treating it as a post-write reader target.

Do not rerun full semantic, graph, known-document, or complete object-digest parity every day. Do not build new monitoring infrastructure for the soak. If existing evidence cannot cover a window, reset and stop for a revised decision.

Reset the seven-day clock after any rollback, missing/late record, clock regression, overlap, coverage gap, legacy process restart, unexpected legacy connection attempt/write, failed backup, unresolved consumer error, duplicate, contract regression, or integrity failure.

Acceptance:

- Seven lightweight records cover seven exact contiguous complete windows after the final writer cutover, with the final boundary at least 168 hours after the trusted start.
- Full boundary suites pass at the start and end.
- Every existing evidence source attests its complete assigned window; snapshots without continuous coverage do not pass.
- No record relies on channel fallback or a legacy response to claim PostgreSQL success.
- Legacy remains stopped, unchanged, intact, and restartable through the entire soak.

### T7 - Create and restore-verify the archival set

After V3:

1. Verify the final legacy datastore/object inventory remains at the accepted frozen boundary. If it changed unexpectedly, stop and revise the migration decision.
2. Verify the portable legacy export remains byte-identical to its approved checksums. Because legacy was stopped before new writes, a changed boundary is a failure, not permission to create an unreviewed replacement export.
3. Create a fresh PostgreSQL custom-format dump, checksum, manifest, complete MinIO inventory/archive, and Menos configuration-state backup.
4. Archive legacy deployment configuration, authorized public keys, source revision, backup schedule, and the actually deployed object-store data in a format with a verified restore/read procedure.
5. Store bulk archival copies outside the service host with appropriate private access controls. Independently compute all manifests on the authorized workstation and commit/push their digests, source revisions, restore evidence, and storage identifiers to the private values repository.
6. Restore the complete PostgreSQL database and complete MinIO archive into an isolated target. Compare every expected database metric and every object key, size, required metadata field, version where applicable, and content digest before verifying signed API behavior and readiness.
7. Restore/read-verify the complete legacy archive independently enough to prove it does not depend on the legacy host remaining intact.
8. Verify private Git provenance and all archive digests again immediately before G3.

Acceptance:

- The final archival package is checksum-clean, off-host, and sufficient for both PostgreSQL recovery and legacy historical recovery.
- Complete database and object manifests match their isolated restored targets; representative sampling is insufficient.
- Every archive has independently computed immutable private Git evidence, source/image revisions, retention location, and redacted restore procedure.

### G3, T8, and V4 - Legacy decommission

The privately committed `values/artifacts/menos-cutover/decommission-packet.json` must present three lists:

1. **Reversible stopped state:** every API, datastore, object store, model service, backup cron/timer, callback, and runtime process already stopped by G2, with proof it stayed stopped and its tested restart command.
2. **Credential disposition:** classify every credential as legacy-only, shared, rotatable, or recovery-critical. Name external revocation/rotation for legacy-only credentials, preservation checks for shared credentials, and protected escrow or tested replacement for recovery-critical material.
3. **Irreversible deletion:** containers, volumes/data directories, DNS records, credentials, host files, or repository/archive actions proposed for removal.

It must identify the independently verified archive that recovers each deleted stateful item, state which legacy resources are unmanaged by homelab OpenTofu, and name its exact private Git commit. Approval names reversible retirement separately from every irreversible deletion.

Execution order:

1. Verify `values/artifacts/menos-cutover/decommission-packet.json` is byte-identical to its approved private Git commit, then verify archival manifests, private Git provenance, and seven-window soak evidence.
2. Verify all Pi, Claude, backfill, signed API, search, graph, backup, Onclave, SearXNG, Caddy, and Menos workflows against PostgreSQL while legacy remains stopped.
3. Confirm no configured consumer, executable source path, private endpoint setting, callback, DNS record, credential, or schedule still references legacy.
4. If validation fails, keep deletion blocked and recover PostgreSQL Menos. Do not restart or repoint to stale legacy unless a separately approved data-equivalence gate passes.
5. Execute credential revocation/rotation and deletion only when G3 explicitly includes each exact action and all pre-deletion validation passed.
6. Run the final checker and a homelab `just plan` whose expected action set is exactly zero. Retain the machine-readable plan summary, exit result, and hash in the final evidence manifest.

Acceptance:

- No consumer or writer references legacy within the closed covered inventory.
- PostgreSQL Menos and neighboring services remain healthy.
- Shared/recovery credentials remain usable, legacy-only credentials are revoked, and only explicitly approved resources are deleted.
- Complete archival evidence remains readable, immutable, and off-host.
- Homelab OpenTofu reports exactly zero actions.

## Dependency Graph

```text
T1 + T2 -> V0
V0 -> T3 -> G1 -> V1
V1 -> G2 -> T4 -> V2
V2 -> T5 -> T6 -> V3
V3 -> T7 -> G3 -> T8 -> V4
V4 -> F1 -> F2 -> F3 -> F4 -> F5
```

No live cutover task can run in parallel with another live mutation. Read-only inventory and local checker implementation may run in parallel only when they do not inspect or write the same evidence artifact.

## Validation Contract

### Behavior preservation

The following are the accepted external contracts:

- unsigned protected requests are rejected;
- the current signed principal is accepted;
- content list, lookup, metadata, bytes, filters, and pagination retain behavior;
- graph behavior retains the accepted nodes, edges, and traversal result;
- known-document bytes match;
- the three established semantic queries retain accepted result ordering and score tolerance;
- ingest produces coherent content, chunks, relationships, job state, and object storage;
- retry/idempotency does not duplicate durable state;
- Pi `/yt`, Claude client scripts, and session-start backfill use PostgreSQL without fallback.

### Validation discipline

- Run only the owning focused checks while implementing or executing a wave.
- One failed live mutation stops later waves and starts targeted recovery.
- Do not rerun the importer, broaden into schema work, or change neighboring services to make a cutover check pass.
- After all tracked and live work is complete, run `make check` in dotfiles if T5 changed dotfiles, run `just plan` once in homelab and require exactly zero actions, then run `just validate` exactly once as the final homelab repository gate.
- Create a final private evidence manifest mapping every T1-T8, V0-V4, G1-G3, and F1-F5 item to timestamped artifact hashes, approval packet private Git commits, source revisions, and validation results.

## Success Criteria

1. The closed coverage manifest maps every in-scope host, principal, route, writer, callback, replica, credential, and schedule, and contains no unmatched activity or coverage gap.
2. Current legacy state contains no unexplained drift from the approved migration boundary; every difference matches an approved transformation or proves PostgreSQL equivalence.
3. Process-local canaries and the actual persistent Pi/Claude workflows use PostgreSQL Menos with exact executable revision, inherited-setting, and request-attribution evidence.
4. The complete legacy writer stack is reversibly stopped before the first PostgreSQL-only durable write, and the immutable phase marker separates pre-write rollback from post-write PostgreSQL recovery.
5. Exactly one external ingest destination is enabled, and the canary is coherent and idempotent under the approved G2 section of `values/artifacts/menos-cutover/cutover-packet.json`.
6. Active consumer code contains no embedded legacy endpoint fallback before decommission.
7. Seven contiguous complete 24-hour windows, covering at least 168 hours with continuous evidence and no gap, pass after the final writer cutover.
8. Complete PostgreSQL, MinIO, configuration, and portable legacy archives pass independent manifest, provenance, and full restore/read verification.
9. Credential retirement and legacy deletion occur only through the exact approved lists in the privately committed `values/artifacts/menos-cutover/decommission-packet.json`.
10. Final consumer workflows pass with legacy stopped or deleted as approved, and homelab `just plan` reports exactly zero actions.
11. Final dotfiles and homelab validation gates pass, every checklist item maps to immutable private evidence, private values stay private, and the plan can be archived.

## Archive Rule

Archive to `.specs/archive/postgresql-consumer-cutover-and-legacy-decommission/plan.md` only after T1-T8, V0-V4, G1-G3, and F1-F5 pass. Do not overwrite an existing archive.

## Execution Status

- **State:** in progress
- **Completed work:** T1 bounded inventory; T2 focused checker, full preflight, healthcheck repair, fresh dump, configuration-state backup, and recovery-input verification; V0; T3 exact process-local reader canaries; and the approved G1 pre-mutation check and future-process backfill disable action
- **Confirmed:** one workstation consumer domain; all legacy principals are local; one healthy API replica per deployment; no writer scheduler, active maintenance writer, callback, unmatched activity, or unexpected legacy data/object drift; live legacy storage is MinIO; current restore-affecting inputs match the successful T7 restore; exact Pi/Claude read entrypoints pass against PostgreSQL without fallback or persistent routing
- **Current blockers:** active Pi/Claude processes must be closed before the approved persistent endpoint switch; this running Pi process cannot inherit a Windows user-environment update
- **Next ready task:** follow the private G1 process-boundary handoff, launch a fresh Pi process, resume this plan, and run V1
- **No action authorized:** G2, ingest, source edits, legacy service shutdown, deletion, plan/apply, or decommission
- **Resume command after review:** `/do-it .specs/postgresql-consumer-cutover-and-legacy-decommission/plan.md`
