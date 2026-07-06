# AGENTS.md

Guidance for coding agents working in this repository.

## Overview

This repo is a generic, reusable homelab infrastructure runbook for Proxmox LXCs running Technitium DNS, Caddy, Forgejo, Infisical, and Hermes.

Tracked source must stay public-safe and free of the operator's real network/domain specifics. Use placeholders such as `example.internal`, `git.example.internal`, `apps.example.net`, and RFC 5737 addresses like `192.0.2.0/24` in tracked files.

Real Proxmox endpoints, LAN IPs, DNS zones/records, hostnames, credentials, and state belong in `values/`, an ignored nested private Git repo. In this deployment, expect `values/` to have its own private Forgejo remote; do not treat it as part of the public runbook repo.

Private values files include:

- `values/.env`
- `values/terraform.tfvars`
- `values/dns-records.local.json`
- `values/ansible/inventory/local.yml`
- `values/terraform.tfstate*`

`scaffold/` is the public-safe starter template copied into `values/`; keep it generic and sanitized. `settings.example.json` documents the ignored local `settings.local.json` operator settings file used for the private values repo remote and enabled service list.

## Layout

- `infra/opentofu/` — OpenTofu configuration for Proxmox resources.
- `infra/ansible/` — Ansible playbooks, dynamic inventory, and service configuration helpers.
- `scaffold/` — public-safe values repo starter files.
- `scripts/` — workflow helpers and explicit live-mutation helpers.
- `tools/` — Docker tooling image files.
- `values/` — ignored nested private Git repo for site values/state.

## Safety Rules

- Do not run `tofu apply`, `terraform apply`, `destroy`, import, or state surgery without explicit user approval.
- Do not commit secrets, live domains/IPs/hostnames, `values/`, `settings.local.json`, state files, plans, or generated local credentials.
- Keep non-public material in `values/` or outside the checkout; do not add another sensitive-data directory to this repo.
- Treat DNS, Forgejo, and HTTPS/SSH endpoints as critical infrastructure. Prefer reviewed plans over ad hoc mutation.
- Do not mutate production routers/firewalls unless explicitly requested.
- If changing service IPs, hostnames, SSH ports, proxy topology, or service-selection behavior, update scaffold examples, private values as requested, README, and any migration notes together.

## Commands

Preferred workflow:

```bash
just setup      # first checkout only; or: just setup <private-values-repo-url>
just validate
just plan
just apply      # only after explicit approval
```

Validation performed by `just validate` includes public-safety checks, OpenTofu format/validate, TFLint, ShellCheck, Python compile/unit checks, Technitium DNS JSON validation, Ansible syntax, ansible-lint, and private `values/` wiring checks.

Treat `[private]` just recipes as implementation details for other recipes only. Do not invoke private recipes directly during normal agent work, even for validation. Use the public command surface above, primarily `just validate`.

Containerized tooling is used for Windows/local consistency. Project commands parse `values/.env` as dotenv-style data through `scripts/parse-env.py` / `scripts/run-infra.sh` and run inside the Docker Compose `infra` service. Do not source `values/.env` directly in new workflow code.

Forgejo Actions deployment monitoring helpers exist as private workflow plumbing for the private values repo. Agents must not invoke those private recipes directly. If monitoring is needed, ask the operator for the approved public workflow or explicit instructions. The underlying monitor redacts logs by default; do not print unredacted logs unless explicitly requested.

## Design Doctrine

- Do not ask the operator for values the repo can derive from existing private values. `just setup` and migrations should infer deterministic defaults such as service hostnames, VMIDs, LAN IPs, DNS records, inventory vars, and generated local secrets from `values/terraform.tfvars`, `values/.env`, DNS records, and existing inventory.
- `values/terraform.tfvars` is the source of truth for infrastructure-derived service shape: VMIDs, Proxmox networking, service LAN IPs, hostnames, and OpenTofu inputs. Ansible inventory should consume those values through `infra/ansible/inventory/tfvars.py` instead of duplicating them by hand.
- Keep service orchestration in Ansible and resource declaration in OpenTofu. Do not use OpenTofu `local-exec` for host or service configuration; add an Ansible playbook/role and wire it into `just apply` in the correct order.
- No breadcrumbs, comment-only placeholder files, dead wrappers, or permanent duplicate knobs. When behavior moves, add or update migration code for existing `values/` repos, update scaffold/docs/tests, and remove the old surface.
- Prefer small Python helpers for local data transformation and Ansible/OpenTofu integration over shell glue. Keep shell wrappers only when they are a narrow tooling boundary.
- Generated secrets belong in `values/.env`, must be idempotent, and must never be printed in logs or responses.

## Workflow

1. Keep tracked edits generic/public-safe.
2. Put site-specific changes in `values/` only; commit/push them with `git -C values ...` to the private values remote when requested.
3. Run `just validate` after source or scaffold changes.
4. If a plan is requested, run `just plan` and summarize creates/changes/destroys.
5. Apply only after explicit approval using `just apply`; it verifies `tfplan.meta.json` before applying.
6. Use the user-facing `just` recipes (`setup`, `validate`, `plan`, `apply`) rather than private recipes or ad hoc shell sequences for normal operations.
7. Do not run `[private]` just recipes directly. If a narrow diagnostic command is needed to investigate a failure, state why before running it and do not present it as repo validation.
8. Do not add new public `just` recipes unless the user explicitly asks for that exact command. Prefer scripts or internal helpers for implementation details, and keep the public command surface limited to requested commands.
9. If plan verification fails, rerun `just plan` instead of reusing or editing saved plan files.
10. For in-LXC service configuration, prefer Ansible playbooks via `just apply` over ad hoc shell changes.

## Service HTTPS / Caddy Pattern

This repo generally uses service-local Caddy instances rather than one central reverse proxy.

- Technitium LXC runs its own Caddy for the DNS/Technitium UI.
- Forgejo LXC runs its own Caddy for Forgejo.
- New browser-facing first-class services should usually follow the same pattern: app plus Caddy in the same LXC, with Caddy proxying to the app on loopback. Infisical and Hermes follow this pattern.
- Caddy uses Cloudflare DNS-01 ACME via `CF_DNS_API_TOKEN`, so multiple service-local Caddy instances can obtain certificates without competing for HTTP-01 port 80 routing.
- Avoid turning the Technitium/DNS LXC into a general ingress proxy unless there is an explicit design reason. `caddy_extra_vhosts` exists, but should not be the default for new first-class services.

## DNS Management

Technitium DNS records are synced by `infra/ansible/playbooks/technitium-dns.yml` during `just apply`, after OpenTofu creates the LXC and Ansible installs/configures Technitium. Do not call the Technitium API from OpenTofu resources.

The Ansible playbook invokes `infra/ansible/scripts/apply-technitium-dns.py`; keep DNS service orchestration in Ansible.

The intended pattern is hybrid DNS:

- Technitium Forwarder zones hold explicit static records.
- Unknown names in those zones forward to existing internal resolvers.
- The gateway should remain focused on DHCP/routing/firewall and eventually point DHCP DNS to Technitium.

Technitium DNS sync runtime settings belong in `values/.env`: `TECHNITIUM_API_URL`, `TECHNITIUM_API_TOKEN`, and `DNS_RECORDS_FILE`. Keep application runtime workflow variables out of OpenTofu variables unless OpenTofu directly uses them.

## Response hygiene

Do not print token values, generated passwords, real domains/IPs/hostnames, or real local DNS inventory in responses or logs. When summarizing live checks, describe outcomes without exposing site-specific inventory unless the user explicitly requests it.
