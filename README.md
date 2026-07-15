# Homelab Infrastructure Runbooks

Reusable OpenTofu and Ansible runbooks for Proxmox LXCs running Technitium DNS, Caddy, Forgejo, Infisical, Hermes, and optional runner/VPN services.

This public repo is intentionally generic. Real domains, LAN IPs, DNS records, Proxmox endpoints, credentials, and state belong in `values/`, an ignored nested Git repo. In a typical install, `values/` is pushed to a private Forgejo repository while this runbook repo stays public-safe.

## Artifact integrity

Forgejo, Forgejo runner, Docker Compose, just, Go, custom Caddy builds, Tailscale, Technitium portable releases, and Hermes Agent use managed version pins and integrity checks before activation. Hermes 0.18.0 uses a complete hashed wheel lock for Debian 13 amd64/Python 3.13 and verifies its official PyPI provenance. Infisical, PostgreSQL, Redis, SearXNG, and the tooling Debian base use full OCI tag-and-digest references. After its release-age hold, `just update` advances only private pin sets that still exactly match this runbook's managed defaults; any differing pin is operator-owned and remains unchanged. OCI resolution verifies Registry V2 header/body digests and linux/amd64 multi-arch index semantics. Managed Debian hosts also install automatic security-only updates with automatic reboots disabled.

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

## Documentation

- [Docs index](docs/README.md) lists public-safe operator and architecture notes.
- [Debian baseline](docs/debian-baseline.md) documents the verified Debian 13 LXC template and separately pinned Debian 13 `onramp_host` image.
- [Hermes operator pilot PRD](docs/hermes-operator-pilot-prd.md) defines the Hermes cockpit requirements and safety boundaries.
- [Managed service-state backup and restore](docs/service-state-backup.md) covers private `values/` backups for Hermes memory/soul state and other managed service state.
- [Hermes tuning](docs/hermes-tuning.md) documents managed compression and delegation settings.
- [Onramp app-platform contract](docs/onramp-app-platform-contract.md) defines how `homelab-infra`, `onramp-vNext`, and Hermes split onramp-host ownership.
- [Onramp SearXNG handoff](docs/onramp-searxng-handoff.md) documents the default future Onramp-owned SearXNG contract and the current temporary `homelab-infra` exception.
- [App-host runbook](docs/onramp-host-runbook.md) covers `onramp_host` rollback and future deployment validation.
- [Service update policy](docs/service-update-policy.md) defines managed version updates and the Technitium portable-release path.
- [Technitium high availability](docs/technitium-ha.md) covers the optional second Proxmox node, clustering, floating DNS address, staged rollout, and recovery.

## Fresh setup

Local prerequisites are Git, Git Bash, Docker/Docker Compose, `just`, and CPython 3.11 or newer. Install CPython through Python.org, `winget install --exact --id Python.Python.3.13`, or your platform package manager. The journal helper is the only host Python workflow; infrastructure tooling remains containerized. Run the journal helper through `scripts/host-python.sh`. Python, OpenTofu, Ansible, TFLint, ShellCheck, SSH client usage for setup/apply, and related tooling run inside the Docker tooling container. Your host SSH directory is mounted read-only so the container can use your existing Proxmox SSH key when a command opts in.

From a fresh checkout, optionally copy the local settings template:

```bash
cp settings.example.json settings.local.json
```

Edit `settings.local.json` if you want `just setup` to clone your private `values/` Git repo. For example, set `values_repo.remote` to your Forgejo SSH URL. The file is ignored by Git. Supported services are defined in `infra/services.json` and currently include `technitium`, `technitium_secondary`, `forgejo`, `tailscale_client`, `forgejo_runner`, `infisical`, `infisical_onramp`, `hermes`, `onramp_host`, and `searxng_onramp`; `technitium` includes its Caddy proxy, LXC browser-facing services use service-local Caddy, `onramp_host` prepares a Debian 13 Podman VM with shared Caddy, `infisical_onramp` and `searxng_onramp` deploy rootless services on that VM, and `forgejo_runner` creates/configures a separate Forgejo Actions runner LXC.

Then run:

```bash
just setup
```

This builds the local tooling container and creates `values/` from `scaffold/`, or clones the `values_repo.remote` configured in `settings.local.json`. If no remote is configured and setup is interactive, it can ask for a base domain, probe `git.<domain>` for an accessible `homelab-infra-values` repository, save the discovered remote in ignored `settings.local.json`, and clone it. It also starts setup wizards for Proxmox API access and domain-derived service names. The Proxmox wizard asks for your Proxmox host, verifies root SSH key access, offers an alternate key file or a command to authorize your default public SSH key if default keys fail, creates/updates a dedicated Proxmox API user/token, and writes the endpoint/token/SSH target to `values/.env` without printing the token secret. The domain wizard asks for your base domain plus service IPs, then derives names such as `dns.<domain>`, `technitium.<domain>`, `git.<domain>`, `infisical.<domain>`, `hermes.<domain>`, and `searxng.apps.<domain>` in the authoritative private values files.

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

`just update` checks known upstream releases and applies each target's hold policy. Most tool and service pins use the default 48-hour hold; Technitium, upstream Hermes, and OCI pins use 168 hours. Verified releases from the configured custom Hermes fork have no release-age delay. The default Hermes source verifies the upstream tag commit, official PyPI wheel digest and trusted-publishing provenance, and requires a matching tracked transitive lock before advancing all four private pins together. The optional custom-fork source verifies an eligible fork tag, canonical release URL, downloaded wheel SHA-256, and dependency metadata parity before writing checksum-specific locks under private `values/artifacts/hermes/`. Technitium release discovery can select the newest eligible release while a newer release remains held. Review the resulting diff before continuing with validation and planning.

Technitium apply uses the pinned portable archive. It prefers an optional private cache at `values/artifacts/technitium/<version>/DnsServerPortable.tar.gz`, falls back to the official versioned URL, verifies SHA-256 and archive layout, and activates only when the healthy installed-version marker differs. The previous application release and pre-activation `/etc/dns` state are retained for failed-health-check rollback. Do not rerun the upstream `install.sh` as an update mechanism.

Hermes apply supports the official PyPI wheel or a checksum-pinned custom GitHub release wheel. It downloads only hash-locked dependencies, verifies the selected Hermes wheel before installation, installs entirely from the local wheelhouse, builds a checksum-specific venv, and atomically switches `/usr/local/lib/hermes-agent/venv`. It also installs a checksum-verified, versioned Node.js runtime and hash-locked dashboard messaging dependencies before starting the dashboard; Hermes runtime dependency self-bootstrap and lazy installs are disabled. A systemd preflight verifies Node, the release-following TUI bundle, dashboard/channel Python imports, and writable runtime state, and apply rejects fatal startup-journal markers. The configured Hermes runtime user receives full passwordless sudo through a validated `/etc/sudoers.d/hermes-runtime` policy; treat Hermes and its dashboard credentials as root-equivalent access to this LXC. `/usr/local/bin/hermes` and the systemd command remain stable. The immediately preceding venv is retained through `/usr/local/lib/hermes-agent/previous` and restored only after gateway and dashboard rollback health pass. Runtime state remains at `/home/<runtime-user>/.hermes` outside application releases. On a fresh Hermes host with absent or empty state, apply validates and restores the newest customized full-state archive from the private values repo before Hermes starts; it never automatically replaces existing live state. `hermes update` is not the managed update path.

Review infrastructure/DNS changes:

```bash
just plan
```

Apply the reviewed plan and configure services with Ansible:

```bash
just apply
```

`just plan` writes `tfplan` plus `tfplan.meta.json`. `just apply` refuses to run if the saved plan or its inputs changed. Destructive stateful changes additionally require a verified backup no older than 24 hours. A plan affecting multiple stateful services is blocked by default; create a one-service canary with `INFRA_TARGET_SERVICE=<service> just plan`, apply and verify that service, then run a full `just plan` before the next rollout. `INFRA_ALLOW_STATEFUL_BATCH=1` is reserved for an explicitly reviewed exception and does not replace `INFRA_ALLOW_DESTROY=1`.

After OpenTofu, apply runs enabled Ansible service chains sequentially by default and stops at the first failure. During recovery, target only the failed enabled service with `scripts/apply-service.sh <service>`; resume broad orchestration only after its direct endpoint and persisted state are healthy. Set `INFRA_APPLY_ANSIBLE_MODE=parallel` only for a healthy routine rollout, and use `INFRA_APPLY_ANSIBLE_MAX_WORKERS=<n>` to cap parallel service chains. Apply removes plan artifacts after the attempt. `TECHNITIUM_API_URL` should use the direct LXC API endpoint (`http://<technitium-lxc-ip>:5380/api`) so DNS sync does not depend on records it creates. If the Technitium token is missing or still a placeholder, apply bootstraps one through the local API and stores it in `values/.env` without printing the token.

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

- Proxmox LXC resources, including optional per-container VLAN tags when
  `*_vlan_id` values are set in `values/terraform.tfvars`
- Optional Tailscale client LXC shape, disabled by default until `tailscale_client_enabled` is set in private values
- Optional Forgejo Actions runner LXC when `forgejo_runner` is enabled in local settings
- Optional Infisical secrets service, either as the legacy LXC with service-local Caddy or as `infisical_onramp` on the shared onramp host
- Optional Hermes management LXC with SSH tooling, a non-root `anvil` dashboard runtime user, and a service-local Caddy reverse proxy for the Hermes Agent web dashboard
- Optional Debian 13 Podman `onramp_host` VM substrate for app services, using `anvil` as the default cloud-init/deploy user and a shared Caddy instance with per-service snippets. The boot source is a clean Debian 13 genericcloud image imported by OpenTofu from the URL declared in private `values/terraform.tfvars`.
- LXC resource shape, while deliberately ignoring externally owned `mount_point` state; OpenTofu does not attach host-directory bind mounts

Ansible manages:

- Proxmox host ZFS dataset/storage preparation before OpenTofu apply
- LXC lifecycle readiness on the Proxmox host, including the narrow [Forgejo bind-mount lifecycle boundary](docs/forgejo-bind-mount.md), followed by direct SSH/become service configuration on each service host
- Technitium installation, including an optional clustered secondary LXC on a standalone Proxmox host
- Keepalived unicast VRRP for an optional floating LAN DNS address, with local UDP and TCP DNS health checks
- Caddy installation/configuration directly on the primary Technitium LXC. The scaffold exposes the Technitium UI at both `dns.example.internal` and `technitium.example.internal`; set `caddy_server_names` in private inventory for your real domain aliases.
- Forgejo installation/configuration, including Actions settings
- Caddy and OpenSSH integration on the Forgejo LXC
- Forgejo Actions runner installation/registration on a separate LXC
- Infisical Docker Compose stack on the legacy LXC, or rootless Infisical Podman stack on `onramp_host` when `infisical_onramp` is enabled
- Hermes management tooling, SSH-oriented bootstrap directories, the Hermes Agent web dashboard running as `anvil`, and Caddy
- App-host SSH hardening, rootless Podman readiness, `anvil` deploy-user setup, shared Caddy setup, default-deny host firewall policy, and deployment directory preparation
- Temporary SearXNG onramp workload deployment with rootless Podman, a shared Caddy site snippet, Technitium DNS record input, and Hermes endpoint env wiring when `searxng_onramp` is enabled
- Optional Tailscale installation and private backup restore on the Tailscale client LXC
- Technitium DNS records/settings through `infra/ansible/playbooks/technitium-dns.yml`

Ansible inventory combines `values/ansible/inventory/local.yml` with `infra/ansible/inventory/tfvars.py`, which derives service hosts, VMIDs, and addresses from `values/terraform.tfvars` using `python-hcl2`. Normal service diagnostics and steady-state configuration use each service's direct inventory group, such as `technitium`, `forgejo`, `infisical`, or `hermes`; Proxmox access is reserved for lifecycle readiness, storage prep, bootstrap/recovery, and explicit host-boundary work.

## Safety

Do not apply without reviewing `just plan` output. If `just apply` says the saved plan is stale, rerun `just plan` and review it again. Do not commit secrets, state, plans, or real site values to the public repo.

`settings.local.json` is the local operator settings file. It can set `values_repo.remote` for setup and the `services` list used by OpenTofu planning plus Ansible validation/apply. Removing a service from the list tells OpenTofu to stop maintaining its resources, which can plan destroys; review `just plan` before applying.

Container VLAN tags are optional. Omit a `*_vlan_id` variable or set it to
`null` for an untagged LXC interface; set it to a VLAN ID from 1 through 4094
for a tagged interface. The selected Proxmox bridge must already be configured
for that VLAN.

Browser-facing services with DNS records should use static LXC IP addresses,
not DHCP-only addresses. The setup wizard derives contiguous static service IPs
from the first managed service IP you provide and keeps `*_lan_ip`, LXC network
configuration, and Technitium DNS records aligned.

Hermes dashboard uses a form-login provider named `basic`. Store
`HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH` in private values instead of a
plaintext password; generate it with `python scripts/hermes-password-hash.py`.
The service-local Caddy config rewrites the upstream provider redirect to the
form login route and proxies only to the loopback-bound dashboard. Hermes `web-searxng` plugin/runtime should read the SearXNG endpoint from the
Hermes-native `SEARXNG_URL` environment key. Private values keep the same
endpoint as `HERMES_WEB_SEARXNG_URL`, and Ansible renders both names into the
Hermes dashboard environment for compatibility. When `searxng_onramp` is
enabled, this repo temporarily manages that endpoint on `onramp_host` as
`https://searxng.apps.<domain>` or the private equivalent.

`values/.env` is parsed as dotenv-style data by `scripts/parse-env.py`; it is not sourced as shell. Keep required variables from `scaffold/.env.example` in sync with your private `values/.env`.

The tooling container runs as the unprivileged `anvil` user and mounts `${HOST_SSH_DIR:-${HOME}/.ssh}` read-only. It copies public SSH support files into `/home/anvil/.ssh` by default; set `INFRA_COPY_SSH_KEYS=true` only when private keys must be copied into the container for a run. Direct LXC service runs use strict host-key checking with an ephemeral controller trust store at `/tmp/homelab-infra/ansible/known_hosts`; it is isolated from ambient user/global known-hosts files and is never written to `values/`. The store is shared only by Ansible subprocesses in the same apply container, with a `0700` directory and `0600` file. Before each direct LXC service play, Ansible authenticates to the configured Proxmox host as root, reads the LXC's `/etc/ssh/ssh_host_*_key.pub` files through `pct exec`, validates allowed public-key types/formats, removes stale entries for the direct inventory name and address, and installs only those authoritative keys. It never uses `ssh-keyscan`; failure to obtain or validate keys stops the service play before direct SSH. The apply service scheduler serializes this shared controller trust-store update, so its parallel service runs do not race the file replacement. VMIDs and addresses come from the OpenTofu-derived dynamic inventory, not private inventory duplicates.
