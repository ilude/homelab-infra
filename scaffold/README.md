# Private excluded-data repository

This repository is retained only for private data that is deliberately outside the BWS site-configuration snapshot:

- service-state backup archives and checksums
- database dumps and migration artifacts
- cached release artifacts
- OCI or object-data exports
- mutable Hermes state archives

Do not add site configuration or OpenTofu state here. BWS is authoritative for the rendered `.env`, tfvars, Ansible inventory, DNS records, and operator settings. SeaweedFS is authoritative for encrypted OpenTofu state.

The public runbook checkout ignores `values/`, so initialize this directory as its own private Git repository. See [`docs/bws-seaweedfs-state.md`](../docs/bws-seaweedfs-state.md) in the public runbook for bootstrap, recovery, and validation procedures.

## Onclave input migration

BWS owns the site configuration families, so do not recreate removed configuration files in this excluded-data repository. To migrate an existing BWS-backed configuration, run the public migration in dry-run mode, review the key-only status, then rerun with `--write`:

```bash
docker compose run --rm infra python scripts/bws-snapshot.py \
  --settings settings.local.json migrate-onclave
docker compose run --rm infra python scripts/bws-snapshot.py \
  --settings settings.local.json migrate-onclave --write
```

The migration extracts retired `MENOS_*` application credentials from `HOMELAB_ENV`, creates or reuses matching standalone `ONCLAVE_VAULT_*` BWS runtime secrets, then removes the application credential lines from that family. It checks collisions before writing, reports keys only during dry-run, and can resume after a partial write. It also renames inventory variables and environment lookup tokens. It fails before mutation when a legacy `all.vars` key uses quoted or flow-style YAML; rewrite that key in plain block style and rerun. The adopted `/menos/data` directory, `menos` PostgreSQL database/user, and `menos` S3 bucket remain unchanged. `ONCLAVE_VAULT_OPENAI_API_KEY`, `ONCLAVE_VAULT_CALLBACK_URL`, and `ONCLAVE_VAULT_CALLBACK_SECRET` are optional.
