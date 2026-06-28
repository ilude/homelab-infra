# AGENTS.md

Guidance for coding agents working in this repository.

## Overview

This repo is a generic, reusable homelab infrastructure runbook for Proxmox LXCs running Technitium DNS, Caddy, and Forgejo.

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

- `infra/opentofu/` — OpenTofu configuration and Technitium DNS helper.
- `infra/ansible/` — Ansible playbooks and roles for in-LXC service configuration.
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

Containerized tooling is used for Windows/local consistency. Project commands parse `values/.env` as dotenv-style data through `scripts/parse-env.py` / `scripts/run-infra.sh` and run inside the Docker Compose `infra` service. Do not source `values/.env` directly in new workflow code.

## Workflow

1. Keep tracked edits generic/public-safe.
2. Put site-specific changes in `values/` only; commit/push them with `git -C values ...` to the private values remote when requested.
3. Run `just validate` after source or scaffold changes.
4. If a plan is requested, run `just plan` and summarize creates/changes/destroys.
5. Apply only after explicit approval using `just apply`; it verifies `tfplan.meta.json` before applying.
6. Use the user-facing `just` recipes (`setup`, `validate`, `plan`, `apply`) rather than ad hoc shell sequences for normal operations.
7. If plan verification fails, rerun `just plan` instead of reusing or editing saved plan files.
8. For in-LXC service configuration, prefer Ansible playbooks via `just apply` over ad hoc shell changes.

## DNS Management

`infra/opentofu/dns.tf` uses `terraform_data` to run `infra/opentofu/scripts/apply-technitium-dns.py` against `values/dns-records.local.json` via `var.dns_records_file`.

The intended pattern is hybrid DNS:

- Technitium Forwarder zones hold explicit static records.
- Unknown names in those zones forward to existing internal resolvers.
- The gateway should remain focused on DHCP/routing/firewall and eventually point DHCP DNS to Technitium.

A Technitium API token must be supplied through `values/.env` / `TF_VAR_technitium_api_token` before planning or applying DNS resources.

## EdgeRouter helper

`scripts/edgeos-static-host-mapping.sh` mutates a live EdgeRouter config to add a temporary static host mapping.

Run only after explicit approval.

## Response hygiene

Do not print token values, generated passwords, real domains/IPs/hostnames, or real local DNS inventory in responses or logs. When summarizing live checks, describe outcomes without exposing site-specific inventory unless the user explicitly requests it.
