# homelab-infra values template

This directory is a public-safe template for `values/`, the nested private Git repo that stores site values and state.

`values/` is ignored by the public runbooks repo. In normal use it has its own private remote, such as a Forgejo repository, and is committed/pushed separately from this repo.

## Files

- `.env` — local credentials and bootstrap environment variables, including Hermes Agent dashboard auth secrets.
- `terraform.tfvars` — site-specific Proxmox/LXC/OpenTofu variables, including optional per-container VLAN tags and the optional disabled-by-default Tailscale client LXC.
- Optional private artifact cache — stage Technitium archives as `artifacts/technitium/<version>/DnsServerPortable.tar.gz`; keep them in ignored private storage outside tracked `scaffold/`.
- `dns-records.local.json` — site-specific Technitium DNS zones and records.
- `ansible/inventory/local.yml` — site-specific Ansible role variables. Do not duplicate the Proxmox host here: dynamic inventory derives the single `pve` target from `PVE_HOST`, uses `root`, and derives its node identity from `proxmox_node_name` in `terraform.tfvars`. The Technitium Caddy proxy uses `caddy_server_names` for DNS UI aliases such as `dns.example.internal` and `technitium.example.internal`.

## Initialize

From the runbooks repo root:

```bash
cp settings.example.json settings.local.json  # optional local setup defaults
just setup
```

Or clone an existing private values repo, such as the Forgejo-hosted values repo, during setup:

```bash
just setup git@git.example.internal:owner/homelab-infra-values.git
```

When run interactively, `just setup` starts setup wizards if private values still have scaffold placeholders. The Proxmox wizard asks for the Proxmox host, tests root SSH key access, offers an alternate key file or a command to authorize your default public SSH key if default keys fail, creates/updates a Proxmox API user/token, and stores the endpoint/token/SSH target in `.env` without printing the token secret. The domain wizard asks for your base domain plus a starting service IP, then derives static LXC addresses and names such as `dns.<domain>`, `technitium.<domain>`, `git.<domain>`, `infisical.<domain>`, and `hermes.<domain>` in the authoritative private values files. To rerun the Proxmox wizard later from the runbooks repo root:

```bash
scripts/bootstrap-pve-token.sh --force
```

To rerun the domain wizard:

```bash
scripts/python.sh scripts/bootstrap-domain.py --force
```

Container VLAN tags default to `null`, which leaves the LXC interface untagged.
Set the matching `*_vlan_id` value to a VLAN ID from 1 through 4094 when the
Proxmox bridge should tag that container interface.

Hermes and the optional onramp host use `anvil` as their non-root runtime/deploy user by default. Add real public SSH keys to `lxc_ssh_public_keys`; the onramp cloud-init keys fall back to that list when `onramp_host_ssh_public_keys` is empty. The Hermes runtime user receives full passwordless sudo inside its LXC, so its SSH keys and dashboard credentials are root-equivalent for that service host. Hermes version, tag, commit, and wheel SHA-256 form one managed pin group. Leave all four at managed defaults for `just update`, or customize the group intentionally; migrations and updates do not fill or overwrite partial custom groups. Node.js version and architecture checksums form a separate managed compatibility pin group. Apply uses the tracked Debian 13 amd64/Python 3.13 hashed wheel lock, includes dashboard messaging dependencies, installs verified Node.js before dashboard startup, disables runtime self-bootstrap and lazy installs, and preserves `/home/anvil/.hermes` across versioned venv activation and rollback. On a fresh Hermes host with absent or empty state, the newest customized full-state archive under `service-backups/hermes/` is validated and restored before startup; existing live state is never replaced automatically.

Technitium updates use the private version/checksum pin group in `ansible/inventory/local.yml`. Apply prefers a matching cached archive when present and otherwise uses the official versioned URL; both paths verify the private SHA-256 before extraction. Keep live cached tarballs and checksums out of tracked source.

After editing the copied files, run the normal validation entry point:

```bash
just validate
```

Keep `.env` in dotenv-style `KEY=value` or `export KEY=value` format. The runbooks parse it as data and reject shell execution patterns.

Optional EdgeRouter access uses `EDGEROUTER_ADDR` (for example, `firewall.example.internal`) and `EDGEROUTER_USER` (for example, `ubnt`). Configure that account for key-based, read-only SSH access. Do not store `EDGEROUTER_PASS`.

For Hermes dashboard form login, store `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH`, not a plaintext password. Generate it with:

```bash
python scripts/hermes-password-hash.py
```

For Forgejo Actions deployment, set `FORGEJO_RUNNER_REGISTRATION_SECRET` to a persistent 40-character hex secret and enable `forgejo_runner` in `settings.local.json` services before planning the runner LXC.
