# Onclave core-only rollout

Use the public wrapper for a managed core image rollout:

```bash
bash scripts/onclave-core-rollout.sh \
  --source-sha <40-character-commit-sha> \
  --core-digest sha256:<64-character-ghcr-manifest-digest>
```

Omit `--core-digest` to resolve the immutable GHCR manifest digest for the
source SHA. The wrapper runs through `scripts/run-infra.sh`, so BWS is rendered
into an ephemeral snapshot and no local `values/` configuration is used.

## Eligibility and contract handoff

The controller downloads the commit-pinned Compose definition and both pinned
PostgreSQL helper scripts. The helpers must be byte-for-byte unchanged. The two
Compose documents must be semantically identical, with one narrow transition
exception: the exact `onclave-core.healthcheck.test` command may change one way
from `/health` to `/live`. Every other Compose leaf must remain type-sensitively equal. A service
environment, topology, dependency, port, volume, config, restart, or health
timing change is refused and must use the reviewed Onclave role.

The release that first adds the seven job and delivery environment mappings and
the `20260722_job_durability` migration is therefore not eligible for this
workflow. Deploy that release once through the reviewed role. The migration is
additive and idempotent and runs during vault construction before the listener
starts. Successful startup and configured readiness are sufficient migration
evidence; this workflow does not run SQL or attempt a down migration.

For an eligible release, the controller computes artifact SHA-256 values and
updates only these `HOMELAB_ANSIBLE_INVENTORY` pins:

- Onclave source SHA and app-definition URL/checksum
- PostgreSQL backup and restore helper checksums
- core image tag and immutable digest

The prior pin set and compatible health command are recorded in
`.tmp/onclave-core-rollout/`. BWS is updated only after the rendered inventory
still matches the BWS pins observed before the change. If deployment or
validation fails, the controller restores the prior pins and redeploys the
prior core image with its recorded compatible health command. Rollback tolerates
an absent or failed core container and an unavailable old HTTP endpoint long
enough to restore `Image`, `GIT_SHA`, and `HealthCmd`; dependency snapshots remain
mandatory and post-restore validation remains strict. It never assumes that an
older image implements `/live`. A changed BWS inventory blocks rollback
rather than overwriting an operator change.

## Bounded deployment and evidence

The Ansible playbook changes only `Image`, `GIT_SHA`, and the validated
image-compatible `HealthCmd`, then explicitly restarts only
`onclave-core.service`. It does not restart `onclave-onramp.target`, RabbitMQ,
PostgreSQL, SeaweedFS, Ollama, SearXNG, Docling, or Caddy. It records one
explicit restart action separately from systemd `NRestarts` and Podman restart
counts, which represent automatic restarts. Dependency container identities,
PIDs, and automatic restart counts must remain unchanged.

Before deployment, unsupported `/live` or `/metrics` endpoints from an older
compatible image are recorded without failing the preflight. A post-deployment
`/live` contract requires HTTP 200 and exactly `status=ok`. The operational gate
also requires:

- `/health`: HTTP 200 `ok` or HTTP 503 `degraded`, the selected source revision,
  build and app version fields, broker diagnostics, bounded transcript history,
  and the static safe proxy diagnostic
- `/ready`: HTTP 200 `ready`; PostgreSQL, S3, Ollama, broker, the native core's
  required OpenRouter pipeline check, and any selected embedding-provider check
  use only the documented safe tokens and all configured required checks pass
- `/metrics`: HTTP 200 with Prometheus 0.0.4 text content type and `HELP`/`TYPE`
  declarations for all six counter and four duration-summary families, even
  when there are no samples
- core lifecycle: running with zero automatic systemd and container restarts

The rollout record contains pre/post revisions, `affected_units` limited to
`onclave-core.service`, endpoint summaries, metric-family results, the explicit
restart action count, and per-unit automatic restart observations. It does not
store endpoint URLs, credentials, raw health payloads, or metric samples.
Failures include at most 200 lines of redacted core logs.

This workflow does not create a service-state backup. Review the recorded
previous pins and operational evidence before any later broad service apply.
