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

Local prerequisites are Git, Docker/Docker Compose, and `just`. Python, OpenTofu, Ansible, TFLint, ShellCheck, SSH client usage for setup/apply, and related tooling run inside the Docker tooling container. Your host SSH directory is mounted read-only so the container can use your existing Proxmox SSH key when a command opts in.

From a fresh checkout, optionally copy the local settings template:

```bash
cp settings.example.json settings.local.json
```

Edit `settings.local.json` if you want `just setup` to clone your private `values/` Git repo. For example, set `values_repo.remote` to your Forgejo SSH URL. The file is ignored by Git. Supported services are `technitium`, `forgejo`, `tailscale_client`, and `forgejo_runner`; `technitium` includes its Caddy proxy, `forgejo` includes its in-LXC Caddy configuration when enabled in inventory, and `forgejo_runner` creates/configures a separate Forgejo Actions runner LXC.

Then run:

```bash
just setup
```

This builds the local tooling container and creates `values/` from `scaffold/`, or clones the `values_repo.remote` configured in `settings.local.json`. If no remote is configured and setup is interactive, it can ask for a base domain, probe `git.<domain>` for an accessible `homelab-infra-values` repository, save the discovered remote in ignored `settings.local.json`, and clone it. It also starts setup wizards for Proxmox API access and domain-derived service names. The Proxmox wizard asks for your Proxmox host, verifies root SSH key access, offers an alternate key file or a command to authorize your default public SSH key if default keys fail, creates/updates a dedicated Proxmox API user/token, and writes the endpoint/token/SSH target to `values/.env` without printing the token secret. The domain wizard asks for your base domain plus service IPs, then derives names such as `dns.<domain>`, `technitium.<domain>`, and `git.<domain>` in the private values files.

You can also pass the values repo URL directly:

```bash
just setup git@git.example.internal:owner/homelab-infra-values.git
```

Then edit the remaining private files:

```text
values/.env
values/terraform.tfvars
values/dns-records.local.json
values/ansible/inventory/local.yml
```

If you skipped the Proxmox token wizard or need to rotate the token later, run:

```bash
scripts/bootstrap-pve-token.sh --force
```

If you need to rerun the domain wizard, run:

```bash
scripts/python.sh scripts/bootstrap-domain.py --force
```

## Daily workflow

Validate public source and private values wiring:

```bash
just validate
```

`just validate` runs source checks, linting, tests, and private `values/` wiring checks. Use it as the normal validation entry point.

Check for eligible pinned version updates without applying infrastructure changes:

```bash
just update
```

`just update` checks known upstream releases and only updates pins for releases at least 48 hours old. Review the resulting diff before continuing with validation and planning.

Review infrastructure/DNS changes:

```bash
just plan
```

Apply the reviewed plan and configure services with Ansible:

```bash
just apply
```

`just plan` writes `tfplan` plus `tfplan.meta.json`. `just apply` refuses to run if the saved plan or its inputs changed, then applies infrastructure, runs enabled Ansible playbooks, and syncs Technitium DNS records after the DNS service is installed. It removes plan artifacts after the apply attempt.

After a successful apply, review and commit the private `values/` repo because OpenTofu state and local inventory may have changed:

```bash
git -C values status --short
git -C values add -- terraform.tfstate terraform.tfstate.backup ansible/inventory/local.yml dns-records.local.json
git -C values commit -m "chore: update local infrastructure state"
git -C values push
```

## Forgejo Actions deployment

The optional `forgejo_runner` service creates a separate Forgejo Actions runner LXC. Keep the runner repository-scoped to the private `values/` repository and use the `homelab-deploy` label for deployment workflows. The runner uses a host execution label so it can run the repo's Docker-backed `just validate`, `just plan`, and `just apply` workflow; do not share it with untrusted repositories. Enable `forgejo` together with `forgejo_runner`; runner registration depends on Forgejo being present and configured first.

Bootstrap order:

1. Add `forgejo_runner` to `settings.local.json` services.
2. Set `FORGEJO_RUNNER_REGISTRATION_SECRET` in `values/.env` to a persistent 40-character hex secret.
3. Configure `forgejo_runner_scope` in private inventory as the private values repo owner/name.
4. Run `just validate`, review `just plan`, then run `just apply` after approval.
5. Commit and push `values/.forgejo/workflows/deploy.yml` in the private values repo.

After bootstrap, pushes to the private values repo can run the deployment workflow automatically when a matching runner is online.

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
- Optional Forgejo Actions runner LXC when `forgejo_runner` is enabled in local settings
- Forgejo ZFS bind mount shape
- Technitium DNS records/settings through `infra/opentofu/scripts/apply-technitium-dns.py`

Ansible manages:

- Technitium installation
- Caddy installation/configuration on the Technitium LXC. The scaffold exposes the Technitium UI at both `dns.example.internal` and `technitium.example.internal`; set `caddy_server_names` in private inventory for your real domain aliases.
- Forgejo installation/configuration, including Actions settings
- Caddy and OpenSSH integration on the Forgejo LXC
- Forgejo Actions runner installation/registration on a separate LXC
- Optional Tailscale installation and private backup restore on the Tailscale client LXC

## Safety

Do not apply without reviewing `just plan` output. If `just apply` says the saved plan is stale, rerun `just plan` and review it again. Do not commit secrets, state, plans, or real site values to the public repo.

`settings.local.json` is the local operator settings file. It can set `values_repo.remote` for setup and the `services` list used by OpenTofu planning plus Ansible validation/apply. Removing a service from the list tells OpenTofu to stop maintaining its resources, which can plan destroys; review `just plan` before applying.

`values/.env` is parsed as dotenv-style data by `scripts/parse-env.py`; it is not sourced as shell. Keep required variables from `scaffold/.env.example` in sync with your private `values/.env`.

The tooling container runs as the unprivileged `anvil` user and mounts `${HOST_SSH_DIR:-${HOME}/.ssh}` read-only. It copies public SSH support files into `/home/anvil/.ssh` by default; set `INFRA_COPY_SSH_KEYS=true` only when private keys must be copied into the container for a run.

`scripts/edgeos-static-host-mapping.sh` mutates a live EdgeRouter config and should only be run after explicit review/approval. Use `--dry-run` to inspect commands first.
