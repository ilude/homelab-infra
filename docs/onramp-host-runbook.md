# App-host runbook

The optional `onramp_host` service creates a Debian 13 VM substrate for rootless Podman services and owns the shared Caddy instance. It is not an app deployment by itself; enable app services such as `infisical_onramp`, `searxng_onramp`, or `onclave_onramp` with `onramp_host` when this repo should manage those workloads on that VM.

## Enable or disable

- Enable host only: add `onramp_host` to `settings.local.json` services and fill the private `values/terraform.tfvars` onramp-host fields.
- Enable Infisical onramp: add both `onramp_host` and `infisical_onramp`, then set the Infisical private secrets and point `infisical_server_name` DNS at the onramp host.
- Enable temporary SearXNG: add both `onramp_host` and `searxng_onramp`, then set `SEARXNG_SECRET_KEY`, `HERMES_WEB_SEARXNG_URL`, `searxng_server_name`, and `searxng_public_url` in private values.
- Enable Onclave: add both `onramp_host` and `onclave_onramp`, store the RabbitMQ credentials in the configured Bitwarden Secrets Manager project, then set the BWS project/server configuration, app/image pins, HTTP server name, and Technitium record in private values. RabbitMQ AMQP and management remain loopback-only with no LAN or public listener. Clients outside the onramp host require an approved local transport or tunnel.
- Disable SearXNG only: remove `searxng_onramp`, remove or update its DNS/Hermes private values, then run a reviewed `just plan` before any apply.
- Disable host: remove `onramp_host` from `settings.local.json` services, then run a reviewed `just plan` before any apply.

Removing `onramp_host` can cause OpenTofu to plan VM changes or destroy actions. Do not run `just apply`, destroy, import, or state surgery without explicit approval.

## Private values source of truth

`values/terraform.tfvars` owns the onramp-host VM shape:

- VMID, hostname, Debian 13 genericcloud image URL/file name, datastore, CPU, memory, disk
- static IPv4/CIDR, gateway, DNS servers, search domain, bridge, optional VLAN
- cloud-init/bootstrap user, SSH public keys, deploy user, deploy directory, SSH policy, and firewall source CIDRs. New scaffold values use `anvil` for both the cloud-init and deploy user, and the cloud-init keys fall back to `lxc_ssh_public_keys` when `onramp_host_ssh_public_keys` is empty.

Tracked scaffold values use only placeholders such as `onramp-host.example.internal`, `searxng.apps.example.net`, and `192.0.2.0/24`. The scaffold reserves 128 GB because a state import and the restore workflow's pre-restore snapshot can coexist temporarily. The onramp-host VM must be built from a clean cloud image; do not point it at a mutable VM template with existing cloud-init state.

After increasing an existing VM disk, verify both the block device and mounted filesystem with `lsblk` and `df`. Proxmox expands the virtual disk but does not guarantee that the guest partition and filesystem grow. For the scaffold's ext4 root on `/dev/sda1`, reviewed maintenance can use `growpart /dev/sda 1` followed by `resize2fs /dev/sda1`; verify the actual root device before running either command.

Onramp services use the shared system Caddy instance from `onramp_host`. The base Caddyfile imports `/etc/caddy/sites.d/*.caddy`; each app role owns only its own snippet and must not overwrite `/etc/caddy/Caddyfile`.

Onclave private values are:

- Bitwarden Secrets Manager: `RABBITMQ_DEFAULT_USER` and `RABBITMQ_DEFAULT_PASS`.
- BWS `HOMELAB_ANSIBLE_INVENTORY`: BWS project/API server configuration, source Compose checksum, digest-pinned RabbitMQ and core images, `onclave_onramp_authorized_keys` (for example, `ssh-ed25519 <public-key> operator@example.invalid`), and the adopted PostgreSQL database and user inputs, `onclave_onramp_postgres_database` and `onclave_onramp_postgres_user`. Their physical values remain `menos`.
- Standalone BWS runtime secrets: `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS`, and the Onclave Vault credentials: `ONCLAVE_VAULT_POSTGRES_PASSWORD`; `ONCLAVE_VAULT_S3_ACCESS_KEY` and `ONCLAVE_VAULT_S3_SECRET_KEY`; `ONCLAVE_VAULT_SEARXNG_SECRET`; `ONCLAVE_VAULT_WEBSHARE_PROXY_USERNAME` and `ONCLAVE_VAULT_WEBSHARE_PROXY_PASSWORD`; `ONCLAVE_VAULT_YOUTUBE_API_KEY`; and `ONCLAVE_VAULT_OPENROUTER_API_KEY` and `ONCLAVE_VAULT_ANTHROPIC_API_KEY`. `ONCLAVE_VAULT_OPENAI_API_KEY`, `ONCLAVE_VAULT_CALLBACK_URL`, and `ONCLAVE_VAULT_CALLBACK_SECRET` are optional and may be absent or empty. Do not place any of these application credentials in `HOMELAB_ENV`.
- `values/dns-records.local.json`: the Onclave name, such as `onclave.example.internal`, mapped to the onramp-host IP.

For an existing BWS configuration, run the dry-run and write migration documented in [`scaffold/README.md`](../scaffold/README.md#onclave-input-migration). It renames inputs only; the adopted `/menos/data` directory, PostgreSQL database/user, and S3 bucket remain named `menos`. It fails before mutation when a legacy `all.vars` key uses quoted or flow-style YAML, so rewrite that key in plain block style before retrying.

The controller receives only `BITWARDEN_ACCESS_KEY` from the operator environment and resolves the Onclave secrets before running the role. The bootstrap credential is not copied to the managed host. The role verifies the source Compose checksum, binds RabbitMQ AMQP and management to loopback with no LAN or public listener, keeps the internal Compose service URL `rabbitmq:5672`, binds the Onclave API to loopback behind shared Caddy, and stores RabbitMQ/core data below the service deployment directory for backup coverage. Clients outside the onramp host require an approved local transport or tunnel.

Before changing Onclave state, create the device-local recovery archive with `scripts/service-state.sh backup onclave_onramp`. The command includes the Onclave deployment, Caddy snippet, and adopted PostgreSQL and MinIO data. An active Onclave user service is unavailable only while the uncompressed cold archive is created, Caddy stays running, and an inactive Onclave service remains inactive. Compression and five-archive retention continue in the background. Restore the current archive with `scripts/service-state.sh restore onclave_onramp latest`. Device-local history does not protect against loss of the Onramp host. Ollama data is rebuildable and is not archived.

Temporary SearXNG private values are:
- `values/.env`: `SEARXNG_SECRET_KEY` and `HERMES_WEB_SEARXNG_URL`
- `values/terraform.tfvars`: `searxng_server_name`, `searxng_public_url`, container image/port/bind variables
- `values/dns-records.local.json`: `searxng.apps.<domain>` mapped to the onramp-host IP

## Future deployment validation

A later live deployment plan must:

1. Run `just plan` and summarize creates, changes, and destroys.
2. Obtain explicit operator approval before `just apply`.
3. Run `just apply` to create/configure the VM and onramp-host readiness role.
4. Verify SSH reachability as the Onramp deploy user, `anvil` by default.
5. Verify rootless `podman info`, the selected Compose provider, rootless socket semantics if used, and deployment directory ownership.
6. If app services such as `infisical_onramp`, `searxng_onramp`, or `onclave_onramp` are enabled, let this repo deploy them through Ansible on the onramp host.
7. Verify Caddy on the onramp host, confirm no host-published app ports exist outside approved proxy ports 80/443, and confirm RabbitMQ AMQP has no LAN or public listener.
8. Confirm private `HERMES_WEB_SEARXNG_URL` points to the SearXNG endpoint and smoke-test Hermes search integration once the plugin/runtime exists.
9. For Onclave, verify the core health response reports broker connectivity and topology declaration, then verify AMQP only through an approved local transport or tunnel, not a direct LAN connection.

## Rollback choices

Before applying a rollback, decide whether the VM should be retained or deleted.

- Retain VM: remove or pause Onramp workloads, remove `onramp_host` from active orchestration only when a reviewed `just plan` shows acceptable changes, and keep private DNS/inventory values for future reuse.
- Delete VM: stop Onramp workloads first, clean up Onramp app state and proxy records, remove `onramp_host` from settings, review `just plan`, then apply only after explicit approval.

DNS cleanup belongs to the component that created the records. While `searxng_onramp` is enabled, Technitium records for SearXNG are synced by `homelab-infra`; after handoff, app reverse-proxy names should move to the Onramp-owned path. Private values follow-up may include removing `HERMES_WEB_SEARXNG_URL`, `SEARXNG_SECRET_KEY`, SearXNG tfvars, onramp-host tfvars, and Onramp inventory entries.

Do not perform OpenTofu state surgery, import, destroy, or live mutation without explicit approval and a rollback path.
