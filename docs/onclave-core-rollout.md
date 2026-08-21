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

The controller downloads the commit-pinned Compose definition and both pinned
PostgreSQL helper scripts. A core-only rollout is refused if any of those
contracts differ from the currently deployed source revision. It computes their
SHA-256 values and updates only these `HOMELAB_ANSIBLE_INVENTORY` pins:

- Onclave source SHA and app-definition URL/checksum
- PostgreSQL backup and restore helper checksums
- core image tag and immutable digest

The prior pin set is recorded in `.tmp/onclave-core-rollout/`. BWS is updated
only after the rendered inventory still matches the BWS value observed before
the change. If the core-only deployment or validation fails, the controller
restores the prior inventory pins and redeploys the prior core image. A changed
BWS inventory blocks rollback rather than overwriting an operator change.

The Ansible playbook persists the selected core image pins and source revision
in the existing host configuration, uses a temporary Compose override, and runs
`pull` and `up -d --no-deps onclave-core`. It does not run the Onclave systemd unit and
does not restart RabbitMQ, PostgreSQL, MinIO, Ollama, SearXNG, or Caddy. It
fails immediately if the core container exits or reports a restart, then waits
for HTTP `/health` to return `status=ok`, the requested `git_sha`, and
`broker.connected=true`. Failures include at most 200 lines of redacted core
logs.

This workflow does not create a service-state backup. Review the recorded
previous pins and direct health result before any later broad service apply.
