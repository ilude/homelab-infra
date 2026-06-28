# Homelab Infrastructure Runbooks

Reusable OpenTofu and Ansible runbooks for Proxmox LXCs running Technitium DNS, Caddy, Forgejo, and an optional Tailscale client.

This public repo is intentionally generic. Real domains, LAN IPs, DNS records, Proxmox endpoints, credentials, and state belong in `values/`, an ignored nested Git repo. In a typical install, `values/` is pushed to a private Forgejo repository while this runbook repo stays public-safe.

## Layout

Tracked public source:

```text
infra/opentofu/    OpenTofu configuration and Technitium DNS API helper
infra/ansible/     Ansible playbooks and roles for in-LXC service config
scaffold/          Public-safe starter files copied into values/
scripts/           Local workflow helpers
tools/             Docker tooling image
```

Ignored site/local state:

```text
values/            Nested private Git repo for site values/state
.terraform/        OpenTofu/Terraform working data
tfplan             Local plan artifact
```

Keep non-public material in `values/` or outside this checkout; do not add another sensitive-data directory to this repo.

## Fresh setup

From a fresh checkout, optionally copy the local settings template:

```bash
cp settings.example.json settings.local.json
```

Edit `settings.local.json` if you want `just setup` to clone your private `values/` Git repo. For example, set `values_repo.remote` to your Forgejo SSH URL. The file is ignored by Git. Supported services are `technitium`, `forgejo`, and `tailscale_client`; `technitium` includes its Caddy proxy, and `forgejo` includes its in-LXC Caddy configuration when enabled in inventory.

Then run:

```bash
just setup
```

This builds the local tooling container and creates `values/` from `scaffold/`, or clones the `values_repo.remote` configured in `settings.local.json`.

You can also pass the values repo URL directly:

```bash
just setup git@git.example.internal:owner/homelab-infra-values.git
```

Then edit the private files:

```text
values/.env
values/terraform.tfvars
values/dns-records.local.json
values/ansible/inventory/local.yml
```

## Daily workflow

Validate public source and private values wiring:

```bash
just validate
```

`just validate` runs source checks, linting, tests, and private `values/` wiring checks. Use it as the normal validation entry point.

Review infrastructure/DNS changes:

```bash
just plan
```

Apply the reviewed plan and configure services with Ansible:

```bash
just apply
```

`just plan` writes `tfplan` plus `tfplan.meta.json`. `just apply` refuses to run if the saved plan or its inputs changed, then removes plan artifacts after the apply attempt.

## Private values repo

`values/` is a separate Git repository nested inside this checkout. It is ignored by the public runbook repo and should be pushed only to a private remote, such as your Forgejo instance. `just setup` either clones that repo from `settings.local.json` / the CLI argument, or initializes a new local `values/` repo from `scaffold/`.

The scaffold defines this shape:

```text
values/
  .env
  terraform.tfvars
  dns-records.local.json
  ansible/inventory/local.yml
```

Use normal Git commands against the nested repo when you need to inspect, commit, or push private values:

```bash
git -C values status --short --branch
git -C values remote -v
```

## Responsibilities

OpenTofu manages:

- Proxmox LXC resources
- Optional Tailscale client LXC shape, disabled by default until `tailscale_client_enabled` is set in private values
- Forgejo ZFS bind mount shape
- Technitium DNS records/settings through `infra/opentofu/scripts/apply-technitium-dns.py`

Ansible manages:

- Technitium installation
- Caddy installation/configuration on the Technitium LXC
- Forgejo installation/configuration
- Caddy and OpenSSH integration on the Forgejo LXC
- Optional Tailscale installation and private backup restore on the Tailscale client LXC

## Safety

Do not apply without reviewing `just plan` output. If `just apply` says the saved plan is stale, rerun `just plan` and review it again. Do not commit secrets, state, plans, or real site values to the public repo.

`settings.local.json` is the local operator settings file. It can set `values_repo.remote` for setup and the `services` list used by OpenTofu planning plus Ansible validation/apply. Removing a service from the list tells OpenTofu to stop maintaining its resources, which can plan destroys; review `just plan` before applying.

`values/.env` is parsed as dotenv-style data by `scripts/parse-env.py`; it is not sourced as shell. Keep required variables from `scaffold/.env.example` in sync with your private `values/.env`.

The tooling container mounts `${HOST_SSH_DIR:-${HOME}/.ssh}` read-only. It copies public SSH support files by default; set `INFRA_COPY_SSH_KEYS=true` only when private keys must be copied into the container for a run.

`scripts/edgeos-static-host-mapping.sh` mutates a live EdgeRouter config and should only be run after explicit review/approval. Use `--dry-run` to inspect commands first.
