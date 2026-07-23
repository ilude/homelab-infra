# App-host runbook

The optional `onramp_host` service creates a Debian 13 VM substrate for rootless Podman services and owns the shared Caddy instance. It is not an app deployment by itself; enable app services such as `infisical_onramp`, `searxng_onramp`, or `onclave_onramp` with `onramp_host` when this repo should manage those workloads on that VM.

## Enable or disable

- Enable host only: add `onramp_host` to `settings.local.json` services and fill the private `values/terraform.tfvars` onramp-host fields.
- Enable Infisical onramp: add both `onramp_host` and `infisical_onramp`, then set the Infisical private secrets and point `infisical_server_name` DNS at the onramp host.
- Enable temporary SearXNG: add both `onramp_host` and `searxng_onramp`, then set `SEARXNG_SECRET_KEY`, `HERMES_WEB_SEARXNG_URL`, `searxng_server_name`, and `searxng_public_url` in private values.
- Enable Onclave: add both `onramp_host` and `onclave_onramp`, then set the app/image pins, RabbitMQ credentials, HTTP server names, and Technitium records in private values. AMQP is the only LAN-published app port; its firewall sources inherit the approved onramp-host CIDRs.
- Enable Menos: add both `onramp_host` and `menos_onramp`, then set six image pins, required credentials, authorized public keys, the Menos server name, and its Technitium record. Only the API is loopback-bound behind Caddy; dependency ports remain internal.
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

- `values/.env`: `RABBITMQ_DEFAULT_USER` and `RABBITMQ_DEFAULT_PASS`
- `values/ansible/inventory/local.yml`: source Compose checksum, digest-pinned RabbitMQ and core images, and Onclave/RabbitMQ server names
- `values/dns-records.local.json`: Onclave and RabbitMQ names mapped to the onramp-host IP

The role verifies the source Compose checksum, keeps AMQP published for approved LAN clients, binds both HTTP surfaces to loopback behind shared Caddy, and stores RabbitMQ/core data below the service deployment directory for backup coverage.

Menos private values are:

- `values/.env`: database, object-storage, search, proxy, and model-provider credentials
- `values/ansible/inventory/local.yml`: source Compose checksum, six digest-pinned images, the HTTPS server name, and authorized public keys
- `values/dns-records.local.json`: the Menos API name mapped to the onramp-host IP

The Menos service-state archive contains only the source-derived Compose file, private env, authorized keys, and Caddy configuration. PostgreSQL custom-format dumps and MinIO payloads are separate bulk recovery artifacts under the host-local backup boundary and are not included in service-state archives. The role installs checksum-verified `bin/backup-postgres.sh` and `bin/restore-postgres.sh` from the same immutable Onclave revision as the Compose definition. Run them as the deploy user against the existing internal PostgreSQL container without exporting database credentials:

```bash
cd /srv/onramp/menos
postgres_container="$(podman-compose -f compose.yaml ps -q postgres)"
POSTGRES_CONTAINER="${postgres_container}" CONTAINER_RUNTIME=podman \
  ./bin/backup-postgres.sh ./backups/postgres
```

Restore only into an empty PostgreSQL public schema, with the Menos API stopped. Use the same `POSTGRES_CONTAINER` and `CONTAINER_RUNTIME` values with `bin/restore-postgres.sh`, then restart the API and verify `/ready`. Restore PostgreSQL and MinIO sequentially before starting the user service. Cross-host legacy cutover additionally requires the quiesced export/import and parity gates in the Onclave Menos cutover plan.

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
7. Verify Caddy on the onramp host and confirm no host-published app ports exist outside approved proxy ports 80/443 and explicitly approved protocol ports such as Onclave AMQP 5672.
8. Confirm private `HERMES_WEB_SEARXNG_URL` points to the SearXNG endpoint and smoke-test Hermes search integration once the plugin/runtime exists.
9. For Onclave, verify the core health response reports broker connectivity and topology declaration, then test AMQP from an approved LAN client.
10. For Menos, verify `/health` reports the pinned source SHA, `/ready` reports healthy PostgreSQL, S3, and Ollama dependencies, then run signed content, ingest, list, and semantic-search acceptance checks before consumer cutover.

## Rollback choices

Before applying a rollback, decide whether the VM should be retained or deleted.

- Retain VM: remove or pause Onramp workloads, remove `onramp_host` from active orchestration only when a reviewed `just plan` shows acceptable changes, and keep private DNS/inventory values for future reuse.
- Delete VM: stop Onramp workloads first, clean up Onramp app state and proxy records, remove `onramp_host` from settings, review `just plan`, then apply only after explicit approval.

DNS cleanup belongs to the component that created the records. While `searxng_onramp` is enabled, Technitium records for SearXNG are synced by `homelab-infra`; after handoff, app reverse-proxy names should move to the Onramp-owned path. Private values follow-up may include removing `HERMES_WEB_SEARXNG_URL`, `SEARXNG_SECRET_KEY`, SearXNG tfvars, onramp-host tfvars, and Onramp inventory entries.

Do not perform OpenTofu state surgery, import, destroy, or live mutation without explicit approval and a rollback path.
