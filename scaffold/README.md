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

## Herdr remote-LXC example boundary

Herdr site configuration remains in the BWS configuration families. Do not add these examples, rendered `.env` files, tfvars, inventory, DNS records, SSH private keys, or runtime state to this excluded-data repository. The following is a documentation-only public example for review; it is not a second configuration source:

```text
services: ["herdr", "onramp_host"]
herdr_server_name: herdr.example.internal
herdr_operator_user: herdr
herdr_allowed_ssh_cidrs: ["192.0.2.0/24"]
herdr_password_authentication: false
herdr_permit_root_login: false
```

The Herdr binary is fetched from its pinned official release URL and checked against its pinned SHA256. The operator uses the direct non-root Herdr SSH endpoint. Inside the Herdr LXC, the `herdr-onramp` Docker context uses `ssh://herdr-onramp`; the remote restricted key may run only the exact `docker system dial-stdio` relay to the rootless Podman socket. The Pi package and bundled Herdr integration are installed inside Herdr as the operator. The generated transport private key remains only in Herdr; only its public half reaches onramp. See [`docs/herdr-remote-lxc.md`](../docs/herdr-remote-lxc.md) for the full public contract and [`../.specs/herdr-remote-lxc/plan.md`](../.specs/herdr-remote-lxc/plan.md) for the reviewed rollout boundary.
