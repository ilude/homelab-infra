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

With no archive argument, `restore-if-present` restores the newest archive for
that service when one exists. If no archive exists, it logs a skip message and
exits successfully.

Restore stops the managed service units declared for the service, writes a
pre-restore archive of the current state into `values/service-backups/<service>/`,
restores the selected archive, and starts the managed units again. Backups stream
directly over service SSH into an atomic private `0600` archive. Before any restore
stops services or removes state, the archive is checksum/manifest validated and a
mount-aware capacity preflight must confirm room for the incoming archive, current
state, pre-restore snapshot/archive allowance, and a safety reserve. A capacity
failure makes no guest-state change; expand the affected guest filesystem and rerun
the explicit restore.

Hermes is also restored automatically during guarded bootstrap when its live
`.hermes` directory is missing or empty. The role validates the newest complete
private archive and requires customized `SOUL.md` state before restoring it. An
existing non-empty Hermes state directory is never replaced automatically.

## Supported targets

Current service-state targets are:

- `hermes` — runtime user's `.hermes` directory, including memory/soul files,
  config, history, logs, and Hermes-managed backups.
- `forgejo` — `/etc/forgejo` and `/var/lib/forgejo`.
- `infisical` — legacy Infisical configuration, PostgreSQL, Redis, and attachment data.
- `technitium` — `/etc/dns`.
- `onramp_host` — `/etc/caddy` and the configured onramp deployment directory.
- `infisical_onramp` — Infisical onramp deployment directory and Caddy snippet.
- `searxng_onramp` — SearXNG onramp deployment directory and Caddy snippet.

The definitions live in `infra/ansible/vars/service-state.yml`. Add a target
there when this repo starts managing a new stateful service.

## Operator notes

- Run backups before rebuilding or replacing a service host.
- Review and commit/push the private `values/` repo after a successful backup if
  you want the archive stored in the private remote.
- Restore is normally explicit and service-scoped. Hermes is the exception during
  guarded bootstrap: only missing or empty live state can be restored automatically.
- Use `restore-if-present` for first-run/rebuild flows that should continue when
  no prior private backup exists.
- The workflow uses the normal direct Ansible inventory group for each service.
  If direct SSH to a service host is unavailable, fix service SSH access before
  relying on routine backup/restore.
