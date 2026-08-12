# App-host runbook

The optional `onramp_host` service creates a Debian 13 VM substrate for rootless Podman services and owns the shared Caddy instance. It is not an app deployment by itself; enable app services such as `infisical_onramp`, `searxng_onramp`, or `onclave_onramp` with `onramp_host` when this repo should manage those workloads on that VM.

## Enable or disable

- Enable host only: add `onramp_host` to `settings.local.json` services and fill the private `values/terraform.tfvars` onramp-host fields.
- Enable Infisical onramp: add both `onramp_host` and `infisical_onramp`, then set the Infisical private secrets and point `infisical_server_name` DNS at the onramp host.
- Enable temporary SearXNG: add both `onramp_host` and `searxng_onramp`, then set `SEARXNG_SECRET_KEY`, `HERMES_WEB_SEARXNG_URL`, `searxng_server_name`, and `searxng_public_url` in private values.
- Enable Onclave: add both `onramp_host` and `onclave_onramp`, store the RabbitMQ credentials in the configured Bitwarden Secrets Manager project, then set the BWS project/server configuration, app/image pins, HTTP server name, and Technitium record in private values. AMQP is the only LAN-published app port; its firewall sources inherit the approved onramp-host CIDRs. RabbitMQ management remains loopback-only.
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
- `values/ansible/inventory/local.yml`: BWS project/API server configuration, source Compose checksum, digest-pinned RabbitMQ and core images, `menos_authorized_keys` (for example, `ssh-ed25519 <public-key> operator@example.invalid`), and the adopted PostgreSQL database and user inputs, `menos_postgres_database` and `menos_postgres_user`.
- `values/.env`: the adopted unified Onclave secrets: `MENOS_POSTGRES_PASSWORD`; `MENOS_S3_ACCESS_KEY` and `MENOS_S3_SECRET_KEY`; `MENOS_SEARXNG_SECRET`; `MENOS_WEBSHARE_PROXY_USERNAME` and `MENOS_WEBSHARE_PROXY_PASSWORD`; `MENOS_YOUTUBE_API_KEY`; and the model-provider keys `MENOS_OPENROUTER_API_KEY` and `MENOS_ANTHROPIC_API_KEY`. `MENOS_OPENAI_API_KEY` is optional when the selected model configuration needs it.
- `values/dns-records.local.json`: the Onclave name, such as `onclave.example.internal`, mapped to the onramp-host IP.

The `menos_` and `MENOS_` names remain the private compatibility inputs for the unified Onclave deployment because it adopts the existing Menos state. They are not a request to restore the retired Menos workload.

The controller receives only `BITWARDEN_ACCESS_KEY` from the operator environment and resolves the Onclave secrets before running the role. The bootstrap credential is not copied to the managed host. The role verifies the source Compose checksum, keeps AMQP published for approved LAN clients, binds the Onclave API to loopback behind shared Caddy, keeps RabbitMQ management loopback-only, and stores RabbitMQ/core data below the service deployment directory for backup coverage.

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

## Rollback choices

Before applying a rollback, decide whether the VM should be retained or deleted.

- Retain VM: remove or pause Onramp workloads, remove `onramp_host` from active orchestration only when a reviewed `just plan` shows acceptable changes, and keep private DNS/inventory values for future reuse.
- Delete VM: stop Onramp workloads first, clean up Onramp app state and proxy records, remove `onramp_host` from settings, review `just plan`, then apply only after explicit approval.

DNS cleanup belongs to the component that created the records. While `searxng_onramp` is enabled, Technitium records for SearXNG are synced by `homelab-infra`; after handoff, app reverse-proxy names should move to the Onramp-owned path. Private values follow-up may include removing `HERMES_WEB_SEARXNG_URL`, `SEARXNG_SECRET_KEY`, SearXNG tfvars, onramp-host tfvars, and Onramp inventory entries.

Do not perform OpenTofu state surgery, import, destroy, or live mutation without explicit approval and a rollback path.
