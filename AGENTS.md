# AGENTS.md

Guidance for coding agents working in this repository.

## Overview

This repo manages homelab infrastructure with OpenTofu/Terraform, including Technitium DNS, Forgejo, and service bootstrap scripts.

This GitHub repository is intended to be a generic, reusable template/source repo for similar homelab setups. Tracked files must stay public-safe and free of this operator's real network/domain specifics.

Tracked examples should use documentation-safe placeholders such as `example.internal`, `git.example.internal`, `apps.example.net`, and RFC 5737 addresses like `192.0.2.0/24`. Do not commit real domains, LAN IPs, hostnames, DNS zones/records, Proxmox endpoints, usernames, emails, tokens, passwords, or local inventory.

Real Proxmox endpoints, LAN IPs, DNS zones, records, and credentials belong in local gitignored files or the nested private `values/` repo:

- `values/.env`
- `values/terraform.tfvars`
- `values/dns-records.local.json`
- `values/ansible/inventory/local.yml`
- `.env` / `terraform.tfvars` / `dns-records.local.json` only for legacy local workflows
- `ansible/inventory/local.yml`
- `private/`

`values.example/` is the public-safe scaffold for `values/`; keep it generic and sanitized.

## Safety Rules

- Do not run `tofu apply`, `terraform apply`, `destroy`, import, or state surgery without explicit user approval.
- Do not commit secrets, live domains/IPs/hostnames, `.env`, `terraform.tfvars`, `dns-records.local.json`, `ansible/inventory/local.yml`, `private/`, state files, plans, or generated local credentials.
- Treat DNS, Forgejo, and HTTPS/SSH endpoints as critical infrastructure. Prefer reviewed plans over ad hoc mutation.
- Do not mutate production routers/firewalls unless explicitly requested.
- If changing service IPs, hostnames, SSH ports, or proxy topology, update local tfvars, local DNS records, README, and any migration notes together.

## Commands

Prefer OpenTofu:

```bash
tofu fmt -check -recursive
tofu validate
tofu plan -out=tfplan
tofu show tfplan
```

Terraform may be used for local validation if OpenTofu is unavailable:

```bash
terraform fmt -check -recursive
terraform validate
```

Containerized tooling is available for Windows/local consistency:

```bash
docker compose run --rm infra tofu fmt -check -recursive
docker compose run --rm infra tofu validate
docker compose run --rm infra ansible --version
docker compose run --rm infra ansible-lint ansible
```

Use `bash -lc 'set -a; . <(tr -d "\r" < ./.env); set +a; ...'` for containerized commands that source `.env`, so CRLF line endings do not corrupt environment values.

Shell/Python validation:

```bash
shellcheck scripts/*.sh
python -m py_compile scripts/apply-technitium-dns.py
python -m json.tool dns-records.example.json >/dev/null
```

## Credentials and Local Config

Preferred local values setup from a fresh checkout:

```bash
just setup
# or clone an existing private values repo:
just setup <private-values-repo-url>
```

Project commands source `values/.env` through `scripts/run-infra.sh`.

Legacy local files are still supported when needed:

```bash
cp example.vars terraform.tfvars
cp dns-records.example.json dns-records.local.json
cp .env.example .env
```

Do not print token values, generated passwords, real domains/IPs/hostnames, or real local DNS inventory in responses or logs. When summarizing live checks, describe outcomes without exposing site-specific inventory unless the user explicitly requests it.

## Workflow

1. Edit tracked source/example files or local ignored config as requested.
2. Run formatting and validation.
3. If a plan is requested, use `just plan`.
4. Summarize planned creates/changes/destroys.
5. Apply only after explicit approval using `just apply`.
6. For in-LXC service configuration, prefer Ansible playbooks via `just apply` over ad hoc bootstrap-script reruns.

## Bootstrap

After the LXC is created, install Technitium with:

```bash
./scripts/bootstrap-technitium.sh <vmid>
```

Configure local Caddy HTTPS proxy with:

```bash
./scripts/bootstrap-caddy.sh <vmid>
```

After the Forgejo LXC is created, install/configure Forgejo with:

```bash
./scripts/bootstrap-forgejo.sh <vmid>
```

Preferred Forgejo topology: point the Forgejo hostname directly at the Forgejo LXC, run Caddy on that LXC for HTTPS, and use system OpenSSH on port 22 integrated with Forgejo for git SSH. Use a separate Caddy instance on the Technitium LXC for the Technitium UI.

## EdgeRouter helper

`scripts/edgeos-static-host-mapping.sh` mutates a live EdgeRouter config to add a temporary static host mapping.

Run only after explicit approval.

## DNS Management

`dns.tf` uses `terraform_data` to run `scripts/apply-technitium-dns.py` against the local DNS records file specified by `var.dns_records_file`.

The intended pattern is hybrid DNS:

- Technitium Forwarder zones hold explicit static records.
- Unknown names in those zones forward to existing internal resolvers.
- The gateway should remain focused on DHCP/routing/firewall and eventually point DHCP DNS to Technitium.

A Technitium API token must be supplied via `.env`/`TF_VAR_technitium_api_token` before planning or applying DNS resources.
