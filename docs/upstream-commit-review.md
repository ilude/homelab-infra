# Upstream Commit Review

Tracking review of commits added to the upstream repository on 2026-07-14.
Reviews proceed from oldest to newest, one commit at a time. No upstream
changes are incorporated until explicitly approved.

## Review status

| Order | Commit | Subject | Status |
| ---: | --- | --- | --- |
| 1 | `8319d3f` | `feat(hermes): deploy customized release wheels` | Deferred |
| 2 | `e2fbb0c` | `docs(hermes): keep fork skill public-safe` | Deferred |
| 3 | `1588637` | `feat(hermes): trust verified fork releases immediately` | Deferred |
| 4 | `6725f08` | `fix(workflow): resolve backup and inventory warnings` | Incorporate |
| 5 | `576cf26` | `docs: archive update journal design and review artifacts` | Deferred |
| 6 | `6a14ef4` | `docs: add agent platform design handoff` | Deferred |
| 7 | `4c8ab08` | `feat: add deterministic update run journal` | Deferred |
| 8 | `06a0529` | `feat(ansible): manage security updates and service pins` | Incorporate |
| 9 | `3fc59e2` | `feat(update): expand managed release pin validation` | Incorporate |
| 10 | `452a580` | `fix(inventory): preserve disabled service groups` | Incorporate |
| 11 | `90d1e0a` | `fix(security): avoid false IPv6 findings for config keys` | Incorporate |
| 12 | `e834d28` | `docs(spec): clarify mutation categories` | Deferred |
| 13 | `f0bf977` | `feat(technitium): add clustered secondary DNS and floating failover` | Deferred |
| 14 | `2763810` | `feat(tooling): support staged Technitium cluster configuration` | Deferred |
| 15 | `9d375a4` | `test(technitium): document and verify high availability changes` | Deferred |
| 16 | `930f331` | `fix(storage): preserve service-managed dataset ownership` | Incorporate |

## Deferred review: `8319d3f`

This commit adds support for deploying a customized Hermes fork release as a
verified GitHub wheel instead of using only the official PyPI artifact.

### Potential value

- Allows deployment of fork-specific fixes and features.
- Provides immutable, checksum-pinned releases and rollback identity.
- Keeps custom source changes in the fork rather than mutating installed files.
- Retains hash-locked, offline installation of the runtime environment.

### Risks and prerequisites

- The custom fork and its release workflow become a root-equivalent trust
  boundary for the Hermes service.
- Wheel metadata parity does not prove that custom code is safe.
- The upstream tests do not replace a real Debian 13/Ansible deployment test.
- Generated lock paths assume the container controller path `/workspace`.
- Switching sources causes a full Hermes virtual-environment rebuild and
  restart; the existing official release must remain a verified rollback target.
- The implementation should be manually ported because this fork has unrelated
  Hermes changes and should not receive a wholesale cherry-pick.

### Decision

**Deferred.** Reconsider only if deploying the customized Hermes fork is a
required outcome. Before implementation, protect fork release permissions,
perform a disposable integration deployment, verify rollback, and confirm the
controller path assumption.

## Deferred review: `e2fbb0c`

This documentation-only commit sanitizes the concrete Hermes release-tag
example introduced by `8319d3f`, changing it to the
public-safe `homelab-vX.Y.Z.1` form.

It is deferred with `8319d3f` because the skill file does not exist in this
fork independently. If the Hermes fork-maintenance workflow is later adopted,
its sanitized example should be retained.

## Deferred review: `1588637`

This commit removes the 168-hour cooling-off period for custom Hermes fork
releases while retaining the existing checksum, metadata, tag-commit, and
non-rollback checks.

It is deferred with the preceding Hermes fork-release commits. Immediate
eligibility increases exposure to accidental or compromised releases; if the
custom source is later adopted, a hold should remain or immediate deployment
should be an explicit private opt-in.

## Review decision: `6725f08`

**Incorporate.** This change addresses backup permission enforcement on
Windows bind mounts and improves migration of templated legacy Proxmox
inventory values.

During implementation, correct the backup-root handling so the secured host
directory matches `SERVICE_STATE_BACKUP_ROOT`, keep the backup and migration
changes logically separable, and add platform-appropriate tests. Required
validation includes the existing unit/contract suite, shell checks, migration
regression tests, and a Windows/MSYS or equivalent ACL integration test where
available.

## Deferred review: `576cf26`

This documentation-only commit archives the update-run journal design and
review artifacts under `.specs/archive/update-run-journal/`. It adds no
runtime implementation. The archive references journal files that are absent
from this fork and contains inconsistent readiness statements, so it is
**deferred** unless the update journal is later implemented and the archive is
reconciled to describe its actual status.

## Deferred review: `6a14ef4`

This documentation-only commit adds a large agent-platform design handoff
covering Hermes, Pi, sandboxing, messaging, memory, personalization, and
future development services. It is **deferred** because it is broad,
speculative, and not required for the current infrastructure runbook.

The operator specifically wants to discuss this document in depth at a later
time before deciding whether any of its ideas should be adopted. Future review
must preserve the current repository-native source-of-truth and approval
boundaries.

## Deferred review: `4c8ab08`

This commit adds a large host-side journal for observing `just update`,
`just validate`, and `just plan`. It is **deferred** pending a decision that
durable update-session history justifies the implementation complexity.

The upstream tests passed, but the launcher files are non-executable despite
documentation showing direct execution, and real POSIX/Windows launcher,
interruption, locking, and host/container integration tests are still needed.
Unrelated service-update documentation changes should also be separated if this
feature is revisited.

## Review decision: `06a0529`

**Incorporate selectively.** Adopt the Technitium shutdown wait and Tailscale
version verification, and evaluate the Debian security-update role and other
changes as separate focused changes.

Required validation includes Debian security-origin dry-run testing, APT lock
contention handling, Tailscale pin lifecycle/migration coverage, Forgejo
Codeberg artifact verification, and backup equivalence tests for
`cp --archive --parents` versus the existing `rsync` behavior. Avoid adopting
the entire upstream commit as one unit.

## Review decision: `3fc59e2`

**Incorporate selectively.** Port the update re-resolution, checksum, Tailscale,
and Forgejo improvements with their related service work. Treat Caddy, xcaddy,
Cloudflare-module, and Go-toolchain management as a separate effort because
this fork lacks the required pin fields and deployment baseline.

Required validation includes release pagination/format handling, commit-time
hold behavior, Forgejo Codeberg assets, Tailscale migration and pin lifecycle,
and OCI responses with and without digest headers.

## Review decision: `452a580`

**Incorporate.** Initialize deterministic empty groups for all registered
services in the dynamic inventory and add the regression test. Keep the
unrelated TFLint suppression comments separate if they are needed.

Run the inventory tests through the repository tooling container, including
`python-hcl2` coverage, before considering the change complete.

## Review decision: `90d1e0a`

**Incorporate directly.** Tighten the IPv6 scanner boundaries to avoid
configuration-key false positives and retain the regression tests. Add a few
valid IPv6, URL, bracket, and zone-identifier cases during implementation.

## Deferred review: `e834d28`

This one-line documentation correction updates the archived update-journal
review material from deferred commit `576cf26`. It is **deferred with that
archive** and has no current operational effect.

## Deferred review: `f0bf977`

This commit adds a Technitium secondary LXC, clustered DNS replication,
Keepalived floating failover, and a second Proxmox provider. It is a desired
future capability, but is **deferred** because the design requires an in-depth
discussion before implementation.

The future review must address TLS verification, credential fallback,
cluster-dependency validation, DNS-client/VIP migration, failure-domain
assumptions, integration testing, and backup/recovery behavior. It should be
treated as a separate DNS high-availability project rather than routine fork
synchronization.

## Deferred review: `2763810`

This tooling commit supports staged private-value preparation for the proposed
Technitium HA design. It is **deferred with `f0bf977`** because it is tightly
coupled to that future project.

The review identified a critical default-selection issue: the example settings
enable `technitium_secondary` even though the secondary is described as
optional. The future implementation must keep it disabled by default and add
backup, dry-run, conflict-proofing, authoritative IP allocation, and atomic
private-values writes before activation tooling is adopted.

## Deferred review: `9d375a4`

This commit adds Technitium HA documentation and supporting tests. It is
**deferred with `f0bf977` and `2763810`** because the HA implementation still
requires security fixes, default-selection correction, network/failover
integration testing, and recovery design.

The staged rollout documentation and tests should be revisited as part of the
future HA project rather than adopted independently.

## Review decision: `930f331`

**Incorporate directly, adapted to this fork's storage task path.** Apply the
first-creation-only ownership condition to
`infra/ansible/tasks/host-storage-zfs-dataset.yml` and preserve existing
behavior for other storage backends.

Validation must cover first creation, repeat application, Forgejo bind mounts,
and explicit ownership-repair behavior for existing datasets.

All 2026-07-14 upstream commits currently identified for review have now been
covered.

## Pending reviews

The remaining commits have not yet been reviewed. Their status should be
updated only after inspecting the commit diff and assessing applicability to
this fork.
