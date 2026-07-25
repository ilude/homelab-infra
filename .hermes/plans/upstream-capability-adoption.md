# Upstream Capability Adoption Plan

**Status:** Implementation in progress — approved fork-native work; no live infrastructure mutation, plan, or apply has been performed.

**Source decision record:** [`docs/upstream-gap-review-2026-07-19.md`](../../docs/upstream-gap-review-2026-07-19.md)

## Objective

Implement only the upstream-derived capabilities explicitly approved during the capability-series review, using fork-native designs. Do not cherry-pick the upstream range or introduce its LXC-only, application-specific, custom-release, or critical-DNS HA assumptions.

## Confirmed decisions

| Area | Decision | Implementation status |
|---|---|---|
| Rollout safety and targeted apply | Already incorporated; no action | No task |
| Hermes runtime, gateway, guarded restore | Already incorporated; no action | No task |
| Hermes custom releases and maintenance skill | Keep official pinned releases; no permanent custom channel or separate skill | No task |
| Generic service-state transfer and recovery | Approve fork-native adaptation | Planned below |
| Update/security behavior | Policy/design first; no code port yet | Planned below |
| Control-plane correctness | Adapt disabled groups; adopt IPv6 and disabled-DNS corrections | Planned below |
| Technitium HA | Defer as separately approved critical-DNS project | No task |
| Generic storage ownership | Approve fork-native adaptation | Planned below |
| Onramp lint/capacity | Evaluate lint optimization; defer fixed disk growth | Planned below |
| Onclave/Menos program | Reject | No task |
| Historical journals/handoffs | Do not import now | No task |

## Implementation constraints

The operator approved the fork-native tasks below and selected the active working branch. All changes must follow `AGENTS.md`: tracked source remains public-safe; private values and state stay in `values/`; no `just apply`, direct infrastructure mutation, or private recipes; direct service access remains the normal path.

## Ordered tasks

### UCA-01 — Record the final capability decisions

- [ ] Update the upstream review and documentation index to record the explicit interactive dispositions from this plan.
- [ ] Keep the capability-series table as the primary decision surface and the 43-commit table as traceability evidence.

**Affected paths:** `docs/upstream-gap-review-2026-07-19.md`, `docs/README.md`.

**Evidence:** Markdown link/path check, focused public-safety check over the changed documents, and `git diff --check`.

### UCA-02 — Preserve disabled service inventory groups from the registry

- [ ] Map the current registry’s known service inventory groups, including disabled services, without selecting disabled services for orchestration.
- [ ] Adapt dynamic inventory so group existence works for both LXC and VM implementations.
- [ ] Add focused tests for disabled services and runtime-specific group behavior.

**Likely paths:** `infra/services.json`, `infra/ansible/inventory/tfvars.py`, `tests/test_tfvars_inventory.py`, and registry-parity tests where needed.

**Evidence:** Focused dynamic-inventory and registry-parity tests; syntax-safe public validation; `git diff --check`.

### UCA-03 — Apply the public-safety IPv6 false-positive correction

- [ ] Port the narrow boundary-regex intent from upstream without relaxing real IPv6 detection.
- [ ] Add a regression fixture for a double-colon configuration key and retain a positive real-address case.

**Likely paths:** `scripts/public-safety-check.py` and its existing focused test module or a new adjacent test module.

**Evidence:** Focused checker regression tests and `scripts/public-safety-check.py`; `git diff --check`.

### UCA-04 — Preserve disabled-service DNS records during values migration

- [ ] Define explicit migration semantics: disabled optional services must not cause removal of operator-managed records.
- [ ] Adapt the migration logic without changing private records or applying DNS changes.
- [ ] Add regression cases for enabled, disabled, and absent optional-service state.

**Likely paths:** `scripts/migrate-values.py`, `tests/test_migrate_values.py`, and possibly public migration documentation.

**Evidence:** Focused migration tests; public-safety check; `git diff --check`.

### UCA-05 — Repair generic onramp state-recovery wiring

- [ ] Declare `rsync` on the onramp host because the restore playbook already uses it for pre-restore snapshots.
- [ ] Forward `SERVICE_STATE_BACKUP_ROOT` and `SERVICE_STATE_RESTORE_FILE` into the tooling Compose service.
- [ ] Add the Git Bash/MSYS exclusion for those two container-path environment variables, preserving any pre-existing exclusion value.
- [ ] Add focused tests for the package dependency, Compose environment contract, empty/pre-existing MSYS exclusion behavior, backup and restore path propagation.

**Likely paths:** `infra/ansible/roles/onramp_host/defaults/main.yml`, `compose.yaml`, `scripts/service-state.sh`, `tests/test_service_state_cli.py`, `tests/test_onramp_host_contract.py`, `tests/test_service_state.py`.

**Evidence:** Focused state CLI/onramp contract tests; public validation; `git diff --check`.

### UCA-06 — Adapt service-state transfer for large archives

- [ ] Design the fork-native LXC/VM transport contract before changing transfer code: direct service access, `ansible_become`, private destination, atomic local output, `0600`, checksums/manifests, redaction, cleanup, and failure behavior.
- [ ] Implement streaming or equivalent bounded-memory transfer only after the contract is approved in code review.
- [ ] Add public-safe tests for both LXC and VM paths, atomic cleanup, permissions, manifest/checksum validation, and a restore-oriented validation scenario.

**Likely paths:** `infra/ansible/playbooks/service-state-backup.yml`, `infra/ansible/playbooks/service-state-restore.yml`, `scripts/service-state.sh`, `infra/services.json`, `tests/test_service_state.py`, `tests/test_service_state_cli.py`.

**Evidence:** Focused state tests plus a safe read-only/public validation path. A restore test must use disposable fixtures or guests; no production restore is evidence for this task.

### UCA-07 — Preserve service-managed storage ownership across repeat applies

- [ ] Identify creation versus repeat-application state for each supported storage backend.
- [ ] Set mapped ownership/mode only on initial creation; do not overwrite guest/service-managed ownership later.
- [ ] Cover directory, ZFS, NFS, and CIFS handlers with first-run and repeat-run tests.

**Likely paths:** `infra/ansible/tasks/host-storage-zfs-dataset.yml`, related storage tasks, storage documentation, `tests/test_ansible_safety.py`, and dedicated storage tests if the existing structural tests cannot prove idempotence.

**Evidence:** Backend-specific first/repeat-run test coverage, Ansible syntax/lint through the public validation surface, and `git diff --check`.

### UCA-08 — Define update and security policy before code adoption

- [ ] Write a fork-native policy that decides guest coverage, maintenance windows, no-auto-reboot behavior, restart/reboot reporting, artifact provenance/checksum rules, rollback, and Technitium constraints.
- [ ] Map which upstream pin-validation ideas are compatible with that policy.
- [ ] Convert accepted policy rules into implementation tasks; do not introduce unattended update behavior in this task.

**Likely paths:** `docs/service-update-policy.md`, `docs/upstream-gap-review-2026-07-19.md`, `scripts/update.py`, `tests/test_update.py`.

**Evidence:** Reviewed policy document, explicit implementation/defer matrix, public-safety check, and `git diff --check`.

### UCA-09 — Evaluate Windows ansible-lint performance optimization

- [ ] Benchmark or reproduce the relevant Windows bind-mount bottleneck in a safe environment.
- [ ] Compare upstream temporary-filesystem behavior against the fork’s full playbook list, config-relative paths, container command, and cleanup requirements.
- [ ] Implement only if equivalence is demonstrated; otherwise record a no-change decision.

**Likely paths:** `scripts/validate-public.sh` and its focused test coverage.

**Evidence:** Before/after benchmark or reproducible timing record, equivalence checks, cleanup verification, and `git diff --check` if code changes.

### UCA-10 — Design generic state-recovery capacity preflight

- [ ] Define a capacity model covering incoming archive, existing state, pre-restore snapshot, staging/temporary overhead, and filesystem—not merely virtual-disk—capacity.
- [ ] Specify non-mutating preflight output and actionable remediation guidance.
- [ ] Decide later whether a generic onramp default change is justified; do not copy the upstream 128-GB default by assumption.

**Likely paths:** `docs/service-state-backup.md`, `docs/onramp-host-runbook.md`, `infra/ansible/playbooks/service-state-restore.yml`, scaffold/migration defaults, and focused tests for any preflight helper.

**Evidence:** Reviewed formula with public-safe fixtures, non-mutating preflight tests, and `git diff --check`.

## Dependency order

`UCA-01` → (`UCA-02`, `UCA-03`, `UCA-04`) → `UCA-05` → `UCA-06` → `UCA-07` → (`UCA-08`, `UCA-09`, `UCA-10`).

- `UCA-05` must precede the Windows path work included in it, and it should precede any state-transfer redesign.
- `UCA-06` and `UCA-10` share recovery semantics; keep their capacity and temporary-file assumptions aligned.
- `UCA-08` is a policy gate for any future security-update or expanded pin-validation code.
- `UCA-09` is optional and must not block correctness/safety tasks.

## Non-goals / explicit deferrals

- No custom Hermes release channel or maintenance skill.
- No Technitium HA code, configuration, private inputs, or tests.
- No Onclave/Menos workload, migration, schema-normalization, or canary code.
- No fixed onramp disk-size increase absent the `UCA-10` capacity decision.
- No live infrastructure mutation, `just plan`, or `just apply` as part of plan preparation or implementation verification unless separately requested and approved.

## Verification evidence log

| Task | Evidence required | Status |
|---|---|---|
| UCA-01 | Link/path check; focused safety check; diff check | Complete — review/index and implementation plan recorded |
| UCA-02 | Inventory and registry tests | Complete — focused inventory regression coverage |
| UCA-03 | Checker regression tests | Complete — focused public-safety regression coverage |
| UCA-04 | Migration regression tests | Complete — focused migration regression coverage |
| UCA-05 | State CLI and onramp contract tests | Complete — focused recovery/MSYS contract coverage |
| UCA-06 | State-transfer/restore fixture tests | Partial — streaming, archive validation, cleanup, and restore-capacity tests; guest smoke pending |
| UCA-07 | Storage backend first/repeat tests | Complete — YAML-driven first/repeat behavior model for all backends; canonical Ansible validation pending |
| UCA-08 | Reviewed policy and implementation matrix | Complete — policy/design only; no unattended updates implemented |
| UCA-09 | Equivalence and benchmark evidence | Partial — isolated lint workspace implemented; Windows equivalence/benchmark pending |
| UCA-10 | Non-mutating capacity-preflight tests | Partial — helper and unit coverage complete; mount-layout/guest smoke pending |

## Decision log

- 2026-07-22: Capability-series review completed interactively. The decisions in the table above were confirmed by the operator.
- 2026-07-22: This plan was created as a planning artifact only. Implementation remains gated on separate explicit approval.
