---
created: 2026-07-07
status: draft
completed:
---

# Plan: Convert Hermes Ansible to Direct Service Access

## Context & Motivation

The operator access model for this homelab is direct service access: operators should SSH to the service endpoint, for example `ssh <user>@hermes.example.internal`, and browse the service-local HTTPS endpoint. The current Hermes Ansible role contradicts that model by targeting `hosts: pve` and performing steady-state service configuration through Proxmox-mediated `pct exec` and `pct push` commands.

The user explicitly corrected the access assumption: Hermes should be accessed directly as `user@hermes.ilude.com`, not by SSHing to Proxmox and entering the LXC. `AGENTS.md` has been updated to state that direct service SSH/HTTPS is the normal path, while Proxmox `pct` access is for lifecycle diagnostics, bootstrap, console recovery, or explicit operator instruction. This plan turns that policy into the actual Hermes Ansible implementation.

## Constraints

- Platform: Windows host with Git Bash/MSYS (`MINGW64_NT-10.0-26200`), repo commands executed through Bash and Docker Compose tooling.
- Shell: `/usr/bin/bash`.
- Public tracked files must remain generic and public-safe; no real domains, IPs, hostnames, or secrets in tracked files.
- BWS owns configuration families and runtime secrets, SeaweedFS owns encrypted OpenTofu state, and ignored `values/` retains only excluded backups, artifacts, dumps, and mutable service-state data. Do not commit those private surfaces, `settings.local.json`, plans, or credentials.
- Use public `just` workflow commands for normal validation. Do not invoke private Just recipes as ordinary validation.
- Do not run `just apply`, OpenTofu apply/destroy/import/state surgery, or destructive operations without explicit user approval.
- Hermes steady-state service configuration should be performed by direct Ansible SSH to the Hermes service host, not `pct exec` from Proxmox.
- Proxmox access remains valid for LXC lifecycle/readiness checks, first-boot rescue, and cases where direct service SSH is unavailable.
- The MVP should be implementable and validated in one focused session.

## Risk & Manual Gate Decision

Manual gates are exceptional. Decide based on blast radius and rollback, not generic confidence. Be conservative for work/shared systems and data/resources that cost money; treat personal/local GitHub repos as localized-to-user when changes are reversible and validated.

- **Risk level:** Medium
- **Blast radius:** Local/home-lab Hermes management service and public source repo
- **Rollback:** Known: revert Git changes; avoid live apply unless separately approved; direct Ansible changes are idempotent and can be re-run or reverted by restoring the prior role/playbook
- **Manual approval before action:** Not required for source edits, tests, syntax checks, inventory checks, or non-mutating SSH ping. Required before any `just apply` or other live configuration mutation.
- **Manual validation after action:** Not required. Automated validation and non-mutating direct Ansible connectivity checks are sufficient for the MVP.
- **Decision reason:** The MVP changes tracked Ansible structure and validates it without destructive operations. Live deployment can be deferred or run only after explicit approval because repo policy requires approval for `just apply`.

## Alternatives Considered

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Convert only Hermes steady-state configuration to direct Ansible SSH while keeping `lxc_ready` on Proxmox | Aligns with the corrected operator model; limited scope; preserves Proxmox lifecycle readiness; validates the pattern before broad migration | Requires refactoring the Hermes role away from `pct exec`/`pct push`; may reveal missing SSH/user assumptions in BWS configuration | **Selected** |
| Convert all LXC service roles in one pass | Fully aligns every service immediately | Large cross-cutting migration across Technitium, Forgejo, Infisical, Forgejo Runner, and Hermes; higher risk; harder to validate in one focused session | Rejected for MVP; defer after Hermes pattern proves out |
| Keep current Proxmox-mediated Ansible and only document direct operator SSH | Minimal code change | Leaves implementation contradicting policy; encourages agents to keep using Proxmox as the default control path | Rejected: user explicitly called this half-measure out |
| Manage Hermes direct config with ad hoc SSH scripts instead of Ansible | Simple for one-off fixes | Creates another configuration surface; weak idempotence; bypasses repo workflow | Rejected: repo doctrine says service orchestration belongs in Ansible |

The selected and rejected medium/large approaches reflect a service-management pattern choice. The opposite pattern, Proxmox-mediated `pct exec`, remains correct for recovery when direct SSH is broken, for LXC lifecycle checks before the guest is reachable, or for bootstrapping a newly-created container before SSH is ready.

## Objective

Refactor the Hermes Ansible workflow so Proxmox is used only for Hermes LXC readiness and Hermes steady-state configuration is applied directly to the Hermes service host over SSH using normal Ansible modules where practical.

## MVP Boundary

The smallest user-visible outcome is: a fresh agent or operator can run the Hermes playbook and see that it targets `hermes` directly for service configuration, with no steady-state `pct exec`/`pct push` inside the Hermes role, while repo validation and direct Hermes Ansible connectivity checks pass.

This is sufficient because it fixes the specific policy/implementation mismatch for Hermes without turning the plan into a broad all-services migration. The scope is small enough for one focused implementation session.

## Explicit Deferrals

- Converting Technitium, Forgejo, Forgejo Runner, Infisical, and Caddy proxy roles to direct service SSH.
- Adding a new non-root Hermes operator account if private inventory currently uses root; this plan can support whichever configured direct Ansible user already exists, but creating/changing users is separate live access design.
- Deploying or integrating Menos into Hermes.
- Running `just apply` or live Hermes reconfiguration without explicit user approval.
- Changing DNS, firewall, Proxmox resource shape, VMID/LXC IDs, or service IPs.

## Project Context

- **Language**: Infrastructure repository with Justfile, Bash/Python helper scripts, OpenTofu HCL, Ansible YAML, and Python unit tests.
- **Test command**: `just validate`
- **Lint command**: included in `just validate` via ShellCheck/TFLint/ansible-lint/public-safety checks. Focused checks may use `scripts/python.sh -m unittest ...` and `scripts/run-infra.sh ... ansible-playbook --syntax-check ...`.
- **Existing specs**: `.specs/archive/onramp-host-pilot`, `.specs/archive/searxng-podman-runtime`; this plan uses `.specs/direct-hermes-ansible` to avoid collision.

## Automation Plan

List every operational step required to complete this plan and how it is automated. Prefer scripts, playbooks, wrappers, and repeatable commands over manual steps. Any manual-only step must include why it cannot be safely automated.

| Operation | Command/wrapper | Credentials | Evidence |
|-----------|-----------------|-------------|----------|
| Preflight | `git status --short --untracked-files=all && rg -n "pct (exec|push|enter)|hosts: pve" infra/ansible/playbooks/hermes.yml infra/ansible/roles/hermes` | None | Terminal output showing baseline and target patterns |
| Inventory/direct connectivity check | `INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c 'ansible-inventory -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py --graph; ansible -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py hermes -m ping'` | SSH keys and BWS-rendered configuration from existing approved mechanisms | Terminal output; no secrets printed |
| Implement | Targeted edits to `infra/ansible/playbooks/hermes.yml`, `infra/ansible/roles/hermes/tasks/main.yml`, templates/tests as needed | None | Git diff and focused tests |
| Task-specific validate | `scripts/run-infra.sh bash -euo pipefail -c 'ansible-playbook -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py --syntax-check infra/ansible/playbooks/hermes.yml'` | BWS-rendered inventory only; no mutation | Syntax-check exits 0 |
| Pattern validate | `rg -n "pct (exec|push|enter)" infra/ansible/roles/hermes infra/ansible/playbooks/hermes.yml; test $? -eq 1` | None | No matches for steady-state `pct` in Hermes role/playbook except allowed `lxc_ready` role outside Hermes role |
| Repo-wide validate | `just validate` | BWS-rendered configuration and Docker tooling | Exits 0 |
| Deployment | Not part of MVP. If user explicitly approves live reconfiguration, use `just plan` then `just apply` per repo policy. | BWS secrets plus SSH/API credentials through existing approved mechanisms | Apply output and post-apply `ansible hermes -m ping`; not required for archive |
| Rollback | `git restore --source=HEAD -- <changed tracked files>` before commit, or `git revert <commit>` after commit | None | Git status clean or revert commit present |

## Execution Checklist

This checklist is the durable resume ledger for `/do-it`. Every executable task, validation gate, and final completion gate has exactly one matching checkbox. Checked means verified complete; unchecked means pending, in-progress, blocked, or invalidated.

`/do-it` must mark each item `[x]` immediately after that item passes its required verification and before starting any dependent or next sequential step. `/review-it` must preserve checked state, add unchecked items for new executable work, and never mark implementation or validation work complete.

### Wave 1

- [ ] T1: Verify current Hermes inventory and direct SSH assumptions
  - Status: pending
  - Evidence: --
- [ ] T2: Refactor Hermes playbook to split Proxmox readiness from direct Hermes configuration
  - Status: pending
  - Evidence: --
- [ ] V1: Validate wave 1
  - Status: pending
  - Evidence: --

### Wave 2

- [ ] T3: Refactor Hermes role tasks to run directly on Hermes
  - Status: pending
  - Evidence: --
- [ ] T4: Update tests/docs for direct Hermes Ansible access policy
  - Status: pending
  - Evidence: --
- [ ] V2: Validate wave 2
  - Status: pending
  - Evidence: --

### Final Gates

- [ ] F1: Task-specific verification complete
  - Status: pending
  - Evidence: --
- [ ] F2: Repo-wide validation complete
  - Status: pending
  - Evidence: --
- [ ] F3: Manual validation not required or completed
  - Status: pending
  - Evidence: --
- [ ] F4: Deployment validation complete or not required
  - Status: pending
  - Evidence: --
- [ ] F5: Archive preflight complete
  - Status: pending
  - Evidence: --

## Task Breakdown

| # | Task | Files | Type | Model | Agent | Depends On |
|---|------|-------|------|-------|-------|------------|
| T1 | Verify current Hermes inventory and direct SSH assumptions | 0-2 | research | small | ansible-specialist | -- |
| T2 | Refactor Hermes playbook to split Proxmox readiness from direct Hermes configuration | 1 | feature | medium | ansible-specialist | -- |
| V1 | Validate wave 1 | -- | validation | medium | validation-lead | T1, T2 |
| T3 | Refactor Hermes role tasks to run directly on Hermes | 2-4 | architecture | large | engineering-lead | V1 |
| T4 | Update tests/docs for direct Hermes Ansible access policy | 2-5 | feature | medium | qa-engineer | V1 |
| V2 | Validate wave 2 | -- | validation | large | validation-lead | T3, T4 |

## Execution Waves

### Wave 1 (parallel)

**T1: Verify current Hermes inventory and direct SSH assumptions** [small] -- ansible-specialist
- Description: Confirm that dynamic inventory exposes a `hermes` group/host with an `ansible_host` derived from private tfvars and that direct Ansible SSH to Hermes is possible or identify the exact private inventory gap.
- Files: Read-only expected; if a tracked test fixture needs adjustment, use `tests/test_tfvars_inventory.py`.
- Acceptance Criteria:
  1. [ ] Inventory includes a `hermes` group and host with direct `ansible_host`.
     - Verify: `scripts/run-infra.sh bash -euo pipefail -c 'ansible-inventory -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py --graph | grep -A3 hermes'`
     - Pass: Output shows a `hermes` group and `hermes_lxc` or equivalent Hermes host.
     - Fail: Dynamic inventory is not producing Hermes; inspect `infra/ansible/inventory/tfvars.py`, `settings.local.json`, and private tfvars without printing secrets.
  2. [ ] Direct Ansible ping to Hermes works, or the failure is documented as a BWS configuration/access gap before refactor proceeds.
     - Verify: `INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c 'ansible -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py hermes -m ping'`
     - Pass: Hermes returns `SUCCESS` and `ping: pong`.
     - Fail: SSH/auth/name resolution fails; do not switch live deployment expectations until the private direct access issue is resolved or explicitly documented.

**T2: Refactor Hermes playbook to split Proxmox readiness from direct Hermes configuration** [medium] -- ansible-specialist
- Description: Change `infra/ansible/playbooks/hermes.yml` to keep a first play on `pve` for `lxc_ready`, then add a second play on `hermes` with `become: true` running the `hermes` role directly. The Hermes role must no longer depend on `pct` being available on its target host.
- Files: `infra/ansible/playbooks/hermes.yml`; possibly `infra/ansible/playbooks/site.yml` only if orchestration references need updating.
- Acceptance Criteria:
  1. [ ] Hermes playbook contains separate Proxmox readiness and direct Hermes configuration plays.
     - Verify: `python - <<'PY'
from pathlib import Path
text = Path('infra/ansible/playbooks/hermes.yml').read_text()
assert 'hosts: pve' in text
assert 'lxc_ready' in text
assert 'hosts: hermes' in text
assert 'become: true' in text
print('hermes-playbook-split-ok')
PY`
     - Pass: Prints `hermes-playbook-split-ok`.
     - Fail: Playbook still only targets `pve` or lacks direct Hermes configuration play.
  2. [ ] Hermes playbook syntax is valid with the repo inventory.
     - Verify: `scripts/run-infra.sh bash -euo pipefail -c 'ansible-playbook -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py --syntax-check infra/ansible/playbooks/hermes.yml'`
     - Pass: Syntax check exits 0 and reports the Hermes playbook.
     - Fail: Fix syntax/inventory/variable errors before continuing.

### Wave 1 -- Validation Gate

**V1: Validate wave 1** [medium] -- validation-lead
- Blocked by: T1, T2
- Checks:
  1. Run acceptance criteria for T1 and T2.
  2. `scripts/python.sh -m unittest tests.test_tfvars_inventory tests.test_settings` -- all tests pass.
  3. `scripts/run-infra.sh bash -euo pipefail -c 'ansible-playbook -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py --syntax-check infra/ansible/playbooks/hermes.yml'` -- exits 0.
  4. Cross-task integration: direct inventory group used by the new Hermes play exists and is reachable or the plan is explicitly blocked on direct SSH access.
- On failure: create a fix task, re-validate after fix.

### Wave 2

**T3: Refactor Hermes role tasks to run directly on Hermes** [large] -- engineering-lead
- Blocked by: V1
- Description: Convert Hermes role steady-state tasks from `pct exec`/`pct push` to normal direct Ansible operations. Use `ansible.builtin.apt` for packages where practical, `template`/`copy` directly to final destinations, `systemd` for services, direct `command`/`shell` only when an idempotent module is not practical, and keep `changed_when`/`failed_when` accurate. Preserve no-log handling for secret env files.
- Files: `infra/ansible/roles/hermes/tasks/main.yml`, `infra/ansible/roles/hermes/handlers/main.yml`, `infra/ansible/roles/hermes/templates/*.j2` as needed.
- Acceptance Criteria:
  1. [ ] Hermes role/playbook no longer contains steady-state Proxmox `pct exec`, `pct push`, or `pct enter` calls.
     - Verify: `rg -n "pct (exec|push|enter)" infra/ansible/roles/hermes infra/ansible/playbooks/hermes.yml; test $? -eq 1`
     - Pass: `rg` finds no matches in Hermes role/playbook. `lxc_ready` may still use `pct` outside the Hermes role.
     - Fail: Any match indicates remaining Proxmox-mediated steady-state config; convert or justify outside the Hermes role.
  2. [ ] Secret-bearing Hermes env tasks remain protected.
     - Verify: `scripts/python.sh -m unittest tests.test_ansible_safety`
     - Pass: Tests pass, including no-log and Caddy validation safety checks.
     - Fail: Restore `no_log: true` for secret tasks or adjust tests only if behavior is safer and still public-safe.
  3. [ ] Direct Hermes role syntax validates.
     - Verify: `scripts/run-infra.sh bash -euo pipefail -c 'ansible-playbook -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py --syntax-check infra/ansible/playbooks/hermes.yml'`
     - Pass: Exits 0.
     - Fail: Fix module arguments, variable assumptions, or inventory targeting.

**T4: Update tests/docs for direct Hermes Ansible access policy** [medium] -- qa-engineer
- Blocked by: V1
- Description: Add or update tests and docs so future changes do not regress Hermes back to Proxmox-mediated steady-state configuration. Keep examples public-safe and generic.
- Files: likely `tests/test_ansible_safety.py`, `AGENTS.md`, `docs/onramp-host-runbook.md` or `README.md` only if necessary. Avoid unnecessary broad docs churn.
- Acceptance Criteria:
  1. [ ] A regression check fails if Hermes role/playbook reintroduces `pct exec`, `pct push`, or `pct enter` for steady-state configuration.
     - Verify: `scripts/python.sh -m unittest tests.test_ansible_safety`
     - Pass: Tests pass with the new regression check.
     - Fail: Add focused test coverage or correct the role.
  2. [ ] Documentation/instructions state direct service access is normal and Proxmox access is lifecycle/recovery only.
     - Verify: `rg -n "direct service access|pct enter|Proxmox.*recovery|ssh <user>@hermes.example" AGENTS.md README.md docs -g '*.md'`
     - Pass: Output contains public-safe guidance with no real hostnames/IPs/secrets.
     - Fail: Update docs with generic examples only.

### Wave 2 -- Validation Gate

**V2: Validate wave 2** [large] -- validation-lead
- Blocked by: T3, T4
- Checks:
  1. Run acceptance criteria for T3 and T4.
  2. `scripts/python.sh -m unittest tests.test_ansible_safety tests.test_tfvars_inventory tests.test_settings` -- all tests pass.
  3. `scripts/run-infra.sh bash -euo pipefail -c 'ansible-playbook -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py --syntax-check infra/ansible/playbooks/hermes.yml'` -- exits 0.
  4. `rg -n "pct (exec|push|enter)" infra/ansible/roles/hermes infra/ansible/playbooks/hermes.yml; test $? -eq 1` -- confirms no steady-state Hermes `pct` usage.
  5. Cross-task integration: tests and documentation match the new playbook/role structure.
- On failure: create a fix task, re-validate after fix.

## Dependency Graph

```
Wave 1: T1, T2 (parallel) → V1
Wave 2: T3, T4 (parallel after V1) → V2
Final Gates: V2 → F1 → F2 → F3 → F4 → F5
```

## Success Criteria

1. [ ] Hermes playbook uses Proxmox only for readiness and configures Hermes directly over Ansible SSH.
   - Verify: `python - <<'PY'
from pathlib import Path
play = Path('infra/ansible/playbooks/hermes.yml').read_text()
role = Path('infra/ansible/roles/hermes/tasks/main.yml').read_text()
assert 'hosts: pve' in play and 'lxc_ready' in play
assert 'hosts: hermes' in play and 'become: true' in play
assert 'pct exec' not in play and 'pct push' not in play and 'pct enter' not in play
assert 'pct exec' not in role and 'pct push' not in role and 'pct enter' not in role
print('direct-hermes-ansible-ok')
PY`
   - Pass: Prints `direct-hermes-ansible-ok`.
2. [ ] Direct Hermes inventory path is usable.
   - Verify: `INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c 'ansible -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py hermes -m ping'`
   - Pass: Hermes returns `SUCCESS` and `ping: pong`, or the plan is explicitly marked blocked on private direct SSH configuration before archive.
3. [ ] Repo validation passes.
   - Verify: `just validate`
   - Pass: Exits 0 with public safety, OpenTofu validation, tests, Ansible syntax/lint, and values wiring checks passing.

## Validation Contract

`/do-it` must satisfy this contract before reporting the plan complete or archiving it.

### Automation completeness

- Required: yes
- `/do-it` must be able to run all agent-runnable validation steps through documented commands, scripts, playbooks, or wrappers.
- Credentials are expected through existing approved mechanisms: BWS configuration and runtime secrets, SSH keys copied into the infra container via `INFRA_COPY_SSH_KEYS=true`, and Docker Compose tooling. Excluded `values/` data is not an inventory or credential source.
- Manual-only steps are not required for the MVP. If direct Hermes SSH credentials are missing, mark the plan blocked with the failing command rather than inventing manual validation.

### Required automated validation

1. [ ] Run the strongest repo-wide validation command for this project.
   - Command: `just validate`
   - Pass: exits 0 with no failed validation stages.
   - Fail: do not archive; update execution status with the failing command and next fix.

2. [ ] Run task-specific verification from every acceptance criterion above.
   - Command: see each task's `Verify:` command.
   - Pass: every acceptance criterion passes as written.
   - Fail: create/fix a task, rerun affected checks, then rerun repo-wide validation.

3. [ ] Run direct Hermes connectivity verification.
   - Command: `INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c 'ansible -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py hermes -m ping'`
   - Pass: Hermes returns `SUCCESS` and `ping: pong`.
   - Fail: block archive unless the user explicitly decides direct SSH setup is a separate prerequisite; do not fall back to Proxmox `pct` as a success path.

### Manual validation

Manual validation is exceptional. It should be `Required: no` unless the plan includes destructive operations, data-loss risk, irreversible external side effects, shared/work production impact, paid/billing/data-costing resources, secret exposure risk, hardware/physical checks, or genuinely subjective user judgment that cannot be replaced by safe automation.

- Required: no
- Justification: Automated static checks, Ansible syntax/lint, direct Ansible ping, and repo-wide validation are sufficient for this non-destructive source refactor. Live apply requires explicit approval but is not required for archive.
- Steps:
  1. None.

If manual validation is not required, `/do-it` may mark the manual gate complete after recording why automated evidence is sufficient.

### Deployment validation

- Required: no for MVP archive.
- Procedure: None for archive. If the user explicitly approves live deployment, run `just plan`, review the plan summary, then run `just apply` only after approval. After apply, rerun direct `ansible hermes -m ping` and `just plan` to confirm no drift.

If deployment is skipped, the plan may still archive because the MVP is a source-level Ansible architecture refactor with direct connectivity and repo validation. If deployment is attempted and fails, `/do-it` must not archive until the failure is resolved or deployment is explicitly removed from the active execution scope.

### Archive rule

`/do-it` may archive this plan only after all required automated validation, task-specific verification, direct Hermes connectivity verification, and repo-wide validation pass. Do not require manual validation merely to increase confidence in non-destructive behavior that automated checks already cover.

## Telemetry & Evidence Contract

Future `/do-it` runs should record non-secret evidence in terminal output and, if using durable artifacts, under `.specs/direct-hermes-ansible/evidence/`. Do not record secrets, private IPs/domains, SSH keys, tokens, or unredacted private inventory.

Machine-readable evidence records should use JSON Lines with these fields:

```json
{"episode_id":"direct-hermes-ansible","phase_id":"wave-1","task_id":"T1","validation_command":"ansible-inventory ... --graph","status":"pending|pass|fail|blocked","archive_status":"not-ready|ready|archived","started_at":"ISO-8601","completed_at":"ISO-8601","evidence":"non-secret terminal summary or artifact path"}
```

Required fields for each record:

- `episode_id`: `direct-hermes-ansible`
- `phase_id`: `wave-1`, `wave-2`, or `final-gates`
- `task_id`: one of `T1`, `T2`, `V1`, `T3`, `T4`, `V2`, `F1`, `F2`, `F3`, `F4`, `F5`
- `validation_command`: exact command or short label for non-command checks
- `status`: `pending`, `pass`, `fail`, or `blocked`
- `archive_status`: `not-ready`, `ready`, or `archived`
- `started_at`: ISO-8601 timestamp
- `completed_at`: ISO-8601 timestamp or `null` while in progress
- `evidence`: non-secret command summary or artifact path

### Plan review data contract

- `plan_profile`: `ansible-service-access-refactor`
- `review_panel_decision`: expected before implementation if the user chooses `/review-it`; not required before `/do-it` unless user requests review
- `expected_reviewer_count`: 3
- `selected_reviewer_personas`: `ansible-specialist`, `security-reviewer`, `devops-pro`
- `selection_reasons`: Ansible target/role refactor; direct SSH/security boundary; live service operations discipline
- `complexity_score`: 7/10
- `risk_score`: 5/10
- `expected_high_risk_areas`: preserving secret `no_log`, avoiding real BWS configuration or excluded private data in tracked docs/tests, maintaining idempotence, avoiding accidental live mutation, ensuring direct SSH inventory works without Proxmox fallback

## Handoff Notes

- The direct-service rule is now explicit in `AGENTS.md`; implementation should make Hermes comply instead of treating it as documentation-only guidance.
- Do not use Proxmox `pct exec` as a substitute for a failed direct Hermes SSH check. A failed direct check is a finding to fix or explicitly block on.
- Keep `lxc_ready` on `pve`; it is lifecycle readiness, not steady-state service configuration.
- If private direct SSH access to Hermes is currently root-only, this plan can still proceed with the configured Ansible user. A dedicated non-root Hermes operator user is a separate design/deployment task.
- No `just apply` is required for plan archive. If live deployment is desired, ask for explicit approval first.
