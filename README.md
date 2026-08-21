# Homelab Infrastructure Runbooks

Reusable OpenTofu and Ansible runbooks for Proxmox LXCs and the shared onramp-host VM running Technitium DNS, Caddy, Forgejo, Infisical, Hermes, FreeLLMAPI, and optional runner/VPN services.

This public repo is intentionally generic. BWS configuration families own real domains, LAN IPs, DNS records, Proxmox settings, operator settings, and enabled services; standalone runtime keys own service secrets. Commands render validated compatibility files in an ephemeral tooling container. Encrypted OpenTofu state is stored in a versioned SeaweedFS S3 backend. The ignored nested `values/` Git repo remains only for excluded private backups, artifacts, dumps, mutable service-state data, and its applicable Forgejo workflow.

## Artifact integrity

Forgejo, Forgejo runner, Docker Compose, just, Go, custom Caddy builds, Tailscale, Technitium portable releases, and Hermes Agent use managed version pins and integrity checks before activation. Hermes 0.18.0 uses a complete hashed wheel lock for Debian 13 amd64/Python 3.13 and verifies its official PyPI provenance. FreeLLMAPI, Infisical, PostgreSQL, Redis, and the tooling Debian base use full OCI tag-and-digest references; the Onclave app definition separately owns its internal SearXNG image contract. After its release-age hold, `just update` advances only private pin sets that still exactly match this runbook's managed defaults; any differing pin is operator-owned and remains unchanged. OCI resolution verifies Registry V2 header/body digests and linux/amd64 multi-arch index semantics. Managed Debian hosts also install automatic security-only updates with automatic reboots disabled.

## Layout

Tracked public source:

```text
infra/opentofu/    OpenTofu configuration and Technitium DNS API helper
infra/ansible/     Ansible playbooks and roles for in-LXC service config
scaffold/          Starter metadata for the excluded private-data repo
scripts/           Local workflow helpers
tools/             Docker tooling image
```

Ignored site/local state:

```text
settings.local.json  BWS project/API locator only
values/              Nested private Git repo for excluded backups/artifacts/dumps/mutable service-state
.terraform/          OpenTofu/Terraform working data
tfplan               Local encrypted plan artifact
```

Keep excluded private backups, artifacts, dumps, and mutable service-state data in `values/` or outside this checkout; do not add another sensitive-data directory to this repo.

## Documentation

- [Docs index](docs/README.md) lists public-safe operator and architecture notes.
- [BWS configuration and SeaweedFS state](docs/bws-seaweedfs-state.md) covers bootstrap, rendering, locking, encryption, and recovery.
- [Debian baseline](docs/debian-baseline.md) documents the verified Debian 13 LXC template and separately pinned Debian 13 `onramp_host` image.
- [Hermes operator pilot PRD](docs/hermes-operator-pilot-prd.md) defines the Hermes cockpit requirements and safety boundaries.
- [Managed service-state backup and restore](docs/service-state-backup.md) covers private `values/` backups for Hermes memory/soul state and other managed service state.
- [Hermes tuning](docs/hermes-tuning.md) documents managed compression and delegation settings.
- [Onramp app-platform contract](docs/onramp-app-platform-contract.md) defines how `homelab-infra`, `onramp-vNext`, and Hermes split onramp-host ownership.
- [App-host runbook](docs/onramp-host-runbook.md) covers `onramp_host` rollback and future deployment validation.
- [Service update policy](docs/service-update-policy.md) defines managed version updates and the Technitium portable-release path.
- [Technitium high availability](docs/technitium-ha.md) covers the optional second Proxmox node, clustering, floating DNS address, staged rollout, and recovery.
- [Herdr remote LXC](docs/herdr-remote-lxc.md) defines the Herdr operator, Pi, and SSH transport contract.

## Fresh setup

Local prerequisites are Git, Git Bash, Docker/Docker Compose, `just`, and CPython 3.11 or newer. Infrastructure tooling runs in the Docker tooling container.

Create ignored `settings.local.json` with the BWS project ID and API server as shown in `settings.example.json`. Set `BITWARDEN_ACCESS_KEY` in the controller environment; do not write it to disk or copy it to managed hosts.

Run setup, optionally supplying the private excluded-data repository URL:

```bash
just setup
just setup git@git.example.internal:owner/homelab-infra-values.git
```

Setup builds the tooling image, creates or clones `values/` for excluded backups and artifacts, rejects obsolete local configuration/state files, and verifies that the BWS snapshot renders. See [BWS configuration and SeaweedFS state](docs/bws-seaweedfs-state.md) for the exact family keys and recovery order.

## Daily workflow

Validate public source, the BWS snapshot, and the excluded-data boundary:

```bash
just validate
```

`just validate` runs source checks, linting, tests, BWS snapshot validation, and excluded `values/` boundary checks. Use it as the normal validation entry point.

Check for eligible pinned version updates without applying infrastructure changes:

```bash
just update
```

`just update` checks known upstream releases, applies each target's hold policy, and writes changed configuration families back to BWS only after the update succeeds. Most tool and service pins use the default 48-hour hold; Technitium, upstream Hermes, and OCI pins use 168 hours. Verified releases from the configured custom Hermes fork have no release-age delay. The default Hermes source verifies the upstream tag commit, official PyPI wheel digest and trusted-publishing provenance, and requires a matching tracked transitive lock before advancing all four private pins together. The optional custom-fork source verifies an eligible fork tag, canonical release URL, downloaded wheel SHA-256, and dependency metadata parity before writing checksum-specific locks under private `values/artifacts/hermes/`. Technitium release discovery can select the newest eligible release while a newer release remains held. Review the resulting diff before continuing with validation and planning.

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

After OpenTofu, apply runs enabled Ansible service chains sequentially by default and stops at the first failure. During recovery, target only the failed enabled service with `scripts/apply-service.sh <service>`; resume broad orchestration only after its direct endpoint and persisted state are healthy. Set `INFRA_APPLY_ANSIBLE_MODE=parallel` only for a healthy routine rollout. Apply removes plan artifacts after the attempt. Technitium DNS credentials must already be valid in `HOMELAB_ENV`; missing or invalid BWS values fail closed instead of creating a second local source.

## Forgejo Actions deployment

The optional `forgejo_runner` service creates a separate Forgejo Actions runner LXC. Keep the runner repository-scoped to the private `values/` repository and use the `homelab-deploy` label for deployment workflows. The runner uses a host execution label so it can run the repo's Docker-backed `just validate`, `just plan`, and `just apply` workflow; do not share it with untrusted repositories. Enable `forgejo` together with `forgejo_runner`; runner registration depends on Forgejo being present and configured first.

Bootstrap order:

1. Add `forgejo_runner` to the `HOMELAB_SETTINGS` service list in BWS.
2. Set `FORGEJO_RUNNER_REGISTRATION_SECRET` in the BWS `HOMELAB_ENV` family to a persistent 40-character hex secret.
3. Configure `forgejo_runner_scope` in the BWS inventory family as the private excluded-data repo owner/name.
4. Run `just validate`, review `just plan`, then run `just apply` after approval.
5. Commit and push `values/.forgejo/workflows/deploy.yml` in the private values repo.

After bootstrap, pushes to the private values repo can run the deployment workflow automatically when a matching runner is online.

## Private excluded-data repo

`values/` is a separate private Git repository nested inside this checkout. It is ignored by the public runbook repo. It now contains only material deliberately excluded from the BWS snapshot, such as service-state backup archives, cached artifacts, dumps, OCI/object exports, and mutable Hermes state archives.

Do not add `.env`, `terraform.tfvars`, Ansible inventory, DNS records, operator settings, or OpenTofu state to `values/`; workflow preflight rejects those obsolete sources. BWS and the encrypted SeaweedFS backend own those contracts.

Use normal Git commands against the nested repo when inspecting excluded private data:

```bash
git -C values status --short --branch
git -C values remote -v
```

## Responsibilities

OpenTofu manages:

- Proxmox LXC resources, including optional per-container VLAN tags when
  `*_vlan_id` values are set in the BWS-rendered tfvars family
- Optional Tailscale client LXC shape, disabled by default until `tailscale_client_enabled` is set in the BWS tfvars family
- Optional Forgejo Actions runner LXC when `forgejo_runner` is enabled in the BWS `HOMELAB_SETTINGS` family
- Optional Infisical secrets service, either as the legacy LXC with service-local Caddy or as `infisical_onramp` on the shared onramp host
- Optional Hermes management LXC with SSH tooling, a non-root `anvil` dashboard runtime user, and a service-local Caddy reverse proxy for the Hermes Agent web dashboard
- Optional Herdr Debian 13 unprivileged LXC shape with disabled nesting and enforced SSH policy
- Optional Debian 13 Podman `onramp_host` VM substrate for app services, using `anvil` as the default cloud-init/deploy user and a shared Caddy instance with per-service snippets. The boot source is a clean Debian 13 genericcloud image imported by OpenTofu from the URL declared in the BWS-rendered tfvars family.
- LXC resource shape, while deliberately ignoring externally owned `mount_point` state; OpenTofu does not attach host-directory bind mounts

Ansible manages:

- Proxmox host ZFS dataset/storage preparation before OpenTofu apply
- LXC lifecycle readiness on the Proxmox host, including the narrow [Forgejo bind-mount lifecycle boundary](docs/forgejo-bind-mount.md), followed by direct SSH/become service configuration on each service host
- Technitium installation, including an optional clustered secondary LXC on a standalone Proxmox host
- Keepalived unicast VRRP for an optional floating LAN DNS address, with local UDP and TCP DNS health checks
- Caddy installation/configuration directly on the primary Technitium LXC. The public fixture exposes the Technitium UI at both `dns.example.internal` and `technitium.example.internal`; set `caddy_server_names` in the BWS inventory family for real domain aliases.
- Forgejo installation/configuration, including Actions settings
- Caddy and OpenSSH integration on the Forgejo LXC
- Forgejo Actions runner installation/registration on a separate LXC
- Infisical Docker Compose stack on the legacy LXC, or rootless Infisical Podman stack on `onramp_host` when `infisical_onramp` is enabled
- Rootless FreeLLMAPI Podman service on `onramp_host`, with a loopback-only application port, shared Caddy HTTPS route, BWS-owned encryption key, and persistent SQLite state
- Hermes management tooling, SSH-oriented bootstrap directories, the Hermes Agent web dashboard running as `anvil`, and Caddy
- Herdr LXC bootstrap, pinned Herdr and Pi installation, operator-local SSH context, and onramp stdio relay access
- App-host SSH hardening, rootless Podman readiness, `anvil` deploy-user setup, shared Caddy setup, default-deny host firewall policy, and deployment directory preparation
- Onclave app deployment on `onramp_host`, including its internal SearXNG container and runtime contract
- Optional Tailscale installation and private backup restore on the Tailscale client LXC
- Technitium DNS records/settings through `infra/ansible/playbooks/technitium-dns.yml`
- Minimal rootless SeaweedFS S3 state storage on `onramp_host`, with a dedicated versioned bucket, lifecycle policy, and shared Caddy HTTPS route

Ansible inventory combines the temporary BWS-rendered inventory with `infra/ansible/inventory/tfvars.py`, which derives service hosts, VMIDs, and addresses from the temporary BWS-rendered tfvars using `python-hcl2`. Normal service diagnostics and steady-state configuration use each service's direct inventory group, such as `technitium`, `forgejo`, `infisical`, or `hermes`; Proxmox access is reserved for lifecycle readiness, storage prep, bootstrap/recovery, and explicit host-boundary work.

## Safety

Do not apply without reviewing `just plan` output. If `just apply` says the saved plan is stale, rerun `just plan` and review it again. Do not commit secrets, state, plans, or real site values to the public repo.

`settings.local.json` contains only the local BWS project/API locator. The BWS `HOMELAB_SETTINGS` family owns the excluded-data repository remote and enabled service list used by OpenTofu and Ansible. Removing a service from that list can plan destroys; review `just plan` before applying.

Container VLAN tags are optional. Omit a `*_vlan_id` variable or set it to
`null` for an untagged LXC interface; set it to a VLAN ID from 1 through 4094
for a tagged interface. The selected Proxmox bridge must already be configured
for that VLAN.

Browser-facing services with DNS records should use static addresses, not DHCP-only addresses. Keep `*_lan_ip`, service networking, and Technitium records aligned across the BWS tfvars, inventory, and DNS families.

Hermes dashboard uses a form-login provider named `basic`. Store
`HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH` in the BWS environment family instead of a
plaintext password; generate it with `python scripts/hermes-password-hash.py`.
The service-local Caddy config rewrites the upstream provider redirect to the
form login route and proxies only to the loopback-bound dashboard. Onclave keeps
its internal SearXNG dependency, while the separately enabled `searxng_onramp`
service provides the managed HTTPS search endpoint used by workstation and Hermes tooling.

The temporary `.env` compatibility snapshot is parsed as dotenv-style data by `scripts/parse-env.py`; it is never sourced as shell. BWS updates must preserve the required variables validated by the public fixture and routing manifest.

The tooling container runs as the unprivileged `anvil` user and mounts `${HOST_SSH_DIR:-${HOME}/.ssh}` read-only. It copies public SSH support files into `/home/anvil/.ssh` by default; set `INFRA_COPY_SSH_KEYS=true` only when private keys must be copied into the container for a run. Direct LXC service runs use strict host-key checking with an ephemeral controller trust store at `/tmp/homelab-infra/ansible/known_hosts`; it is isolated from ambient user/global known-hosts files and is never written to `values/`. The store is shared only by Ansible subprocesses in the same apply container, with a `0700` directory and `0600` file. Before each direct LXC service play, Ansible authenticates to the configured Proxmox host as root, reads the LXC's `/etc/ssh/ssh_host_*_key.pub` files through `pct exec`, validates allowed public-key types/formats, removes stale entries for the direct inventory name and address, and installs only those authoritative keys. It never uses `ssh-keyscan`; failure to obtain or validate keys stops the service play before direct SSH. The apply service scheduler serializes this shared controller trust-store update, so its parallel service runs do not race the file replacement. VMIDs and addresses come from the OpenTofu-derived dynamic inventory, not private inventory duplicates.
