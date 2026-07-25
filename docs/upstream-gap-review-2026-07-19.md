# Upstream Gap and Suitability Review

Date: 2026-07-22

## Scope and exact revision set

This is a source-level, read-only review of every commit reachable from `upstream/main` and not from `origin/main`, compared with the current fork and its post-merge-base history.

- Fork ref/tip: `origin/main` = `524ac1fef94d13ff893dc5e82683dd79bda19995` (`feat: wire Hermes infrastructure operator`)
- Upstream ref/tip: `upstream/main` = `4158ae52cdd33a89b091fd12617c8915f83b4976` (`fix(menos): preserve managed baseline seed data`)
- Merge base: `c4c1b4d28d13f0d4dcf9fe2b3d656bd2234e4e7e` (`docs(scaffold): document EdgeRouter SSH settings`)
- Reviewed range: `origin/main..upstream/main`
- Upstream-only commits: **43**
- Distinct paths changed somewhere in the range: **233**

`git cherry -v origin/main upstream/main` returned `+` for all 43 commits. Therefore no upstream-only commit has an exact patch-ID equivalent on the fork. “Patch absent” is not treated as “behavior absent”: the disposition table explicitly identifies independently implemented or superseded behavior.

## Methodology, evidence, and boundaries

For each commit in the exact range, the review inspected its full patch (`git show --format=fuller --find-renames --find-copies <commit>`) and its changed paths (`git log --reverse --name-status origin/main..upstream/main`). A read-only loop completed all 43 patch inspections. Current-fork comparisons used the current public source and the fork history after the merge base, with particular attention to:

- runtime/service selection: `infra/services.json`, `scripts/service-runtime.py`, `infra/opentofu/services.tf`, and the Debian VM module;
- generic storage and state: `0e3e194`, `infra/ansible/tasks/host-storage-zfs-dataset.yml`, `infra/ansible/playbooks/service-state-backup.yml`, `e017bba`, and `50a6157`;
- rollout and plan safety: `cbefd5b`, `ccbd805`, and `f9623b7`;
- managed pin/update behavior: `39139cb` and the current update tooling;
- Technitium DNS orchestration and its pinned artifact path: `4d124da`, `infra/ansible/playbooks/technitium-dns.yml`, and `infra/ansible/scripts/apply-technitium-dns.py`;
- Hermes authority: `524ac1f`, its plugin, and `scripts/hermes-operator.py`.

Assessment criteria are the public repository policy in `AGENTS.md`: tracked data must remain public-safe; site facts and state belong only in ignored `values/`; resource declaration stays in OpenTofu and guest orchestration in Ansible; normal service access is direct rather than Proxmox `pct`; updates use managed pins and the public `just` workflow; DNS is critical; and the Hermes operator must retain saved-plan verification, explicit approval, separate destructive/stateful gates, and redaction.

No private `values/` content, private history, credentials, real topology, state, plans, or artifacts were inspected. No apply, plan, live diagnostic, service call, state operation, or other infrastructure mutation was run. This report contains only public-safe paths, generic descriptions, and commit identifiers.

Disposition vocabulary:

- **Already incorporated** — substantive capability exists through a different fork patch.
- **Partially incorporated** — the upstream commit mixes present and absent capabilities.
- **Adopt** — port the focused change with normal conflict resolution and tests.
- **Adapt** — retain the intent but redesign for fork architecture/policy.
- **Defer** — potentially useful, but needs an explicit design/product decision.
- **Reject** — unsuitable to import as fork functionality.

## Executive summary

Do not merge or cherry-pick this range wholesale. The fork has intentionally moved beyond upstream in three foundational dimensions:

1. **LXC/VM runtime abstraction.** `infra/services.json`, `scripts/service-runtime.py`, `infra/opentofu/services.tf`, and `infra/opentofu/modules/debian-vm/` support common service behavior across LXC and VM implementations. Much of upstream assumes direct LXC/PVE topology.
2. **Generic storage.** `0e3e194` introduced service storage and host preparation for directory, ZFS, NFS, and CIFS. Upstream’s Forgejo/ZFS-specific material cannot be overlaid directly, although ownership-preservation intent is valuable.
3. **Constrained Hermes authority.** `524ac1f` adds the infrastructure-operator bridge/plugin. It must remain the only Hermes infrastructure-control path: saved-plan evidence, explicit apply approval, separate destructive/stateful gates, output redaction, and post-upgrade plugin availability cannot be weakened by maintenance skills, journals, or custom-release paths.

Near-term value is fork-native adaptation of storage ownership preservation (`930f331`), disabled inventory groups (`452a580`), disabled DNS-record preservation (`14b08bf`), and scalable backup transfer (`845bf634`, with relevant portions of `6725f086`). The public-safety regex fix (`90d1e0a`) is an isolated adoption candidate. Newly reviewed onramp recovery work should adapt `3f78f09` to declare the missing `rsync` dependency and pass state-path variables through the tooling container; `718ae41` can then be adopted to prevent Git Bash/MSYS conversion of those paths. `deb0cfa` identifies a real capacity concern, but its fixed 128-GB default is Menos-import-driven and should be deferred pending a generic free-space preflight and resource-sizing policy. Security/pin expansion needs a runtime-aware policy. Technitium HA is a separate critical-infrastructure project. The expanded Onclave/Menos workload and migration series remains application-specific and should not be imported without an explicit product decision.

## Current-fork capability baseline

- **Stateful rollout and targeting:** `cbefd5b`, `ccbd805`, and `f9623b7` provide stateful gates, targeted rollout, and saved-plan scope binding. `524ac1f` independently constrains operator actions.
- **Hermes:** `33816e8`, `7ca4683`, `baf2b2c`, `04b5b4c`, `50a6157`, and `524ac1f` provide managed dashboard/gateway runtime, controlled sudo policy, explicit legacy opt-in, guarded state work, and the operator boundary.
- **State handling:** `service-state-backup.yml` creates a service-side archive, fetches it into private values, applies mode `0600`, and records a local SHA-256 manifest. Forgejo PostgreSQL and Infisical state are covered by `e017bba`. Remote archive plus Ansible fetch remains a scalability/transport gap.
- **Technitium:** `4d124da` implements pinned, checksum-verified portable releases with rollback/health handling, consistent with the policy against routine `install.sh` reruns.
- **Direct access:** dynamic inventory derives service endpoint/user from tfvars and the runtime map. New work must not regress to normal Proxmox-console access.
- **Public safety:** current `scripts/public-safety-check.py` still uses the pre-fix IPv6 regex at line 36; it is not an independently incorporated equivalent of `90d1e0a`.

## Capability-series analysis — primary assessment

This review is organized around **final upstream capabilities**, not isolated commits. A later correction may narrow, replace, or make an earlier change safe; therefore no commit series below should be cherry-picked selectively unless its row explicitly identifies a standalone extractable change. The commit-level table is retained as **Appendix A** for traceability.

### Decision model

For each area, evaluate the state at `upstream/main` after every follow-up commit in that area:

1. identify the initial capability and all prerequisites, corrections, and tests;
2. state the net behavior at the upstream tip, rather than treating an early patch as final;
3. compare that behavior with this fork’s current runtime, storage, direct-access, public-safety, and Hermes-authority contracts;
4. decide whether to adopt, adapt, defer, or reject the **capability series**;
5. only then identify small, independently useful fragments for separate implementation.

### Capability-series map

| Area | Upstream series | Final upstream behavior | Fork conclusion |
|---|---|---|---|
| Baseline snapshot, stateful rollout, and targeted apply | `99c59bd`, `8e11163`, `14570d9` | A broad snapshot followed by stateful-plan gates and targeted service workflows. | **Already incorporated / partial.** The fork’s runtime-aware targeted rollouts, saved-plan scope binding, and Hermes approval controls supersede the upstream LXC-oriented implementation. Mine no bulk snapshot patch. |
| Hermes managed runtime, gateway, and guarded state restore | `d460191`, `56b54cd`, `c43e600`, `c521d7f` | Managed Node/dashboard runtime, messaging gateway, and guarded customized-state bootstrap. | **Already incorporated.** Preserve the stronger fork implementation and constrained operator boundary. |
| Hermes custom releases and maintenance authority | `8319d3f`, `e2fbb0c`, `1588637` | Adds custom wheel discovery/activation, a source-specific maintenance skill, then relaxes trust timing for verified fork releases. | **Defer/reject as a series.** It creates a second infrastructure-control path and needs an explicit immutable-provenance, signing, rollback, plugin-survival, and authority design before any adoption. |
| Generic service-state transfer and recovery | `845bf63`, `6725f08`, `3f78f09`, `718ae41` | Streamed/compatible state transport plus later recovery dependency, Compose environment, and Windows path corrections. | **Adapt the capability; adopt one narrow follow-up.** Design direct LXC/VM transfer with atomic private output, checksums/manifests, redaction, and restore testing. Separately adapt `3f78f09` for `rsync` and Compose environment forwarding; then adopt `718ae41` for MSYS path preservation. |
| Update and security policy | `06a0529`, `3fc59e2` | Unattended security-update behavior and expanded release-pin validation. | **Adapt.** First decide guest coverage, maintenance windows, restart/reboot reporting, managed-pin provenance, and critical-Technitium policy. |
| Small control-plane correctness fixes | `452a580`, `90d1e0a`, `14b08bf` | Preserves empty disabled-service groups, avoids a public-safety IPv6 false positive, and preserves disabled service DNS records during migration. | **Adapt/adopt individually.** Generate disabled groups from the fork registry; adopt the IPv6 and disabled-DNS corrections with regression coverage. These are standalone and do not require the larger upstream architecture. |
| Technitium high availability | `f0bf977`, `2763810`, `9d375a4` | Secondary DNS guest, floating failover, staged private inputs, and HA tests/documentation. | **Defer as one critical-DNS project.** Do not extract staging or tests before a fork-native authority, failover, split-brain, backup/restore, rollback, and direct-access design exists. |
| Generic storage ownership preservation | `930f331` | Prevents repeat apply from overwriting guest/service-managed dataset ownership. | **Adapt as a focused storage capability.** Apply initial mapped ownership only when creating storage, cover directory/ZFS/NFS/CIFS, and test first and repeat application. |
| Onramp substrate capacity and validation performance | `93f6f9f`, `deb0cfa` | A Windows ansible-lint optimization and a 128-GB onramp default motivated by migration/restore headroom. | **Adapt/defer.** Evaluate the lint optimization for equivalent fork behavior. Defer the fixed disk size: define a generic free-space preflight and workload-based capacity policy before changing VM defaults. |
| Onclave/Menos workload, canary, and C2 migration program | `65a2752`, `8d32d55`, `493470a`, `0c11c62`, `407f26e`, `487a38c`, `e76e324`, `8e201b8`, `73daef1`, `61c1def`, `2ab568c`, `0d6eaad`, `4158ae5` | Named Onclave/Menos workloads; then port/isolation corrections and an evolving Menos/SurrealDB/MinIO migration system with data normalization, deduplication, and managed-baseline handling. | **Reject as a whole.** The final behavior is an application-specific deployment and data-migration program with schema, credential, network, image, and authority contracts absent from this generic runbook. Do not import individual fixes from the series; if required later, design reusable app-platform and migration primitives first. |
| Historical journals and handoffs | `576cf26`, `6a14ef4`, `4c8ab08`, `e834d28` | Archived process artifacts, an agent handoff, and a host-side update journal. | **Reject/defer.** Treat them as reference material only unless the fork explicitly defines private evidence retention and Hermes-operator integration. |

### Supersession and correction map

There are **no explicit `Revert` commits** in the reviewed range. There are, however, important correction chains that must be evaluated as final-state programs rather than additive commit lists:

| Series | Successor relationship | Review implication |
|---|---|---|
| Menos deployment | `8d32d55` corrects the ports introduced by `65a2752`; `493470a` replaces fragile text substitutions with parsed Compose rendering and asserts network isolation. | Neither correction is independently useful without the rejected workload. |
| Menos C2 migration | `407f26e` derives the rollback path and `487a38c` makes validation path-independent after `0c11c62` introduced the migration. `8e201b8` through `4158ae5` progressively rewrite relationship references/timestamps, remove legacy schema and migration history, deduplicate imported relationships, and preserve the new managed baseline. | The initial migration patch is not the final design. Reject the complete final migration program, not merely its first commit. |
| Service-state recovery | `3f78f09` exposes missing runtime dependencies and missing container environment pass-through; `718ae41` protects the same values from Windows/MSYS conversion. | Implement in dependency order: fork-native recovery wiring first, then the narrow Windows compatibility correction. |
| Hermes custom releases | `e2fbb0c` changes the maintenance-skill presentation and `1588637` changes trust timing after `8319d3f` creates custom-release machinery. | Evaluate as one authority/provenance feature; do not adopt the trust relaxation in isolation. |
| Technitium HA | `2763810` and `9d375a4` supply staging/tests after `f0bf977` adds HA. | The core topology decision precedes its configuration and tests; defer the whole program together. |

### Extractable versus coupled work

**Independently extractable after focused tests:** `90d1e0a`, `14b08bf`, and the intent of `452a580`; `718ae41` after the service-state environment wiring is present.

**Fork-native adaptation units, not cherry-picks:** `930f331` storage ownership, `845bf63`/`6725f08` state transfer, `3f78f09` recovery wiring, `06a0529`/`3fc59e2` update policy, and `93f6f9f` lint performance.

**Coupled programs to keep whole:** Technitium HA; Hermes custom releases; Onclave/Menos workload and migration; update journals. A later fix within one of these programs does not become suitable merely because it addresses a real upstream defect.

## Cross-cutting risks

### Runtime and direct service access

Any adopted inventory, backup, update, targeting, or HA change must use `service_runtime` and dynamic inventory rather than LXC/PVE assumptions. Normal diagnostics and backup transport must use direct SSH/HTTPS service access; Proxmox lifecycle access is exception-only. Shared paths need LXC and VM coverage.

### Generic storage and state preservation

`930f331` has the right ownership-preservation principle but names an older dataset model. In this fork, host preparation establishes storage while a guest may deliberately change ownership later. Establish initial ownership only on creation and preserve it thereafter. Review this across directory, ZFS, NFS, and CIFS with first-run/repeat-run tests.

### Update pins and security policy

All version changes must use managed pins and `just update`/`just validate`/`just plan`/approved `just apply`. Do not silently import upstream release-age or source policy. Custom Hermes wheels, Caddy/Go, Tailscale, unattended Debian updates, and application pins require source-aware provenance, checksum, hold, rollback, and maintenance-window policies. Technitium remains a pinned portable artifact; routine installer reruns are prohibited.

### Backup and restore safety

Streaming could reduce controller buffering pressure, but must retain temporary-file atomicity, `0600` private output, archive checksum/manifest validation, cleanup on failure, and service catalog boundaries (including PostgreSQL/Infisical/Hermes). It is not evidence of a tested restore.

### DNS and Technitium

Disabled-record preservation is appropriate because a migration must not delete operator-managed critical DNS merely because a service is disabled. Technitium HA would add peers, floating addressing, cluster credentials, and failover behavior. Keep all real values private and do not proceed without a reviewed, reversible, failover-tested design.

### Hermes authority and public safety

No upstream maintenance skill, host journal, or release workflow may bypass the constrained operator. Preserve saved-plan evidence, explicit apply approval, separate destructive/stateful overrides, redaction, atomic activation/rollback, and plugin availability after upgrades. Tracked files retain placeholders/RFC 5737 data only; real endpoints, credentials, records, archives, state, and topology remain in ignored `values/`.

## Prioritized recommendations

1. **Adapt storage ownership first.** Rework `930f331` for the generic storage contract: record creation, set initial mapped ownership only on create, audit all backends, and test repeat application.
2. **Make small non-destructive control-plane fixes.** Adapt registry-driven disabled groups from `452a580`; adopt `90d1e0a`; adopt `14b08bf` with migration tests.
3. **Design scalable, portable backup transfer.** Adapt `845bf634`, then applicable `6725f086` portions. Test direct SSH streaming, atomic cleanup, permissions, and restore validation on public-safe fixtures for LXC and VM.
4. **Decide update/security policy before porting code.** Define cadence, no-auto-reboot/restart reporting, runtime coverage, and Technitium maintenance behavior; then adapt selected `06a0529`/`3fc59e21` validation. Consider `93f6f9f6` only after equivalence testing.
5. **Retain the Hermes trust boundary.** Keep official pinned releases unless a custom-build requirement is explicitly approved with a stricter provenance/trust contract. Reject the parallel maintenance skill.
6. **Treat Technitium HA as a separately approved project.** Require authority model, secondary runtime, VIP lifecycle, split-brain protection, backup/restore, rollback, and controlled failover tests before considering commits 21–23.
7. **Repair current generic recovery seams.** Adapt `3f78f09` to install `rsync` where the existing restore playbook requires it and forward the two service-state path variables through Compose. Then adopt `718ae41` to protect those paths from MSYS conversion. Add tests for the dependency and container environment propagation.
8. **Make onramp restore capacity explicit.** Defer `deb0cfa`'s 128-GB default. First define a generic free-space preflight, capacity requirements per enabled workload, an expansion procedure, and validation that the guest filesystem—not only the virtual disk—has grown.
9. **Do not import Onclave/Menos.** The expanded commits 30–33 and 35, 38–43 remain coupled to the rejected named workloads and C2 migration. If an explicit product request later selects an application, design reusable app-platform primitives; include port-allocation, migration, rollback, and data-integrity tests rather than importing the workload series.

## Verification performed and results

All verification was read-only and did not access ignored private values.

| Command/check | Result |
|---|---|
| `git fetch upstream --prune`; `git rev-parse --verify origin/main`; `git rev-parse --verify upstream/main` | Refreshed upstream and resolved to `524ac1fef94d13ff893dc5e82683dd79bda19995` and `4158ae52cdd33a89b091fd12617c8915f83b4976`. |
| `git merge-base origin/main upstream/main` | `c4c1b4d28d13f0d4dcf9fe2b3d656bd2234e4e7e`. |
| `git rev-list --count origin/main..upstream/main` | `43`. |
| `git log --reverse --name-status origin/main..upstream/main` | Enumerated all 43 table commits and their changed paths. |
| Full-patch loop over `git rev-list --reverse origin/main..upstream/main` using `git show --format=fuller --find-renames --find-copies` | Completed successfully: `Inspected complete patches: 43`; 233 distinct changed paths. |
| `git cherry -v origin/main upstream/main` | 43 `+` entries; zero exact patch-ID equivalents. |
| `python3 scripts/public-safety-check.py --tracked-files <(printf '%s\n' docs/upstream-gap-review-2026-07-19.md)` | Passed after avoiding a checker-ambiguous double-colon configuration-key literal in the explanatory prose. |
| Current-source checks of runtime registry, storage task, backup/restore playbooks, state CLI/Compose wiring, onramp package list/scaffold, DNS migration, public-safety regex, Hermes operator history | Confirmed the comparisons cited above, including unconditional ZFS ownership, fetch-based backup, pre-fix IPv6 regex, missing current onramp `rsync`/Compose state-path wiring, pre-restore capacity pressure, and `524ac1f` operator surfaces. |

## Confidence and limitations

Confidence is high for exact refs/count, complete 43-commit coverage, patch absence, changed-path/full-patch inspection, and current public-source comparisons. The original 29-commit report was revalidated and extended through the current upstream tip; all 14 later commits are explicitly dispositioned.

Limitations:

- No private `values/` files, private history, credentials, topology, DNS records, artifact cache, state, or backups were inspected.
- No live endpoints, backup sizes, enabled service set, HA prerequisites, plans, or deployment behavior were tested.
- No cherry-pick simulation was performed; this is suitability analysis, not a mechanical-conflict forecast.
- No production validation is implied for either branch.

## Bottom line

All 43 upstream commits are patch-absent, but several earlier capabilities are independently present in the fork. Do not merge the range. Adapt generic storage ownership preservation first, then apply the small public-safety/DNS/inventory corrections and design direct streaming backup. Also adapt the current generic onramp recovery wiring (`3f78f09`) and then adopt the Windows path fix (`718ae41`); defer `deb0cfa`'s 128-GB capacity default pending generic evidence. Treat security/pin expansion as policy work, custom Hermes releases as an optional trust-boundary project, and Technitium HA as separately approved critical-infrastructure work. Reject the source-specific Onclave/Menos series—including its later canary and migration follow-ups—and the duplicate Hermes maintenance skill unless explicitly required.

## Appendix A — commit-level evidence index

The following index preserves the complete 43-commit traceability. Its dispositions support the capability-series conclusions above; it is not the primary unit of import decision-making.

| # | Upstream commit | Changed-path focus | Disposition | Evidence-backed assessment |
|---:|---|---|---|---|
| 1 | `99c59bdc` `fix(repo): update tracked changes` | 99-path snapshot across inventory, LXC roles, state, Hermes, Technitium, update, docs | **Partially incorporated** | Not a coherent port unit. The fork independently supplies later runtime, generic-storage, state, managed Hermes, and managed Technitium capabilities, while this snapshot retains LXC and Forgejo-storage assumptions. Mine focused later fixes only; never import this bulk patch. |
| 2 | `8e111638` `feat(infra): add stateful rollout safety gates` | plan/apply guards, targeted helper, state docs/tests | **Already incorporated** | Fork `cbefd5b` gates stateful batches and `f9623b7` binds apply scope to plan metadata; `524ac1f` adds operator-specific approvals. Retain the stronger runtime-aware fork model. |
| 3 | `14570d94` `feat(infra): support targeted service apply workflows` | inventory, apply/plan/service helper, storage vars | **Already incorporated** | Fork `ccbd805` already provides targeted rollouts and does so against current service-runtime/generic-storage schemas. |
| 4 | `d460191a` `fix(hermes): use packaged dashboard TUI bundle` | Hermes role/dashboard environment/tests | **Already incorporated** | Fork `33816e8` provides the managed dashboard runtime and packaged/preflight flow. |
| 5 | `56b54cdb` `feat(hermes): install and preflight managed Node.js runtime` | Hermes role, preflight/service templates, migration/docs | **Already incorporated** | Fork managed runtime verifies architecture-specific Node pins and drives dashboard preflight/activation. |
| 6 | `c43e6005` `feat(hermes): add managed messaging gateway runtime` | Hermes lock/runtime/systemd/update | **Already incorporated** | Fork `7ca4683` and `baf2b2c` implement gateway service/health and constrained runtime sudo policy. |
| 7 | `c521d7fc` `feat(hermes): restore customized state during guarded bootstrap` | Hermes bootstrap state, catalog/CLI | **Already incorporated** | Current Hermes bootstrap validates archive/checksum/schema, avoids unsafe overwrite, stops services, repairs ownership, and records restoration. |
| 8 | `845bf634` `fix(state): stream large service backups` | backup playbook, `fetch-service-state.py` | **Adapt** | Exact streaming helper is absent: the current playbook creates a remote archive then invokes `ansible.builtin.fetch`. Adapt for direct VM/LXC service access, `ansible_become`, private destination, atomic local output, checksums/manifests, and quiet/redacted output. |
| 9 | `8319d3f7` `feat(hermes): deploy customized release wheels` | custom release discovery, lock artifacts, runtime, `.pi` skill | **Defer** | Current fork uses pinned official wheels and a constrained operator. Custom builds require explicit immutable provenance, signing/trust, lock generation, rollback, state-schema, and plugin-survival decisions. Do not create a parallel maintenance-control surface. |
| 10 | `e2fbb0c1` `docs(hermes): keep fork skill public-safe` | upstream maintenance skill only | **Reject** | A source-specific maintenance skill duplicates/conflicts with the constrained Hermes operator. Sanitized wording does not solve the authority-path problem. |
| 11 | `1588637a` `feat(hermes): trust verified fork releases immediately` | custom-release discovery/update policy | **Defer** | Only meaningful if commit 9 is approved. Removing an age hold based solely on fork identity is weaker than managed-pin policy; any exception needs independently verifiable immutable provenance and explicit policy. |
| 12 | `6725f086` `fix(workflow): resolve backup and inventory warnings` | Compose ACL transport, migration parser, state CLI/docs | **Adapt** | Windows ACL and migration-warning portions may help, but must be reconciled with containerized tooling and direct VM/LXC transport. Assess with `845bf634`; do not copy host-ACL assertions without platform tests. |
| 13 | `576cf26d` `docs: archive update journal design and review artifacts` | 24 archived `.specs` artifacts | **Reject** | Historical process material is not runtime capability and imports stale/non-fork-specific assertions. |
| 14 | `6a14ef49` `docs: add agent platform design handoff` | upstream design handoff | **Defer** | Reference material only. If needed, write a concise fork-native document after VM/storage/operator authority decisions; do not import source-specific claims. |
| 15 | `4c8ab08c` `feat: add deterministic update run journal` | host Python journal/evidence validator/docs | **Defer** | Adds a second host-side execution/audit system and a CPython-host prerequisite. Decide evidence retention, private-data boundaries, and Hermes-operator integration first; it must never imply plan review or approval. |
| 16 | `06a0529a` `feat(ansible): manage security updates and service pins` | unattended-upgrades role, service playbooks, pin sources | **Adapt** | Useful security-only/no-auto-reboot intent is absent. First define LXC/VM guest coverage, service windows, restart/reboot detection, critical-Technitium behavior, and interaction with managed application pins. |
| 17 | `3fc59e21` `feat(update): expand managed release pin validation` | `scripts/update.py`, migration/tests | **Adapt** | Strengthens identity re-resolution and expands Caddy/Go/Tailscale/Forgejo pin handling. Fork `39139cb` already has managed artifacts but differs in source/provenance and runtime policy. Port only target-specific validation with tests; retain private operator pins and no implicit source changes. |
| 18 | `452a5806` `fix(inventory): preserve disabled service groups` | dynamic inventory, tfvars declarations/tests | **Adapt** | Empty known groups reduce Ansible group-resolution failures. Upstream enumerates LXC-era groups; derive groups from the current registry and test disabled services under both LXC and VM without selecting them for orchestration. |
| 19 | `90d1e0a7` `fix(security): avoid false IPv6 findings for config keys` | public-safety IPv6 regex/tests | **Adopt** | Current checker has the pre-fix boundary expression. Upstream prevents double-colon APT configuration keys from being parsed as IPv6 while preserving actual address checks. Port with the regression test. |
| 20 | `e834d287` `docs(spec): clarify mutation categories` | archived journal review artifact | **Reject** | No independent functionality; dependent on rejected archived journal material. |
| 21 | `f0bf9779` `feat(technitium): add clustered secondary DNS and floating failover` | secondary guest, cluster/keepalived roles, DNS/provider/service registry | **Defer** | Coupled critical-DNS design, not a safe incremental patch. It assumes LXC-oriented secondary topology and floating-address behavior. Require a fork-native authority/failover/split-brain/backup/rollback/direct-access design before implementation. |
| 22 | `2763810c` `feat(tooling): support staged Technitium cluster configuration` | private inputs, migration, parse/validate/state tooling | **Defer** | Depends on HA core and introduces peer/topology/token surfaces. A fork-native design must keep real topology in ignored `values/`, examples generic, and logs redacted. |
| 23 | `9d375a4c` `test(technitium): document and verify high availability changes` | HA docs/tests | **Defer** | Becomes valid only after the preceding HA design, including controlled failover and recovery tests. |
| 24 | `930f331a` `fix(storage): preserve service-managed dataset ownership` | ZFS task, docs/test | **Adapt** | Highest-priority correctness gap. Current `host-storage-zfs-dataset.yml` lines 57–63 unconditionally applies host mountpoint owner/group/mode, so repeat apply can undo guest/service-managed ownership. Apply initial mapped ownership only on creation, then audit directory/NFS/CIFS handlers and test first/repeat runs. |
| 25 | `65a27526` `feat(infra): add Onclave and Menos onramp workloads` | 40 application-specific role/playbook/state/migration/registry paths | **Reject** | Adds named deployment contracts, image pins, credentials, DNS, a LAN-published AMQP exception, and broad state boundaries. The generic onramp host exists, but importing these named workloads makes the reusable runbook application-specific without an explicit requirement. |
| 26 | `93f6f9f6` `perf(validation): speed up ansible lint on Windows` | `scripts/validate-public.sh` | **Adapt** | Temporary-filesystem lint input may improve Windows bind-mount performance without values data. Adapt only after equivalence checks for the fork’s container command, full playbook set, config-relative paths, cleanup, and lint invocation. |
| 27 | `869730c1` `test(safety): mark synthetic Menos secret fixture` | Menos importer test fixture | **Reject** | Solely follows rejected commit 25; no corresponding fork capability to test. |
| 28 | `14b08bf9` `fix(dns): preserve disabled service records` | `scripts/migrate-values.py`, migration test | **Adopt** | Current migration still builds desired Infisical/Hermes records from enabled optional services and can remove an absent/disabled record. Preserving operator-managed disabled records avoids destructive Technitium-critical DNS migration behavior. Port with regression coverage and explicit record-management semantics. |
| 29 | `8d32d55a` `fix(onclave): avoid SearXNG port collision` | Onclave role defaults/spec and safety test | **Reject** | The exact 8080→18080 collision correction is patch-absent, but its role only exists in rejected `65a27526`; current fork has no Onclave workload. Do not introduce an isolated, dead application-specific port setting. If Onclave is explicitly selected later, include this non-collision invariant in the fork-native workload design and test it against all shared-onramp ports. |
| 30 | `493470a` `fix(menos): enforce isolated canary deployment` | Menos compose rendering and safety tests | **Reject** | The network-isolation assertion is sound for a selected workload, but `menos_onramp` does not exist in the fork and depends on the rejected application-specific workload series. Preserve the “only explicitly required loopback/public ports” principle in any future generic app-platform contract instead of importing a dead role. |
| 31 | `0c11c62` `feat(menos): add managed C2 migration workflow` | Menos S3/Surreal migration, validation, playbook, tests | **Reject** | This 850-line migration creates a named Menos application contract, private snapshot format, database schema assumptions, migration authority, and a new operational command surface. It cannot be separated from rejected `65a27526`; no current fork service or registry capability can consume it. If an application migration framework is later required, design a generic, separately approved interface with authenticated archives, rollback, direct service access, and explicit operator authorization. |
| 32 | `407f26e` `fix(menos): derive C2 rollback archive path` | Menos migration playbook | **Reject** | Corrects only the rejected Menos migration workflow’s rollback-path parameterization; it has no independent fork surface. |
| 33 | `487a38c` `fix(menos): use absolute C2 validator path` | Menos migration playbook | **Reject** | Corrects only the rejected Menos migration workflow’s controller path assumption; it has no independent fork surface. |
| 34 | `3f78f09` `fix(onramp): harden service-state recovery` | Compose environment and onramp package list | **Adapt** | Current `service-state-restore.yml` uses `rsync` for pre-restore snapshots at lines 139–148, but the current onramp package list lacks it. Current `compose.yaml` also does not pass `SERVICE_STATE_BACKUP_ROOT` or `SERVICE_STATE_RESTORE_FILE`, despite `scripts/service-state.sh` exporting them at lines 114–124. Port the generic package and environment-forwarding intent in a fork-native change with container-environment and onramp-restore coverage; it is not an app-specific workload import. |
| 35 | `e76e324` `test(menos): format migration workflow assertions` | Menos migration tests | **Reject** | Test-only follow-up to rejected `0c11c62`; no fork migration workflow exists to exercise. |
| 36 | `deb0cfa` `fix(onramp): reserve capacity for state recovery` | Onramp scaffold/migration/docs/tests | **Defer** | The current restore process holds existing paths, a pre-restore snapshot, and an incoming archive at once (`service-state-restore.yml` lines 119–180), so the upstream change identifies a real capacity concern. Its fixed 128-GB default, however, is driven by the rejected Menos import rather than a demonstrated generic requirement. Design a free-space preflight, capacity formula, and filesystem-expansion guidance for enabled stateful workloads before making a resource-sizing decision. |
| 37 | `718ae41` `fix(state): preserve container paths on Windows` | Service-state shell CLI and tests | **Adopt** | Current `scripts/service-state.sh` passes `/workspace/...` paths through `SERVICE_STATE_BACKUP_ROOT` and `SERVICE_STATE_RESTORE_FILE` (lines 18, 116, 121–123) but does not exclude them from MSYS2 environment conversion. Port the narrow `MSYS2_ENV_CONV_EXCL` augmentation and regression test so Git Bash users retain Linux-container paths. |
| 38 | `8e201b8` `fix(menos): normalize legacy relationship references` | Menos migration scripts/playbook/tests | **Reject** | Depends on the rejected named Menos schema, snapshot, and C2 migration workflow. |
| 39 | `73daef1` `fix(menos): normalize legacy relationship timestamps` | Menos migration normalizer/tests | **Reject** | Depends on the rejected named Menos schema and migration workflow. |
| 40 | `61c1def` `fix(menos): preserve managed migration history` | Menos migration normalizer/tests | **Reject** | Depends on the rejected named Menos migration workflow and its application-specific history model. |
| 41 | `2ab568c` `fix(menos): import legacy snapshot data only` | Menos migration normalizer/tests | **Reject** | Depends on the rejected named Menos snapshot/import contract. |
| 42 | `0d6eaad` `fix(menos): deduplicate legacy relationships` | Menos migration scripts/normalizer/tests | **Reject** | Depends on the rejected named Menos database and migration workflow. |
| 43 | `4158ae5` `fix(menos): preserve managed baseline seed data` | Menos migration normalizer/tests | **Reject** | Depends on the rejected named Menos baseline-seed and migration contract. |

