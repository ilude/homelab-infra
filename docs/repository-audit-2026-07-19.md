# Infra Fabric Repository Audit

Date: 2026-07-19
Commit reviewed: `524ac1f` (`main`)
Scope: tracked repository source, OpenTofu, Ansible, service definitions, workflow scripts, tooling image, tests, CI, scaffold examples, and public documentation.

## Executive summary

The repository has a strong safety-oriented design: public and private material are deliberately separated, infrastructure plans are hashed and time-gated before apply, destructive/stateful changes have explicit gates, provider and major tool versions are pinned, service selection is centralized, direct service access is preferred over routine hypervisor access, and the test suite contains useful policy checks.

The current revision is not ready to be treated as a fully reliable public infrastructure runbook without remediation. The most important issues are:

1. The public-safety gate fails against the current tracked source because newly added tests contain unannotated RFC 1918 addresses and secret-like fixtures.
2. Several production binaries and build inputs are downloaded without checksum or signature verification, sometimes directly into their final executable path.
3. The Forgejo Actions runner receives an unrestricted SSH key for `root` on the Proxmox host, making a trusted-repository workflow compromise a hypervisor compromise.
4. Service-state restore is not transactional: failures after services are stopped or paths are removed can leave services down or data absent, without automatic rollback.
5. Service-state archives contain sensitive application data in plaintext, while the documented storage model relies on the private values Git repository and does not define encryption, retention, off-site copies, or restore-test objectives.
6. The Caddy build is duplicated in five roles, is not checksum-verified, and only rebuilds when the Cloudflare module is absent; changing pinned inputs does not update an already customized Caddy binary.

Overall assessment: good architectural intent and unusually thoughtful safety controls, but with high-impact supply-chain, CI, hypervisor-boundary, and recovery gaps. Fix the first four findings before expanding the service catalog or relying on automated deployment.

## Repository and project inventory

The repository contains 216 tracked files and approximately 27,150 tracked lines at the reviewed commit.

| Area | Purpose | Observations |
|---|---|---|
| `infra/opentofu/` | Proxmox LXC/VM resources, service enablement, outputs, validation | Local reusable Debian LXC/VM modules; provider lock is tracked; `variables.tf` is a 1,456-line monolith. |
| `infra/ansible/` | Service installation, configuration, readiness, DNS, storage, state backup/restore | Eleven roles and a large playbook surface; direct service access is explicitly enforced. |
| `infra/services.json` | Service registry and dependency/orchestration metadata | Good central source for service names, playbooks, inventory mappings, state capability, and Terraform addresses. |
| `scripts/` | Setup, values migration, validation, plan/apply gates, service orchestration, update checks | Strong plan metadata and redaction concepts; some helpers are large and combine multiple concerns. |
| `scaffold/` | Public-safe seed for the private `values/` repository | Detailed and useful, but duplicates a large configuration surface that migrations must keep synchronized. |
| `tools/` and `compose.yaml` | Reproducible local validation/runtime container | Tool versions are pinned; base image and Python dependency installation are not content-addressed. |
| `tests/` | Unit and policy/contract tests | 195 tests pass with declared dependencies; many Ansible tests inspect text/structure rather than execute roles. |
| `docs/` | Architecture, operator policy, service state, Hermes, and onramp notes | Good topic coverage, but missing governance, recovery objectives, and a concise service-support matrix. |
| `.specs/` | Historical plans and review evidence | 44 files and roughly 4,122 lines (about 15% of repository lines); valuable history, but prominent archival material increases navigation and maintenance noise. |
| `.github/workflows/validate.yml` | Public-source CI | Minimal permissions and commit-pinned checkout action are strengths; the current public-safety failure makes the workflow red. |

Managed service/project domains include Technitium DNS, service-local/shared Caddy, Forgejo, Forgejo Actions runner, Infisical (legacy LXC and onramp-host variants), Hermes, Tailscale client, the onramp host, and SearXNG onramp.

## Findings

### F-01 — High — Current tracked source fails the public-safety gate

Evidence:

- `scripts/public-safety-check.py:124-162` rejects non-example IP literals and secret-like assignments in tracked files unless explicitly annotated.
- `tests/test_hermes_operator.py:21`, `:26`, and `:68` contain unannotated RFC 1918 addresses.
- `tests/test_hermes_operator.py:21` and `:68` contain unannotated `TOKEN=...` fixtures.
- Running `.tmp/audit-venv/bin/python scripts/public-safety-check.py` produced three IP findings and two secret-like findings and exited 1.
- `.github/workflows/validate.yml:16-19` builds the tooling image and runs `scripts/validate-public.sh`, which invokes the same safety gate.

Impact:

- The main branch cannot pass its advertised public validation workflow as written.
- The repository's most important public/private separation control is currently non-enforcing in CI because CI stops on these fixtures.
- A permanently red safety check makes future real leaks easier to overlook.

Recommendation:

- Replace fixture addresses with RFC 5737 examples where the exact address class is irrelevant.
- Where a test intentionally verifies redaction of private addresses or secret assignments, add narrowly scoped `# public-safety: allow-ip` / `allow-secret` annotations and tests that ensure annotations remain limited to fixtures.
- Add a required branch check for `validate-public` and repair main immediately.

### F-02 — High — Production artifacts are installed without checksum or signature verification

Evidence:

- `infra/ansible/roles/forgejo/tasks/main.yml:77-84` downloads Forgejo directly to `/usr/local/bin/forgejo` with no checksum/signature verification.
- `infra/ansible/roles/forgejo_runner/tasks/main.yml:40-53` downloads Docker Compose and `just` without verification.
- `infra/ansible/roles/forgejo_runner/tasks/main.yml:123-130` downloads the Forgejo runner without verification.
- `infra/ansible/roles/infisical/tasks/main.yml:23-29` downloads Docker Compose without verification.
- Five Caddy build paths download and extract Go and build xcaddy dependencies without artifact checksum verification; examples are `infra/ansible/roles/caddy_proxy/tasks/main.yml:27-35` and `infra/ansible/roles/onramp_host/tasks/main.yml:82-90`.
- `docs/service-update-policy.md:16-18` prefers version plus checksum, but this is not consistently implemented.

Impact:

- DNS, Git, secrets, runner, Hermes, and ingress hosts trust network-delivered executables at deployment time.
- A compromised upstream/release path, transparent proxy, bad release asset, or partial direct-to-final download can install or leave a bad executable.
- Version pins alone do not provide artifact integrity.

Recommendation:

- Add architecture-specific SHA256 pins for every downloaded executable/archive and validate before installation.
- Download to a temporary file, verify, then atomically `install` into the final path.
- Prefer upstream signatures/provenance where available and record the verification policy.
- Extend `just update` to update version and checksum in one reviewed change; fail validation when a managed downloadable pin lacks a checksum.

### F-03 — High — Forgejo Actions runner has unrestricted hypervisor root SSH

Evidence:

- `infra/ansible/roles/forgejo_runner/tasks/main.yml:54-60` places the runner user in the Docker group.
- `infra/ansible/roles/forgejo_runner/tasks/main.yml:61-74` creates a persistent runner SSH identity.
- `infra/ansible/roles/forgejo_runner/tasks/main.yml:75-92` appends that identity without restrictions to `/root/.ssh/authorized_keys` on the Proxmox host.
- `README.md:131-144` describes a host-execution runner that can run validate, plan, and apply, and warns not to share it with untrusted repositories.

Impact:

- Compromise of the private values repository, a workflow, a Forgejo administrator, runner registration, or the runner host yields unrestricted root command execution on the Proxmox hypervisor.
- The trust boundary is stronger than an infrastructure deploy credential: it permits arbitrary host mutation outside reviewed OpenTofu/Ansible paths.

Recommendation:

- Replace unrestricted root SSH with a dedicated Proxmox deploy principal and a narrowly scoped forced-command wrapper or audited sudo rules.
- Prefer API-token operations for resource lifecycle where possible; separate host-storage/bootstrap authority from normal deploy authority.
- Add `from=`, `restrict`, `no-agent-forwarding`, `no-port-forwarding`, `no-pty`, and a forced command to any retained SSH authorized-key entry.
- Document the exact threat model, credential rotation/revocation process, and incident response procedure.
- Consider approval-protected deployment environments and signed/allowlisted workflow revisions.

### F-04 — High — Service-state restore is destructive and non-transactional

Evidence:

- `infra/ansible/playbooks/service-state-restore.yml:89-117` stops managed services and tolerates some stop failures.
- `:119-168` creates a pre-restore backup, but it is not used automatically on failure.
- `:176-187` removes all configured state paths before extracting the selected archive.
- `:188-219` performs database recovery and cleanup after filesystem replacement.
- `:230-251` starts services only at the end; system service start failures are suppressed with `failed_when: false`.
- The playbook does not wrap the operation in an Ansible `block` with `rescue`/`always` recovery.

Impact:

- A copy, extraction, disk-space, ownership, database, or service-start failure can leave a critical service stopped or with its prior data removed.
- Operators must manually find and restore the pre-restore archive during an incident.
- Suppressed system service failures can make a restore appear further along than it is.

Recommendation:

- Stage and fully validate the archive before stopping services.
- Check free space and archive contents/types, and require a valid checksum.
- Use `block`/`rescue`/`always`; on failure, restore the pre-restore snapshot and restart the original units.
- Restore into a staging directory and use atomic directory swaps where service layout permits.
- Make post-restore health checks mandatory before declaring success.
- Add destructive restore integration tests in disposable guests/containers.

### F-05 — High — Backups lack a complete confidentiality and disaster-recovery design

Evidence:

- `infra/ansible/playbooks/service-state-backup.yml:106-145` copies service state into a gzip-compressed tar archive.
- `:146-177` applies local permissions and writes an unkeyed SHA256 sidecar, but does not encrypt the archive.
- `infra/ansible/vars/service-state.yml:3-68` includes credentials/config, repositories, databases, logs, DNS configuration, Hermes state, and secret-service data.
- `docs/service-state-backup.md:66-74` recommends committing/pushing archives to the private `values/` Git repository but defines no retention, encryption, immutable/off-site copy, RPO/RTO, or periodic restore test.

Impact:

- Anyone who gains access to the private values remote or its clones obtains broad infrastructure and application state in plaintext.
- Git is inefficient for large changing binary backups and permanently retains deleted sensitive archives unless history is rewritten.
- A failure or compromise affecting the same Forgejo environment may remove both services and the primary backup location.

Recommendation:

- Encrypt archives before they leave the service host/controller using age, SOPS, restic, or equivalent key-managed encryption.
- Store backups in a dedicated, versioned, access-controlled, off-site target rather than ordinary Git history.
- Define retention, RPO, RTO, immutable-copy, key escrow/rotation, and restore-testing policies.
- Keep only manifests/pointers in the values repository if Git-based coordination is useful.

### F-06 — Medium — Caddy's managed pin is duplicated and does not drive upgrades

Evidence:

- The same Go/xcaddy/Cloudflare build command is duplicated in five roles, including `caddy_proxy`, `forgejo`, `infisical`, `hermes`, and `onramp_host`.
- `infra/ansible/roles/caddy_proxy/tasks/main.yml:18-35` rebuilds only when `caddy list-modules` cannot find `dns.providers.cloudflare`.
- Equivalent module-presence gates exist in the other roles.
- `docs/service-update-policy.md:35` says Caddy build inputs are version-pinned but not automatically updated.

Impact:

- Updating a hard-coded Caddy/Go/xcaddy/plugin version does not rebuild an existing binary if the module remains present.
- Five copies can drift and make security patching slow and error-prone.
- There is no installed build marker or binary checksum to establish desired state.

Recommendation:

- Create one reusable Caddy role with centralized version/checksum variables.
- Record a build manifest/hash and rebuild when any input changes.
- Verify the installed binary version/modules and make Caddy an explicit `just update` target.
- Prefer a reproducible prebuilt, signed, content-addressed artifact produced by CI.

### F-07 — Medium — `onramp_host_allow_passwordless_sudo` is a dead and misleading control

Evidence:

- `infra/opentofu/variables.tf:1225-1229` defines the variable and defaults it to `true`.
- `scaffold/terraform.tfvars:193`, `scripts/migrate-values.py:603`, `infra/services.json:223`, and `infra/ansible/roles/onramp_host/defaults/main.yml:7` propagate it.
- `infra/opentofu/onramp-host-checks.tf:37-45` only checks that the boolean is either true or false, which is tautological for a typed bool.
- `infra/ansible/roles/onramp_host/meta/argument_specs.yml` does not declare the option.
- `infra/ansible/roles/onramp_host/tasks/main.yml:155-157` explicitly says no broad sudo policy is installed and the role never uses the variable.

Impact:

- Operators can believe a deliberate sudo policy choice is enforced when it has no effect.
- The default/scaffold/migration surface violates the repository doctrine against permanent duplicate/dead knobs.
- Depending on cloud-init defaults, direct Ansible `become` may work for reasons outside the role's declared contract.

Recommendation:

- Decide the intended contract. Either remove the variable everywhere, or implement a minimal, validated sudoers policy and test both enabled/disabled states.
- Replace the tautological OpenTofu check with meaningful policy validation.
- Add the option to the role argument spec if retained.

### F-08 — Medium — Restore integrity is optional and not authenticity-protected

Evidence:

- `infra/ansible/playbooks/service-state-restore.yml:49-61` validates SHA256 only when a sidecar happens to exist.
- `infra/ansible/playbooks/service-state-backup.yml:161-177` creates an unkeyed SHA256 sidecar in the same directory as the archive.
- `service-state-restore.yml:63-79` checks absolute and `..` member names, but does not establish archive provenance.

Impact:

- A missing sidecar silently downgrades integrity checking.
- An attacker able to replace an archive can also replace its checksum.
- Root extraction makes restore artifacts highly trusted input.

Recommendation:

- Make a valid checksum mandatory and sign/authenticate the manifest (or use authenticated encrypted backup tooling).
- Validate file types, links, ownership ranges, expected roots, manifest service identity, and maximum expanded size before root extraction.

### F-09 — Medium — Onramp user services are also treated as system services

Evidence:

- `infra/ansible/vars/service-state.yml:45-56` lists `infisical-onramp.service` in both `services` and `user_services`.
- `:57-68` does the same for `searxng-onramp.service`.
- `service-state-restore.yml:89-117` and `:230-251` therefore attempt both system- and user-scope operations; system errors are suppressed.

Impact:

- Restore produces misleading failed system operations, hides mistakes through `failed_when: false`, and complicates incident diagnosis.

Recommendation:

- Keep user units only in `user_services`; reserve `services` for actual system units such as Caddy.
- Stop suppressing start failures for expected units and add explicit health verification.

### F-10 — Medium — Test coverage is strong on contracts but weak on executable lifecycle behavior

Evidence:

- The declared dependency environment ran 195 unit tests successfully.
- Tests such as `tests/test_service_state.py:38-44` assert only that strings like `pg_dump` and `pg_restore` occur.
- `tests/test_onramp_host_contract.py:50-56` checks for task labels/text but does not exercise firewall or sudo behavior.
- `tests/test_ansible_safety.py` provides useful structural policies, but there is no Molecule/disposable-guest role convergence, second-run idempotency, backup/restore, or failed-restore rollback test.

Impact:

- Dead controls such as `onramp_host_allow_passwordless_sudo` and lifecycle failures can pass the suite.
- Shell-heavy role behavior is validated syntactically rather than operationally.

Recommendation:

- Add disposable Debian 13 integration tests for high-risk roles and state workflows.
- Test first-run convergence, second-run idempotency, version update, interrupted download, health-check rollback, backup, restore, and failed restore.
- Add a test that every registry/scaffold variable consumed by orchestration is actually referenced by its role.

### F-11 — Medium — CI and security assurance are too narrow for the repository's risk

Evidence:

- `.github/workflows/validate.yml` has one job and only builds the image and runs public validation.
- There are no tracked dependency scanning, container scanning/SBOM, secret-history scanning, OpenTofu security checks, scheduled validation, or release artifact provenance workflows.
- `scripts/public-safety-check.py:35-55` recognizes a limited set of secret assignment patterns/prefixes and scans the current tracked tree, not Git history or high-entropy content.

Impact:

- Vulnerable packages/images, historical secrets, dangerous infrastructure defaults, and supply-chain drift may not be detected.

Recommendation:

- Add pinned CI checks for secret history, dependency vulnerabilities, container/SBOM scanning, and IaC security policy.
- Run scheduled update/validation checks and protect main with required status checks.
- Keep the custom public-safety policy as a domain-specific layer, not the only secret scanner.

### F-12 — Medium — Dependency reproducibility is inconsistent

Evidence:

- `tools/Dockerfile:1` uses `debian:bookworm-slim` without a digest.
- `tools/requirements.txt` pins Python package versions but not hashes.
- `tools/Dockerfile:15-27` installs floating Debian repository packages.
- OpenTofu/TFLint downloads are checksum-verified and the OpenTofu provider lock is tracked, showing a stronger pattern that is not consistently applied elsewhere.

Impact:

- Rebuilding the same commit at different times can produce materially different tooling images.

Recommendation:

- Pin the base image by digest and generate an SBOM.
- Use a hash-locked Python requirements file (`--require-hashes`).
- Define a deliberate OS package snapshot/update policy rather than implying byte-for-byte reproducibility.

### F-13 — Low — Repository navigation and governance can be improved

Evidence:

- `.specs/` contains approximately 4,122 lines of archived planning/review artifacts, about 15% of tracked lines.
- `infra/opentofu/variables.tf` is 1,456 lines and mixes all service domains.
- The repository has no `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CODEOWNERS`, or changelog/release policy.
- `README.md` is detailed but lacks a compact service support matrix showing runtime options, dependencies, storage/state support, backup status, update mechanism, and maturity.

Impact:

- New contributors must reconstruct active architecture from a long README, registry, scaffold, and archived specs.
- Public reuse and vulnerability reporting expectations are unclear.

Recommendation:

- Move historical review evidence to a clearly documented archive, generated artifact, or separate design-history location.
- Split OpenTofu variables by concern/service while preserving the module interface.
- Add governance files appropriate to the intended public audience.
- Add a generated service matrix sourced from `infra/services.json` plus explicit maturity/support fields.

### F-14 — Low — Documentation needs explicit operational objectives and boundary diagrams

Evidence:

- Existing docs explain workflows and ownership well, but do not define RPO/RTO, backup retention, monitoring/alerting ownership, certificate/DNS failure response, upgrade rollback windows, or tested disaster-recovery scenarios.
- The onramp and service-local Caddy ownership model spans multiple documents without one end-to-end architecture/data-flow diagram.

Impact:

- Operators have good command-level guidance but insufficient incident and service-level expectations.

Recommendation:

- Add an architecture overview with trust boundaries and control/data flows.
- Add an operations matrix for health checks, logs, alerts, backup frequency, RPO/RTO, restore test cadence, upgrade/rollback, and owner.

## Strengths

- Strong public/private separation doctrine in `AGENTS.md`, `.gitignore`, scaffold design, and custom public-safety checks.
- Reviewed-plan workflow with plan hash, input hashes, expiry, commit identity, target/replace scope, and destructive/stateful summaries in `scripts/tfplan-metadata.py`.
- Explicit apply gates for destroys and multi-service stateful batches.
- OpenTofu/Ansible responsibility split avoids `local-exec` configuration and keeps DNS changes in Ansible.
- Central service registry reduces hard-coded parity drift across settings, inventory, playbooks, and plan metadata.
- Direct service access and strict known-host handling are safer than routine `pct exec` usage.
- OpenTofu/TFLint artifact checksums, tracked provider lock, commit-pinned checkout action, and minimal CI token permissions are good supply-chain practices.
- Technitium and Hermes managed runtime paths include significantly stronger hash/checksum and rollback controls than several older service paths.
- Secret-bearing templates generally use restrictive modes and `no_log`; tests enforce several of those controls.
- Browser-facing services include local health/smoke checks and loopback binding patterns.
- The test suite is fast and broad at the helper/unit/policy level.

## Validation performed

No infrastructure plan or apply was run, and no live Proxmox, service, DNS, router, private values, or backup target was accessed.

| Check | Result |
|---|---|
| Repository status at start | Clean, `main` at `524ac1f`, aligned with `origin/main`. |
| `just validate` | Could not complete in this host environment: the local tooling image was absent and Docker Buildx 0.13.1 is below Compose's required 0.17. This is an environment/tool-bootstrap blocker. |
| Python unit suite in isolated venv with `tools/requirements.txt` | Passed: 195 tests. |
| Public-safety scanner against current tracked tree | FAIL: findings in `tests/test_hermes_operator.py` (F-01). |
| Python compile | PASS. |
| Bash syntax | PASS. |
| ShellCheck | PASS. |
| Docker Compose configuration | PASS. |
| Ansible inventory with declared dependency PATH | PASS. |
| Ansible syntax checks | PASS, with expected absent-host warnings for disabled scaffold services. |
| ansible-lint | Passed: 0 failures and 0 warnings in 124 processed files. |
| OpenTofu artifact checksum | PASS for pinned 1.12.3 download. |
| TFLint artifact checksum | PASS for pinned 0.63.1 download. |
| `tofu init -backend=false` | PASS; reused locked `bpg/proxmox` 0.111.0. |
| `tofu fmt -check -recursive` | PASS. |
| `tofu validate` | PASS. |
| TFLint (`minimum-failure-severity=error`) | PASS. |

## Prioritized remediation plan

### Immediate: restore trustworthy validation

1. Fix F-01 and make public validation green on `main`.
2. Require the validation status for merges.
3. Add a regression test ensuring the public-safety scanner successfully scans the real tracked tree, not only isolated fixtures.

### Near term: reduce compromise and outage risk

1. Remediate F-03 by removing unrestricted Proxmox root SSH from the runner.
2. Remediate F-02/F-06 by centralizing, checksumming, and atomically installing all managed artifacts.
3. Redesign restore around staged validation, rescue/rollback, mandatory integrity, and health checks (F-04/F-08/F-09).
4. Encrypt and move backups to a dedicated off-site system with documented recovery objectives (F-05).

### Medium term: improve assurance and maintainability

1. Remove or implement the dead sudo control (F-07).
2. Add executable role/lifecycle integration tests (F-10).
3. Expand CI security and supply-chain checks (F-11/F-12).
4. Consolidate Caddy and other repeated shell orchestration into reusable roles/helpers.

### Later: improve public project usability

1. Add governance, architecture/trust-boundary, service-matrix, and operations-objective documentation.
2. Split large configuration files by domain and reduce active-tree noise from archived specs.

## Audit limitations

- Private `values/` was not present and was intentionally not created, cloned, or inspected.
- Live infrastructure and service behavior were not tested.
- No plan/apply, state operation, DNS mutation, router/firewall mutation, or service deployment occurred.
- Vulnerability database results and upstream release freshness were not assessed; findings focus on repository controls and observed implementation.
