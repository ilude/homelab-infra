# App-host runbook

The optional `onramp_host` service creates a Debian 13 VM substrate for Podman services. It is not a SearXNG deployment by itself; enable `searxng_onramp` with `onramp_host` when this repo should temporarily manage SearXNG on that VM.

## Enable or disable

- Enable host only: add `onramp_host` to `settings.local.json` services and fill the private `values/terraform.tfvars` onramp-host fields.
- Enable temporary SearXNG: add both `onramp_host` and `searxng_onramp`, then set `SEARXNG_SECRET_KEY`, `HERMES_WEB_SEARXNG_URL`, `searxng_server_name`, and `searxng_public_url` in private values.
- Disable SearXNG only: remove `searxng_onramp`, remove or update its DNS/Hermes private values, then run a reviewed `just plan` before any apply.
- Disable host: remove `onramp_host` from `settings.local.json` services, then run a reviewed `just plan` before any apply.

Removing `onramp_host` can cause OpenTofu to plan VM changes or destroy actions. Do not run `just apply`, destroy, import, or state surgery without explicit approval.

## Private values source of truth

`values/terraform.tfvars` owns the onramp-host VM shape:

- VMID, hostname, Debian 13 genericcloud image URL/file name, datastore, CPU, memory, disk
- static IPv4/CIDR, gateway, DNS servers, search domain, bridge, optional VLAN
- cloud-init/bootstrap user, SSH public keys, deploy user, deploy directory, SSH policy, and firewall source CIDRs

Tracked scaffold values use only placeholders such as `onramp-host.example.internal`, `searxng.apps.example.net`, and `192.0.2.0/24`. The onramp-host VM must be built from a clean cloud image; do not point it at a mutable VM template with existing cloud-init state.

Temporary SearXNG private values are:

- `values/.env`: `SEARXNG_SECRET_KEY` and `HERMES_WEB_SEARXNG_URL`
- `values/terraform.tfvars`: `searxng_server_name`, `searxng_public_url`, container image/port/bind variables
- `values/dns-records.local.json`: `searxng.apps.<domain>` mapped to the onramp-host IP

## Future deployment validation

A later live deployment plan must:

1. Run `just plan` and summarize creates, changes, and destroys.
2. Obtain explicit operator approval before `just apply`.
3. Run `just apply` to create/configure the VM and onramp-host readiness role.
4. Verify SSH reachability as the Onramp deploy user.
5. Verify rootless `podman info`, the selected Compose provider, rootless socket semantics if used, and deployment directory ownership.
6. If `searxng_onramp` is enabled, let this repo deploy SearXNG through Ansible on the onramp host.
7. Verify Caddy on the onramp host and confirm no default host-published app ports exist outside approved proxy ports 80/443.
8. Confirm private `HERMES_WEB_SEARXNG_URL` points to the SearXNG endpoint and smoke-test Hermes search integration once the plugin/runtime exists.

## Rollback choices

Before applying a rollback, decide whether the VM should be retained or deleted.

- Retain VM: remove or pause Onramp workloads, remove `onramp_host` from active orchestration only when a reviewed `just plan` shows acceptable changes, and keep private DNS/inventory values for future reuse.
- Delete VM: stop Onramp workloads first, clean up Onramp app state and proxy records, remove `onramp_host` from settings, review `just plan`, then apply only after explicit approval.

DNS cleanup belongs to the component that created the records. While `searxng_onramp` is enabled, Technitium records for SearXNG are synced by `homelab-infra`; after handoff, app reverse-proxy names should move to the Onramp-owned path. Private values follow-up may include removing `HERMES_WEB_SEARXNG_URL`, `SEARXNG_SECRET_KEY`, SearXNG tfvars, onramp-host tfvars, and Onramp inventory entries.

Do not perform OpenTofu state surgery, import, destroy, or live mutation without explicit approval and a rollback path.
