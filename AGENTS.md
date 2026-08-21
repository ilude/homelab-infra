# AGENTS.md

Guidance for coding agents working in this repository.

## Overview

This repo is a generic, reusable homelab infrastructure runbook for Proxmox LXCs and the shared onramp-host VM running Technitium DNS, Caddy, Forgejo, Infisical, Hermes, FreeLLMAPI, and other managed services.

The canonical checkout is the `modules/homelab-infra/` submodule of the dotfiles repository. This repository retains its own history, branches, validation, commits, and remote; the dotfiles parent pins an exact commit.

Repository collaboration boundaries:

- Base current implementation decisions on deployed tooling and repositories available in the active workspace. Architecture documents describing a future repository, control plane, or migration target do not make that tooling operational and must not redirect current work to a nonexistent path. When no separate app-platform deployment tooling exists, this repository owns deployment of requested Docker services to its managed hosts using its existing Ansible, BWS, Caddy, and service-state patterns. Preserve a documented future migration boundary without treating it as a current blocker.
- The sibling `../onclave/` module owns Onclave product code, protocols, services, and provider-neutral application contracts. Its checkout must remain attached to and tracking `origin/feature/v2-broker-core` unless the user explicitly requests a branch change. This repository consumes those contracts and owns host placement, infrastructure resources, deployment orchestration, and live configuration.
- The dotfiles parent at `../..` owns workstation setup and Pi runtime wiring. Do not put infrastructure implementation, BWS configuration, or excluded private data in the parent repository.
- BWS owns configuration families and runtime secrets; SeaweedFS owns encrypted OpenTofu state. The nested private `values/` repository stores only excluded backups, artifacts, dumps, and mutable service-state data. Remote runtime backups may remain on managed hosts. Neither the Onclave sibling nor the dotfiles parent may become a second store for these contracts.
- For coordinated changes, edit and validate each owning repository independently. Commit and push homelab-infra changes before the dotfiles parent updates its submodule pointer. Commit `values/` separately to its private remote when requested; never stage it through this public repository.

Tracked source must stay public-safe and free of the operator's real network/domain specifics. Use placeholders such as `example.internal`, `git.example.internal`, `apps.example.net`, and RFC 5737 addresses like `192.0.2.0/24` in tracked files.

BWS configuration families hold real Proxmox endpoints, LAN IPs, DNS zones/records, hostnames, service settings, and runtime secrets. SeaweedFS stores encrypted OpenTofu state. In this deployment, expect `values/` to have its own private Forgejo remote; do not treat it as part of the public runbook repo.

The ignored local `settings.local.json` contains only the BWS project/API locator. `HOMELAB_SETTINGS` in BWS owns the excluded-data repository remote and enabled service list. `scaffold/` remains the public-safe fixture and migration source; it is not the source of private configuration.

## Layout

- `infra/opentofu/` — OpenTofu configuration for Proxmox resources.
- `infra/ansible/` — Ansible playbooks, dynamic inventory, and service configuration helpers.
- `scaffold/` — public-safe values repo starter files.
- `scripts/` — workflow helpers and explicit live-mutation helpers.
- `tools/` — Docker tooling image files.
- `values/` — ignored nested private Git repo for excluded backups, artifacts, dumps, and mutable service-state data.

## Safety Rules

- Do not run `tofu apply`, `terraform apply`, `destroy`, import, or state surgery without explicit user approval.
- BWS owns configuration families and runtime secrets. SeaweedFS owns encrypted OpenTofu state. Do not recreate those sources under `values/`.
- Do not commit secrets, live domains/IPs/hostnames, `values/`, `settings.local.json`, state files, plans, or generated local credentials.
- Keep configuration and runtime secrets in BWS. Keep only excluded backups, artifacts, dumps, and mutable service-state data in `values/` or another approved private store; do not add another sensitive-data directory to this repo.
- Treat DNS, Forgejo, and HTTPS/SSH endpoints as critical infrastructure. Prefer reviewed plans over ad hoc mutation.
- Treat Menos as an experimental single-user transcript service, not production-critical infrastructure. For Menos changes, default to one current verified backup, one explicit rollback boundary, and direct checks of the affected user workflow. Do not require multi-day soak periods, formal approval or evidence packets, continuous monitoring, or production-style operational controls unless the operator explicitly requests them or a concrete destructive or data-loss risk requires them.
- Treat review findings as a backlog, not one apply batch, unless the user explicitly requests implementing those findings. Keep OS migrations, stateful replacements, hardening, backup redesign, and orchestration refactors in separate validated waves, but complete all requested waves without additional approval.
- Replace at most one independent stateful service per plan/apply until its backup, restore path, direct endpoint, and persisted state are verified. Do not use `INFRA_ALLOW_STATEFUL_BATCH=1` except for an explicitly reviewed exception.
- A failed live operation enters incident mode only when it mutated state, degraded a service, or left the mutation boundary unknown. Then stop broad applies, parallel recovery, and unrelated refactoring; preserve healthy services; recover one affected service directly; and resume rollout only after its original endpoint and state checks pass. A fail-closed precondition or validation failure proven to occur before target connection or mutation does not enter incident mode; correct the runner and use the targeted check needed for a safe retry.
- Service version changes must use managed pins and `just update` when a service has update support, followed by the approved targeted public deployment path appropriate to the changed resources. Use `just plan`/`just apply` only when infrastructure resources change, and run one final `just validate` after the complete request or active plan is otherwise finished. Do not rerun upstream installers or ad hoc upgrade commands as the normal update mechanism.
- Prefer direct service access for service diagnostics and operator guidance. Do not default to SSHing into the Proxmox host and then using `pct exec`/`pct enter` when a service has its own LAN IP, DNS name, SSH daemon, or HTTPS endpoint. Proxmox host access is for Proxmox/LXC lifecycle diagnostics, console recovery, or cases where direct service access is unavailable or explicitly requested.
- Do not mutate production routers/firewalls unless explicitly requested.
- If changing service IPs, hostnames, SSH ports, proxy topology, or service-selection behavior, update only the affected contract surfaces among scaffold examples, BWS families, README, and migration notes. Do not touch unaffected surfaces solely for completeness.

## Commands

Preferred workflow:

```bash
just setup      # first checkout only; verifies BWS and prepares excluded-data storage
just update     # when checking or changing managed version pins
just plan       # before infrastructure resource changes
just apply      # after approval when the full infrastructure workflow is required
just validate   # once, as the final gate for the complete request or active plan
```

Validation performed by `just validate` includes public-safety checks, OpenTofu format/validate, TFLint, ShellCheck, Python compile/unit checks, BWS snapshot validation, the excluded-data boundary, Technitium DNS JSON validation, Ansible syntax, and ansible-lint. Run it exactly once after all implementation and live work for the complete request or active plan is otherwise finished. Do not run it between tasks, fixes, retries, or intermediate milestones; use only the targeted checks needed to continue safely during execution.

Treat `[private]` just recipes as implementation details for other recipes only. Do not invoke private recipes directly during normal agent work, even for validation. Use public recipes for complete workflows. During execution, use the targeted public script, playbook, or test needed to continue safely; do not substitute a private recipe or an intermediate `just validate`.

Containerized tooling is used for Windows/local consistency. `scripts/run-infra.sh` renders validated BWS families into an ephemeral tooling-container snapshot and removes it after the command. New workflow code must consume that snapshot contract rather than recreating or sourcing configuration under `values/`.

Forgejo Actions deployment monitoring helpers exist as private workflow plumbing for the private values repo. Agents must not invoke those private recipes directly. If monitoring is needed, ask the operator for the approved public workflow or explicit instructions. The underlying monitor redacts logs by default; do not print unredacted logs unless explicitly requested.

## Design Doctrine

- Do not ask the operator for values or credentials the repo can derive or recover from authorized local state. BWS is authoritative for configuration families and runtime secrets, and SeaweedFS is authoritative for encrypted OpenTofu state. `values/` is authoritative only for excluded backups, artifacts, dumps, and mutable service-state data.
- Before asking the operator for credentials, exhaust authorized recovery sources without exposing secret values: current BWS records, approved secret migrations, excluded backup artifacts when relevant, and prior task artifacts/logs. Compare or test candidates programmatically with redacted output. If this automation previously generated, rotated, restored, or stored the credential, treat recovery as the agent's responsibility. Ask the operator only after documenting that these sources were checked and no valid candidate remains. Never ask the operator to paste credentials into chat.
- The BWS `HOMELAB_TERRAFORM_TFVARS` family is the source of truth for infrastructure-derived service shape: VMIDs, Proxmox networking, service LAN IPs, hostnames, and OpenTofu inputs. Ansible inventory should consume the rendered family through `infra/ansible/inventory/tfvars.py` instead of duplicating it by hand.
- Keep service orchestration in Ansible and resource declaration in OpenTofu. Do not use OpenTofu `local-exec` for host or service configuration; add an Ansible playbook/role and wire it into `just apply` in the correct order.
- No breadcrumbs, comment-only placeholder files, dead wrappers, or permanent duplicate knobs. When behavior moves, update only the affected BWS migration, scaffold, documentation, and test surfaces, and remove the old surface. Do not add or modify unaffected surfaces solely for completeness.
- Prefer small Python helpers for local data transformation and Ansible/OpenTofu integration over shell glue. Keep shell wrappers only when they are a narrow tooling boundary.
- Onclave application secrets belong in Bitwarden Secrets Manager. `BITWARDEN_ACCESS_KEY` is the controller bootstrap credential and must not be copied to managed hosts. Keep only the non-secret BWS project/API locator in ignored `settings.local.json`; do not retain Onclave credentials in `values/`. Other generated runtime secrets belong in BWS runtime families, must be idempotent, and must never be printed in logs or responses.

## Workflow

1. Keep tracked edits generic/public-safe.
2. Put configuration-family and runtime-secret changes in BWS; put only excluded backups, artifacts, dumps, and mutable service-state changes in `values/`, committing them with `git -C values ...` to the private values remote when requested.
3. During execution, use only targeted checks needed to continue safely; do not run `just validate` between tasks, fixes, retries, or intermediate milestones.
4. Before applying infrastructure resource changes, run `just plan` and summarize creates/changes/destroys. Do not require a global infrastructure plan for approved targeted service configuration or incident recovery that does not change infrastructure resources.
5. Apply only after explicit approval using `just apply` when the full infrastructure workflow is required; it verifies `tfplan.meta.json` before applying. A direct request to fix deployed or live behavior counts as explicit approval for the bounded plan, including its listed targeted scripts, playbooks, plan, and apply actions, so do not ask again while target, scope, intended outcome, and destructive impact remain materially unchanged. Ask again only when the reviewed plan introduces destructive action, stateful replacement, router/firewall mutation, or another material boundary change.
6. Use the user-facing `just` recipes (`setup`, `validate`, `plan`, `apply`) for complete workflows. During approved targeted service work or incident recovery, use the specific public service script or Ansible playbook rather than expanding the operation into a global plan/apply cycle.
7. Do not run `[private]` just recipes directly. If a narrow diagnostic command is needed to investigate a failure, state why before running it and do not present it as repo validation.
8. Do not add new public `just` recipes unless the user explicitly asks for that exact command. Prefer scripts or internal helpers for implementation details, and keep the public command surface limited to requested commands.
9. If saved infrastructure plan verification fails, rerun `just plan` instead of reusing or editing saved plan files.
10. For in-LXC service configuration, use the appropriate public service script or Ansible playbook. Use `just apply` only when the complete infrastructure workflow is required.
11. For live diagnostics, use the service's direct endpoint first: SSH to the service DNS name/IP with its configured service user, or use the service HTTPS URL. Use Proxmox `pct exec`/`pct enter` only when debugging Proxmox/container lifecycle, recovering a broken service that cannot be reached directly, or following explicit operator instructions.
12. After all implementation and live work for the complete request or active plan is otherwise finished, run `just validate` exactly once as the final validation gate.

## Service Access Pattern

Services are intended to be accessible directly on the LAN by their service DNS names or IPs. Do not present Proxmox host SSH plus `pct enter` as the normal operator access path for services.

Examples:

- Hermes operator shell access should be described as direct SSH to the Hermes service endpoint and configured user, e.g. `ssh <user>@hermes.example.internal`, not `ssh <proxmox-host>` followed by `pct enter`.
- Browser access should use the service-local HTTPS endpoint, e.g. `https://hermes.example.internal`.
- Proxmox host access is appropriate for OpenTofu/Ansible bootstrap, LXC lifecycle checks, console recovery, or when direct SSH/HTTPS is unavailable and the operator approves that diagnostic path.

## Service HTTPS / Caddy Pattern

This repo generally uses service-local Caddy instances rather than one central reverse proxy.

- Technitium LXC runs its own Caddy for the DNS/Technitium UI.
- Forgejo LXC runs its own Caddy for Forgejo.
- New browser-facing first-class LXC services should usually follow the same pattern: app plus Caddy in the same LXC, with Caddy proxying to the app on loopback. Hermes follows this pattern. Containerized app services that belong on `onramp_host`, such as Infisical onramp and FreeLLMAPI, should use the shared onramp Caddy instance with per-service snippets under `/etc/caddy/sites.d/`.
- Caddy uses Cloudflare DNS-01 ACME via `CF_DNS_API_TOKEN`, so multiple service-local Caddy instances can obtain certificates without competing for HTTP-01 port 80 routing.
- Avoid turning the Technitium/DNS LXC into a general ingress proxy unless there is an explicit design reason. `caddy_extra_vhosts` exists, but should not be the default for new first-class services.

## DNS Management

Technitium DNS records are synced by `infra/ansible/playbooks/technitium-dns.yml` during `just apply`, after OpenTofu creates the LXC and Ansible installs/configures Technitium. Do not call the Technitium API from OpenTofu resources.

The Ansible playbook invokes `infra/ansible/scripts/apply-technitium-dns.py`; keep DNS service orchestration in Ansible.

The intended pattern is hybrid DNS:

- Technitium Forwarder zones hold explicit static records.
- Unknown names in those zones forward to existing internal resolvers.
- The gateway should remain focused on DHCP/routing/firewall and eventually point DHCP DNS to Technitium.

Technitium DNS sync runtime settings belong in the BWS `HOMELAB_ENV` family, while `DNS_RECORDS_FILE` is derived from the ephemeral BWS snapshot. Keep application runtime workflow variables out of OpenTofu variables unless OpenTofu directly uses them.

Technitium service updates must use the managed version/checksum workflow rather than relying on `curl https://download.technitium.com/dns/install.sh | bash` after first install. The upstream portable tarball URL is mutable, so the workflow reads version metadata from the Technitium GitHub release, stores the desired version and SHA256 in the BWS inventory family, optionally caches the tarball under ignored `values/artifacts/technitium/`, and lets Ansible update only when the installed marker differs from the pin. Do not add new ad hoc Technitium installer reruns as an update path.

## Response hygiene

Do not print token values, generated passwords, real domains/IPs/hostnames, or real local DNS inventory in responses or logs. When summarizing live checks, describe outcomes without exposing site-specific inventory unless the user explicitly requests it.
