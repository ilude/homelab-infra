# Hermes state backup and restore

Hermes state backup/restore now uses the generic managed service-state workflow.
The Hermes target captures the runtime user's `.hermes` directory, including
memory/soul files such as `SOUL.md`, configuration, history, logs, and
Hermes-managed backups.

Back up Hermes state:

```bash
scripts/service-state.sh backup hermes
```

The compatibility wrapper still works:

```bash
scripts/hermes-state.sh backup
```

Archives are written under:

```text
values/service-backups/hermes/hermes-state-<timestamp>.tar.gz
values/service-backups/hermes/hermes-state-<timestamp>.tar.gz.sha256
```

Restore a saved Hermes archive:

```bash
scripts/service-state.sh restore hermes values/service-backups/hermes/hermes-state-<timestamp>.tar.gz
```

or:

```bash
scripts/hermes-state.sh restore values/service-backups/hermes/hermes-state-<timestamp>.tar.gz
```

For first-run/rebuild flows where a Hermes backup may not exist yet, use:

```bash
scripts/service-state.sh restore-if-present hermes
```

That command restores the newest normal Hermes backup when one exists;
pre-restore recovery archives are excluded. If no archive exists, it logs a skip
message and exits successfully.

Restore validates the archive and destination before stopping
`hermes-dashboard`. It writes a private pre-restore archive and checksum when
current state exists, restores `.hermes`, and recursively reapplies the
configured Hermes runtime user and group before starting `hermes-dashboard`.
Archived file modes are preserved. Legacy manifestless Hermes archives remain
supported after the same member and link safety checks.

If restore fails after managed paths are changed, services remain stopped and
the command reports the pre-restore recovery archive and checksum for manual
recovery; it does not automatically roll back.

See [Managed service-state backup and restore](service-state-backup.md) for the
shared workflow and other supported service targets.
