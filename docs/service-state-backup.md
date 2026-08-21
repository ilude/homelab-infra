# Managed service-state backup and restore

Managed service state includes runtime configuration and data that is not safe for
this public repository: application config, local databases, repositories,
Hermes memory/soul files, generated runtime state, and service logs.

Backups are private operational state. Most targets store them under the ignored
nested private values repo. Onclave keeps its current backup and compressed
history on the Onramp host for faster backup and restore:

```bash
scripts/service-state.sh list
scripts/service-state.sh backup hermes
scripts/service-state.sh backup onclave_onramp
scripts/service-state.sh backup all
```

Controller-backed targets write archives under:

```text
values/service-backups/<service>/<service>-state-<timestamp>.tar.gz
values/service-backups/<service>/<service>-state-<timestamp>.tar.gz.sha256
```

Onclave writes an atomic uncompressed `latest.tar` under its private device
backup root, restarts the service, and then launches compression with
`systemd-run --no-block`. The background job uses gzip level 1, writes a
checksummed timestamped history archive, and retains five compressed archives
total: the current snapshot and up to four older snapshots. The checksummed
uncompressed `latest.tar` remains available for immediate restore.

Restore a controller archive or the device-local Onclave backup with:

```bash
scripts/service-state.sh restore hermes values/service-backups/hermes/hermes-state-<timestamp>.tar.gz
scripts/service-state.sh restore onclave_onramp latest
scripts/service-state.sh restore onclave_onramp onclave_onramp-state-<timestamp>.tar.gz
```

Onclave restore also accepts a reported pre-restore archive basename. Device
selectors are basenames only; paths and traversal are rejected. Backup and
restore commands fail immediately when another local Onclave state operation is
active.

For rebuild/bootstrap automation where a backup may not exist yet, use the
no-op-on-missing form:

```bash
scripts/service-state.sh restore-if-present hermes
scripts/service-state.sh restore-if-present hermes values/service-backups/hermes/hermes-state-<timestamp>.tar.gz
```

With no archive argument, `restore-if-present` restores the newest normal
controller backup for that service when one exists. Pre-restore recovery
archives are excluded from implicit selection. If no backup exists, it logs a
skip message and exits successfully. Onclave rejects `restore-if-present` because
its device-local archive is an application rollback, not bootstrap state.

Before stopping services, restore requires and verifies device-local checksums,
checks that the archive belongs to the selected target, rejects unsafe members
and links, validates the catalog and destination accounts, and requires exactly
one destination host. It then stops system units followed by user units. Stop
failures abort before any managed path is changed.

When current state exists, restore creates a private pre-restore archive before
removing configured paths. Controller-backed targets stream and checksum it under
`values/service-backups/<service>/`. Onclave keeps it uncompressed on the Onramp
host with a checksum, validates it there, and queues background compression only
after a successful restore. Restore repairs each path's catalog-declared ownership
without changing archived modes, then starts user units before system units in
reverse declared order. A failure before managed path removal restarts managed
services and exits failed. A failure after mutation leaves services stopped and
keeps the recovery archive uncompressed for direct recovery.

## Supported targets

Current service-state targets are:

- `hermes` -- runtime user's `.hermes` directory, including memory/soul files,
  config, history, logs, and Hermes-managed backups.
- `forgejo` -- `/etc/forgejo` and `/var/lib/forgejo`.
- `technitium` -- `/etc/dns`.
- `onramp_host` -- host-owned Caddy base files: `/etc/caddy/env`, `/etc/caddy/Caddyfile`, and `/etc/caddy/sites.d/00-placeholder.caddy`.
- `infisical_onramp` -- Infisical onramp deployment directory and Caddy snippet.
- `onclave_onramp` -- Onclave app definition, private env, persistent broker/core data, adopted PostgreSQL and MinIO directories, and Caddy snippet. Rebuildable Ollama data is excluded.

The managed paths live in `infra/ansible/vars/service-state.yml`. Every path
explicitly declares its owner, group, and whether ownership repair is recursive.
Archive modes remain authoritative. `infra/services.json` is authoritative for
CLI eligibility through each service's `state_capable` metadata; add a target to
both files when this repo starts managing a new stateful service.

## Operator notes

- Before writing a controller-backed backup, the CLI restricts `values/service-backups/` on Windows to the current user, SYSTEM, and Administrators with inheritable ACLs. POSIX hosts enforce mode `0700`. Missing host permission tools fail closed instead of writing an exposed archive.
- Run controller-backed backups before rebuilding or replacing a service host. `just apply` verifies the newest controller archive checksum and manifest for every affected stateful service and requires it to be no older than 24 hours. Device-local Onclave backups are for application rollback, not host replacement.
- `scripts/service-state.sh backup onclave_onramp` leaves an active Onclave user service unavailable only while it creates and atomically installs the uncompressed cold archive. It then restarts that same service even if later background compression fails. Caddy remains running, and an inactive Onclave service remains inactive.
- Onclave backup history is device-local by design. It is fast and simple, but it does not survive loss of the Onramp host. Use a separate off-device copy mechanism if host-loss recovery becomes a requirement.
- A destructive plan affecting multiple stateful services is blocked by default. Use `INFRA_TARGET_SERVICE=<service> just plan` for the canary rollout, verify its direct endpoint and state, then create the next plan.
- Backup archives are not git-tracked. Use a separate mechanism for off-site
  archive storage and durability.
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
