# Managed service-state backup and restore

Managed service state includes runtime configuration and data that is not safe for
this public repository: application config, local databases, repositories,
Hermes memory/soul files, generated runtime state, and service logs.

Backups are private operational state. Store them under the ignored nested
private values repo:

```bash
scripts/service-state.sh list
scripts/service-state.sh backup hermes
scripts/service-state.sh backup all
```

Archives are written under:

```text
values/service-backups/<service>/<service>-state-<timestamp>.tar.gz
values/service-backups/<service>/<service>-state-<timestamp>.tar.gz.sha256
```

To restore a saved archive:

```bash
scripts/service-state.sh restore hermes values/service-backups/hermes/hermes-state-<timestamp>.tar.gz
```

For rebuild/bootstrap automation where a backup may not exist yet, use the
no-op-on-missing form:

```bash
scripts/service-state.sh restore-if-present hermes
scripts/service-state.sh restore-if-present hermes values/service-backups/hermes/hermes-state-<timestamp>.tar.gz
```

With no archive argument, `restore-if-present` restores the newest normal backup
for that service when one exists. Pre-restore recovery archives are excluded
from implicit selection. If no backup exists, it logs a skip message and exits
successfully.

Before stopping services, restore verifies the checksum when a sidecar exists,
checks that the archive belongs to the selected target, rejects unsafe members
and links, validates the catalog and destination accounts, and requires exactly
one destination host. It then stops system units followed by user units. Stop
failures abort before any managed path is changed.

When current state exists, restore writes a private `0600` pre-restore archive
and SHA-256 sidecar under `values/service-backups/<service>/`. Only after that
archive is fetched does restore remove configured paths, extract the selected
archive, and repair each path's catalog-declared ownership without changing
archived modes. User units then start before system units, in reverse declared
order. A failure after mutation leaves services stopped and reports the recovery
archive; restore does not automatically roll back.

## Supported targets

Current service-state targets are:

- `hermes` — runtime user's `.hermes` directory, including memory/soul files,
  config, history, logs, and Hermes-managed backups.
- `forgejo` — `/etc/forgejo` and `/var/lib/forgejo`.
- `technitium` — `/etc/dns`.
- `onramp_host` — `/etc/caddy` and the configured onramp deployment directory.
- `infisical_onramp` — Infisical onramp deployment directory and Caddy snippet.
- `searxng_onramp` — SearXNG onramp deployment directory and Caddy snippet.

The managed paths live in `infra/ansible/vars/service-state.yml`. Every path
explicitly declares its owner, group, and whether ownership repair is recursive.
Archive modes remain authoritative. `infra/services.json` is authoritative for
CLI eligibility through each service's `state_capable` metadata; add a target to
both files when this repo starts managing a new stateful service.

## Operator notes

- Before writing a backup, the CLI restricts `values/service-backups/` on Windows to the current user, SYSTEM, and Administrators with inheritable ACLs. POSIX hosts enforce mode `0700`. Missing host permission tools fail closed instead of writing an exposed archive.
- Run backups before rebuilding or replacing a service host. `just apply` verifies the newest archive checksum and manifest for every affected stateful service and requires it to be no older than 24 hours.
- A destructive plan affecting multiple stateful services is blocked by default. Use `INFRA_TARGET_SERVICE=<service> just plan` for the canary rollout, verify its direct endpoint and state, then create the next plan.
- Review and commit/push the private `values/` repo after a successful backup if
  you want the archive stored in the private remote.
- Restore is normally explicit and service-scoped. Hermes is the exception during
  guarded bootstrap: when a normal private backup exists and live state is absent
  or empty, the role validates and restores the newest complete `.hermes` archive
  before starting Hermes. A customized live
  state directory is never overwritten automatically, and a backup containing a
  known default soul is rejected for automatic restoration.
- Backup manifests use schema version 1 and identify the target, archive kind,
  timestamp, description, and paths present at backup time. Legacy manifestless
  Hermes archives remain supported after the same path and link safety checks.
- Use `restore-if-present` for first-run/rebuild flows that should continue when
  no prior private backup exists.
- The workflow uses the normal direct Ansible inventory group for each service.
  If direct SSH to a service host is unavailable, fix service SSH access before
  relying on routine backup/restore.
