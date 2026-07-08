# Onramp SearXNG handoff

This is a public-safe handoff for the default future `onramp-vNext` implementation and a record of the current temporary exception.

Current exception: `homelab-infra` owns the optional `searxng_onramp` service for now. It deploys SearXNG on the Debian 13 Podman `onramp_host`, binds the app only on loopback, publishes HTTPS through Caddy on the onramp host, adds the Technitium DNS input, and renders `HERMES_WEB_SEARXNG_URL` for Hermes.

Future target: `onramp-vNext` should own the SearXNG container definition, reverse proxy/Caddy configuration, app deployment workflow, and service lifecycle when this temporary exception is retired.

## Inputs from homelab-infra/private values

- `onramp_host` and `searxng_onramp` are selected in `settings.local.json` only when this repo should manage the temporary workload.
- `searxng_onramp` depends on `onramp_host`; selecting it without `onramp_host` is invalid.
- `values/terraform.tfvars` remains the source of truth for `onramp_host_vmid`, `onramp_host_ipv4_address`, `onramp_host_hostname`, `onramp_host_deploy_user`, `onramp_host_deploy_dir`, `searxng_server_name`, and `searxng_public_url`.
- `values/.env` stores `SEARXNG_SECRET_KEY` and `HERMES_WEB_SEARXNG_URL`.
- Ansible inventory derives the onramp-host SSH target from tfvars; do not duplicate real hostnames or IP addresses in tracked files.

## Current homelab-infra implementation checklist

1. Enable `onramp_host` and `searxng_onramp` together in `settings.local.json`.
2. Keep `searxng_server_name` public-safe in tracked files, for example `searxng.apps.example.net`, and private in `values/terraform.tfvars` for real domains.
3. Keep the SearXNG container host binding loopback-only, for example `127.0.0.1:8080:8080`.
4. Publish browser access through Caddy on the onramp host using Cloudflare DNS-01.
5. Sync the SearXNG A record through Technitium DNS automation.
6. Render Hermes runtime config from `HERMES_WEB_SEARXNG_URL`; Hermes plugin/runtime implementation remains a follow-up.

## Future Onramp implementation checklist

1. Add a SearXNG app/service definition in `onramp-vNext`.
2. Target the `onramp_host` Podman host through private inventory/outputs from this repo.
3. Keep Onramp service `port` fields as container/service ports reachable on the Compose network. Do not reinterpret them as host-published ports.
4. Add Onramp-owned Caddy/reverse-proxy routing for `https://searxng.apps.example.net` or the private equivalent.
5. Forbid default host-published app ports. Only the approved Onramp reverse proxy should bind host ports such as 80/443.
6. Emit or document the final SearXNG URL for private values as `HERMES_WEB_SEARXNG_URL`.
7. Validate the service with an Onramp dry run, Podman deployment, reverse-proxy health check, and Hermes endpoint smoke check in a later reviewed deployment plan.

## Ownership boundary

- `homelab-infra`: current temporary SearXNG deployment, VM substrate, SSH/bootstrap policy, rootless Podman readiness, default-deny firewall posture, Technitium DNS input, Hermes endpoint env wiring, and rollback docs.
- `onramp-vNext`: future SearXNG image/configuration, Compose/Podman service, reverse proxy/Caddy rules, app updates, and app rollback after handoff.
- Hermes: consumes the private SearXNG endpoint through `HERMES_WEB_SEARXNG_URL`; plugin/runtime implementation is a follow-up.

## Rollback or handoff

To stop this repo managing SearXNG, remove `searxng_onramp` from `settings.local.json`, remove or update the SearXNG DNS/Hermes private values, run `just validate`, review `just plan`, and run `just apply` only after explicit approval. Keep `onramp_host` enabled if Onramp will continue using the VM substrate.
