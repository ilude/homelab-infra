---
created: 2026-08-10
status: completed
completed: 2026-08-11
---

# Plan: Move Site Configuration to BWS and OpenTofu State to SeaweedFS

## Outcome

Complete one coordinated `homelab-infra` migration with two sequential implementation phases:

1. Deploy SeaweedFS and migrate encrypted, versioned, locked OpenTofu state.
2. Make Bitwarden Secrets Manager (BWS) authoritative for site-specific configuration currently read from `values/`.

The plan remains active across both phases and is archived only after affected services and the final repository gate pass.

## Confirmed Decisions

- This work belongs to `homelab-infra` and must not modify or depend on `onramp-vNext`.
- BWS may hold credentials and non-secret private site configuration.
- Storage remains self-hosted. Do not add paid storage or hosted infrastructure.
- SeaweedFS is the selected OpenTofu S3 backend candidate, subject to deployed-environment verification.
- The private `values/` repository may remain for excluded backup and artifact data, but it must stop being authoritative for migrated configuration and OpenTofu state.
- Preserve exact current values during migration. Credential rotation is separate work.
- Verify affected services only. Do not turn this into a full homelab acceptance run.
- Use existing file formats and validators as authoritative. Do not add a duplicate configuration type system.

## Out of Scope

- `onramp-vNext` changes or dependencies.
- VM/LXC backup design.
- Moving service-state archives, database dumps, OCI artifacts, live object-storage data, or mutable Hermes `.hermes` state.
- Replacing, resizing, creating, or destroying a VM/LXC solely for SeaweedFS.
- Router or firewall redesign.
- Replacing Menos object storage.
- Generalizing temporary Onclave, Menos, or SearXNG roles.
- A multi-provider secret abstraction.
- Pushing commits or private values changes unless separately requested.

## Safety and Execution Rules

- Keep tracked files public-safe and generic. Never record real endpoints, addresses, DNS inventory, credentials, tokens, state contents, or BWS values in this plan or evidence.
- `BITWARDEN_ACCESS_KEY` remains a controller bootstrap credential and must not be copied to managed hosts.
- Resolve and validate only the BWS values required by the current command or phase. Do not make targeted operations depend on unrelated optional keys.
- Use a small routing manifest from BWS keys to existing configuration fields. Existing OpenTofu, Ansible, settings, env, and DNS validators remain authoritative for types and behavior.
- Prefer rendering a temporary compatibility workspace over rewriting every consumer to call BWS independently.
- Do not remove a value from `values/` until its BWS value has been read back and its consumer has passed a focused check.
- Before state migration, capture state lineage, serial, resource count, and an independent encrypted recovery copy without exposing state contents.
- Do not use `force-unlock` unless a lock is proven stale and no process owns it.
- If live work mutates state, degrades a service, or leaves the boundary unknown, stop broad rollout and recover only the affected boundary before continuing.
- Use focused checks between phases. Run `just validate` exactly once after both implementation phases and live work are otherwise complete.
- Creating this checklist does not itself authorize live deployment or state migration. Live execution requires the explicit bounded `/goal` or equivalent user instruction.

## Existing Compatibility Evidence

An isolated local spike used SeaweedFS `4.41` with image index digest `sha256:43b768cd62b00d132439cda881b93fd1adebf1b315e996e794087743821d771d` and OpenTofu `1.12.3`.

Verified locally:

- S3 bucket creation and basic object operations.
- Bucket versioning and recovery of an older object version.
- Conditional `If-None-Match` rejection.
- OpenTofu S3 backend initialization with `use_lockfile = true`.
- Actual two-client lock contention rejection.
- OpenTofu state encryption at rest.
- Two retained state revisions.
- State readability and no-change plan after SeaweedFS restart.
- Clean lock removal after OpenTofu completion.

Observed lifecycle concern:

- Four test lock operations produced four historical `.tflock` object versions and four delete markers. Production lifecycle rules must expire lock history sooner than state history.

The local spike proves compatibility, not production placement, access policy, durability, or deployed-host behavior.

## Durable Checklist

Checked means the item passed its verification. Unchecked means pending, running, blocked, or invalidated. Update `Status` and `Evidence` immediately after each item is resolved.

### Phase 0: Resolve Decisions and Establish the Baseline

- [x] P0.1: Inventory in-scope configuration and consumers
  - Status: passed
  - Evidence: Sanitized family, consumer, and exclusion map recorded in `inventory.md`.
  - Verify: Produce a sanitized map of key names, existing file fields, and consumers for `.env`, tfvars, private inventory, DNS JSON, settings, and backend configuration. Explicitly exclude backup, artifact, dump, and mutable runtime-state data.

- [x] P0.2: Decide the BWS project, key naming, and bootstrap convention
  - Status: passed
  - Evidence: The established deployment project is reused; canonical `HOMELAB_` family keys and the ignored locator-only settings contract are recorded in `inventory.md`.
  - Verify: Record whether one existing project or another established project is authoritative, canonical key naming, how small structured values are represented, and the minimal ignored local locator settings. No site values appear in tracked files.

- [x] P0.3: Decide SeaweedFS placement and persistence
  - Status: passed
  - Evidence: Existing `onramp_host`, persistent `/srv`, rootless Podman, and shared Caddy placement selected with no infrastructure resource change.
  - Verify: Select an existing suitable managed host and persistent storage using current repository contracts. Document bootstrap and recovery ordering. If a new/replaced/resized guest or network redesign is required, mark blocked and stop scope expansion.

- [x] G0: Baseline gate
  - Status: passed
  - Evidence: Scope map, BWS convention, host placement, private working-tree state, and recovery order are explicit; no placement decision requires scope expansion.
  - Verify: The scope map is complete, BWS conventions and SeaweedFS placement are explicit, current Git/private state is understood, and no unresolved decision would force implementation rework.

### Phase 1: SeaweedFS and OpenTofu State

- [x] P1.1: Add the pinned SeaweedFS infrastructure service
  - Status: passed
  - Evidence: Digest-pinned SeaweedFS 4.41 rootless service, persistent `/srv` data, shared Caddy route, service registry entry, and managed OCI update target implemented.
  - Verify: Implementation follows existing service registry, Ansible, direct-access, persistent-storage, update-pin, and service-health patterns. It uses an immutable maintained version/digest and adds no public Just recipe.

- [x] P1.2: Add narrow BWS-backed SeaweedFS and state configuration
  - Status: passed
  - Evidence: BWS has the three new SeaweedFS/state runtime keys; runtime profiles resolve only command-required keys, and the controller token is not rendered or copied to the host.
  - Verify: Only SeaweedFS credentials, backend settings, and encryption material required by this phase are resolved. Runtime credentials are protected with `no_log`; `BITWARDEN_ACCESS_KEY` is absent from managed-host files and processes.

- [x] P1.3: Configure and locally verify the state bucket lifecycle
  - Status: passed
  - Evidence: Dedicated bucket versioning, 90-day state history, 1-day lock history, delete-marker cleanup, old-version retrieval, and conditional-write rejection passed.
  - Verify: The pinned SeaweedFS release idempotently creates a dedicated versioned bucket. A focused local test proves state versions are retained and noncurrent `.tflock` versions/delete markers are eligible for shorter lifecycle cleanup.

- [x] P1.4: Deploy and verify SeaweedFS
  - Status: passed
  - Evidence: Targeted deployment completed with no infrastructure resource apply; direct HTTPS/S3, restart persistence, version retrieval, conditional rejection, and lifecycle checks passed after bounded startup recovery.
  - Verify: Targeted deployment changes no infrastructure resources or unrelated services. Direct readiness, bounded logs, S3 operations, versioning, old-version retrieval, conditional write rejection, restart persistence, and lifecycle configuration pass.

- [x] P1.5: Capture the state recovery and encryption boundary
  - Status: passed
  - Evidence: Sanitized lineage, serial, and resource-count metadata captured; DPAPI-encrypted independent state and key copies passed readback; the remote object exposes only the OpenTofu encryption envelope and ciphertext.
  - Verify: Record sanitized lineage/serial/resource-count metadata, checksum an independent encrypted recovery copy outside SeaweedFS, configure state/plan encryption from BWS, and retain an encrypted offline key recovery copy.

- [x] P1.6: Migrate OpenTofu state
  - Status: passed with recovered deviation
  - Evidence: The one reviewed `init -migrate-state` did not preserve metadata, so the verified unedited source copy was immediately pushed through the encrypted backend. Lineage and 12 resources are exact; serial advanced monotonically from 129 to 130. Two-client lock contention passed.
  - Verify: The backend uses the dedicated bucket and `use_lockfile = true`; a two-client check proves lock contention; the reviewed `tofu init -migrate-state` runs once without unrelated import, state surgery, or infrastructure apply.

- [x] G1: State migration gate
  - Status: passed
  - Evidence: Exact lineage/resources, expected monotonic serial, encrypted two-version state, absent current lock, historical lock versions/delete markers, restart persistence, no-drift plan, and both independent recovery readbacks passed.
  - Verify: Lineage, serial, and resource count are preserved; state is encrypted; versions exist; locks clean up; SeaweedFS restart persistence passes; a no-drift plan passes; independent recovery copies remain readable. Do not begin Phase 2 until this gate passes.

### Phase 2: BWS Site-Configuration Conversion

- [x] P2.1: Add the BWS routing manifest and snapshot resolver
  - Status: passed
  - Evidence: `config/bws-routing.json` and `scripts/bws-snapshot.py` route five canonical families plus scoped runtime keys; focused failure, redaction, encoding, and conflict tests pass.
  - Verify: The manifest maps canonical BWS keys to existing configuration fields and consumers without duplicating existing type schemas. Resolution fails closed on missing, empty, malformed, duplicate, or placeholder required values and never prints values.

- [x] P2.2: Render a temporary compatibility workspace
  - Status: passed
  - Evidence: `scripts/run-infra-container.py` renders mode-restricted compatibility files below container `/tmp`, exports existing path variables, and removes the container/workspace after success or failure.
  - Verify: Existing workflows consume permission-restricted generated `.env`, tfvars, inventory, DNS, settings, and backend files as needed. Reuse `VALUES_DIR` and current parsers/validators where possible; change hard-coded consumers only when required. Temporary files are removed after use.

- [x] P2.3: Seed and compare BWS values safely
  - Status: passed
  - Evidence: Five source families were seeded without overwriting conflicts, deterministic inventory compression fit the BWS limit, and redacted equality verification passed before source removal.
  - Verify: Recover current values from authorized local sources, create only missing BWS entries, report redacted equality, refuse conflicts, and leave current `values/` entries intact until consumer cutover.

- [x] P2.4: Cut over configuration file families sequentially
  - Status: passed
  - Evidence: Environment, settings, tfvars, inventory, and DNS consumers now use the temporary snapshot. BWS-rendered settings, DNS, inventory, Ansible syntax, and no-drift OpenTofu planning passed.
  - Verify: Cut over one bounded family at a time, such as environment, settings, tfvars, inventory, and DNS. For each family, render from BWS, run the focused existing validator/plan, verify affected consumers, and preserve rollback before proceeding.

- [x] P2.5: Verify Hermes and other affected services
  - Status: passed
  - Evidence: BWS-rendered Technitium and SeaweedFS targeted applies passed. Hermes direct access, gateway, dashboard, and login endpoint passed without mutation; exact family equivalence preserved its existing runtime configuration and excluded mutable state.
  - Verify: Derive the affected service list from the routing manifest. Each affected enabled service passes its declared readiness check and one role-appropriate functional operation. If Hermes is affected, verify direct access, gateway, authenticated dashboard, retained `.hermes` state, and one configured integration. Do not deep-test unaffected services.

- [x] P2.6: Remove obsolete migrated values wiring
  - Status: passed
  - Evidence: Migrated private files, old bootstrap/migration generators, duplicate Onclave resolution, and public scaffold configuration sources were removed. `scripts/values.sh check` confirms only excluded data remains.
  - Verify: Remove migrated entries, generators, parser allowlists, scaffold examples, and duplicate documentation only after all corresponding consumers pass. Excluded backup, artifact, dump, and mutable runtime-state data remains unchanged.

- [x] G2: BWS conversion gate
  - Status: passed
  - Evidence: BWS renders every required family for plan/apply/update/validation and service workflows; obsolete sources are rejected and absent; live targeted consumers remain healthy.
  - Verify: BWS is authoritative for every in-scope mapped value, existing commands work from the temporary workspace, old configuration sources are no longer consumed, and affected services are healthy.

### Phase 3: Final Validation and Closeout

- [x] P3.1: Update focused tests and public documentation
  - Status: passed
  - Evidence: Focused tests cover routing, cleanup, redaction, metadata fingerprints, locking/lifecycle, and obsolete-source rejection. The README and BWS/SeaweedFS runbook document bootstrap and recovery with public-safe fixtures.
  - Verify: Tests cover routing, redaction, temporary workspace cleanup, SeaweedFS lifecycle/locking, and obsolete-source rejection. Documentation describes BWS, SeaweedFS state, recovery, and the remaining `values/` boundary using public-safe examples.

- [x] F1: Task-specific acceptance complete
  - Status: passed
  - Evidence: Both migration gates pass; no live blocker remains; `onramp-vNext`, credential values, and excluded private data were not changed.
  - Verify: Every phase item and gate passes, no live blocker remains, and declared exclusions are unchanged.

- [x] F2: Final repository validation complete
  - Status: passed
  - Evidence: The final complete `just validate` run passed public safety, OpenTofu, TFLint, ShellCheck, 332 Python tests, DNS validation, Ansible syntax, ansible-lint, BWS rendering, and excluded-data checks.
  - Verify: Run `just validate` exactly once after both phases and live work are otherwise complete; it exits successfully.

- [x] F3: Public-safety, recovery, and diff review complete
  - Status: passed
  - Evidence: `git diff --check`, changed-file ASCII punctuation, tracked public-safety checks, secret scanning, and final validation passed. Independent encrypted state and key recovery readbacks remain available.
  - Verify: `git diff --check`, tracked public-safety checks, and secret scanning pass. Independent encrypted state/key recovery copies remain available. Tracked changes and evidence contain no private values or endpoints.

- [x] F4: Plan complete and ready to archive
  - Status: passed
  - Evidence: All final success criteria pass; the remaining working tree consists of in-scope public changes and uncommitted private-source deletions, with no push performed.
  - Verify: The final success criteria below pass and no unresolved gap invalidates the outcome.

## Phase Rollback Boundaries

### Phase 1

- Before state migration, SeaweedFS contains no authoritative OpenTofu state and can be corrected without state rollback.
- Preserve the independent encrypted pre-migration state and key recovery copies.
- On a proven migration failure, stop all plans/applies, restore the prior backend configuration, and recover from the verified copy without editing state contents.
- Never run broad applies while backend ownership or lock state is uncertain.

### Phase 2

- Keep each current `values/` entry until BWS readback and consumer verification pass.
- If a consumer fails before mutation, correct only its routing/rendering boundary.
- If a live service degrades, restore the prior value source for that service and redeploy only that service.
- Do not continue to the next configuration family until the current family and affected services are healthy.

## Final Success Criteria

- BWS is authoritative for every in-scope site-configuration key.
- Existing commands consume validated temporary inputs rendered from BWS using existing file formats and validators.
- SeaweedFS is homelab-owned, immutable-pinned, persistent, versioned, and directly healthy.
- OpenTofu state is encrypted in SeaweedFS, distributed locking is proven, useful state versions exist, and the final plan has no drift.
- Independent encrypted state and key recovery copies remain available.
- Migrated values entries and duplicate wiring are removed.
- Excluded backup, dump, OCI, live object-data, VM/LXC backup, and mutable Hermes-state concerns remain unchanged.
- Every affected enabled service passes focused readiness and functional checks.
- No `onramp-vNext` dependency, paid resource, guest replacement, router/firewall redesign, credential rotation, unrelated refactor, or private-data disclosure was introduced.

## Handoff Notes

- Resume from the first unchecked item whose phase dependencies are complete.
- Reinspect current Git, BWS, private, and live state before resuming. Do not assume this draft reflects later mutations.
- Record only sanitized evidence summaries in this file. Large or private output belongs in ignored `.tmp/` or OS temporary storage.
- Run focused checks between phases. Reserve the single `just validate` run for F2 after the complete active plan is otherwise finished.
- Archive the completed plan under `.specs/archive/bws-seaweedfs-state/plan.md` only after F4 passes.
