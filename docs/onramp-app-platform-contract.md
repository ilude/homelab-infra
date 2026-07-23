# Onramp App Platform Contract

## Purpose

This contract defines the boundary between `homelab-infra`, `onramp-vNext`, and Hermes for general Docker application services. It keeps this repository focused on durable infrastructure while allowing Hermes to operate across infrastructure and app-platform workflows.

The selected default direction is option 3: `homelab-infra remains the durable infrastructure substrate`, `onramp-vNext owns Docker app services`, and `Hermes operates across both` through approved repo-native commands. The current SearXNG pilot is a temporary exception: `homelab-infra` owns `searxng_onramp` until the service is handed back to Onramp.

## Ownership

`homelab-infra` owns durable infrastructure resources and first-class services: Proxmox resources, service LAN addressing, static infrastructure DNS, service-local Caddy for first-class services, Ansible roles, and OpenTofu state.

`onramp-vNext` owns Docker app services by default. That includes application catalog entries, Compose or Podman workload definitions, app lifecycle, app-level health checks, and app-specific configuration that does not require infrastructure resource ownership. Onclave and Menos are app workloads under this ownership model, not first-class infrastructure services.

Hermes is the operator cockpit. It may summarize status, run approved validation and planning commands, and guide the operator through approval gates. Hermes must not become a third source of truth for infrastructure or app deployment state.

## DNS Contract

`homelab-infra` may provision DNS needed for the onramp-host substrate and durable infrastructure services. Onramp app services should normally use an approved app-platform DNS convention, such as a wildcard or delegated subdomain, rather than one OpenTofu-managed static record per app.

Specific app DNS records can be promoted into `homelab-infra` only when a separate approved infrastructure plan justifies that they are durable platform resources or a temporary repo-owned exception. `searxng_onramp` currently uses a Technitium-managed `searxng.apps.example.net` placeholder record mapped to the onramp host.

## Caddy Contract

First-class infrastructure services in this repository continue to use service-local Caddy by default. Technitium must not become a general ingress proxy for unrelated app services.

Onramp owns Caddy or reverse-proxy configuration for Onramp app services by default. The temporary `searxng_onramp` exception installs Caddy on `onramp_host` from this repo and proxies only to the loopback-bound SearXNG container. The Onramp service `port` field means the container/service port reachable on the Compose network; it must not be reinterpreted as a host-published port unless a later contract explicitly changes that convention.

Onclave is an explicit protocol exception to loopback-only HTTP publishing: AMQP is a TCP service, so its broker port may be published on the LAN with a Technitium A or CNAME record. Onclave health, RabbitMQ management, and Menos API surfaces are HTTP services and should use the onramp host's shared Caddy instance rather than direct LAN port publication.

## Secrets Contract

Infrastructure secrets, Proxmox credentials, DNS API tokens, OpenTofu state, and private inventory belong in the ignored `values/` repo or approved local secret stores. They must not be copied into tracked public files.

Onramp app secrets belong to the app-platform secret mechanism selected by `onramp-vNext`. Hermes may reference whether required secrets are configured, but it must not print secret values, tokens, private domains, private hostnames, or private IP addresses.

## State Contract

OpenTofu state in this repository tracks infrastructure resources owned by `homelab-infra`. Onramp app services are not managed by OpenTofu by default and must not be added to values/terraform.tfvars, Ansible inventory, or OpenTofu state unless a separate approved infrastructure plan promotes that service or resource into this repository.

Onramp app deployment state belongs to `onramp-vNext` and its runtime. Hermes may aggregate state for operator visibility, but aggregated status is read-only evidence, not source-of-truth state.

## Approval Contract

`homelab-infra` mutation continues to require the reviewed workflow: `just validate`, reviewed `just plan`, and `just apply` only after explicit approval. Destroy, import, state surgery, router/firewall changes, or live service mutation require their own explicit approval.

Onramp app deployment approvals are owned by the Onramp workflow. Hermes can request approval and run approved commands only when the target repo and operation define a safe, repeatable path.

## Onramp Host Runtime

The default future onramp host is a Debian 13 VM running Podman. A VM provides stronger isolation and clearer operational boundaries for a general app substrate than nested containers in a Proxmox LXC.

Podman-in-LXC is experimental. It may be tested for lightweight workloads, but it requires explicit compatibility validation and must not be the default onramp-host direction for the SearXNG pilot or other general app services.

## SearXNG Pilot

SearXNG is classified as an Onramp app-platform service by default. It is useful beyond Hermes, is naturally packaged as an app workload, and should not force this repository to add a first-class LXC for every plugin backend.

Current exception: `homelab-infra` temporarily owns the `searxng_onramp` service. It depends on `onramp_host`, deploys SearXNG with rootless Podman, binds the app only on loopback, publishes HTTPS through Caddy on the onramp host, adds Technitium DNS input, and renders `HERMES_WEB_SEARXNG_URL` for Hermes. This exception should be removed or migrated when Onramp takes over the app definition.

## App Workload Decisions

Onclave and Menos deploy as app workloads on the homelab-managed `onramp_host`. Their source repository owns the host-agnostic app definitions and image contracts; this repository owns the selected host, private DNS inputs, secret delivery, and the role that consumes those definitions. The consumption path must use digest-pinned images and the app definition's declared environment contract.

The Onclave source repository publishes reusable app definitions and immutable image contracts for Onclave and Menos. `onclave_onramp` and `menos_onramp` verify and consume those definitions, apply consumer-owned networking and storage bindings, and keep source and image references digest-pinned. Do not replace these paths with mutable images, local source builds, or duplicate Compose definitions.

Menos exposes only its API through the onramp host's shared Caddy instance. PostgreSQL, MinIO, Ollama, SearXNG, and Docling remain internal to the workload network. Service-state archives cover the Compose definition, private environment, authorized keys, and Caddy configuration. PostgreSQL logical dumps and MinIO payloads remain separate host-local bulk recovery artifacts. PostgreSQL backup and restore helpers are checksum-verified from the same immutable Onclave revision as the app definition and execute database tools inside the internal PostgreSQL container without placing credentials in host command arguments.

Hermes remains a first-class service in this repository while it serves as the cross-platform operator cockpit. Reconsider its placement only when it can join the Onclave fabric as an agent without losing its managed artifact and state controls. SearXNG remains an Onramp handoff candidate. Infisical, Technitium, Forgejo, Tailscale, Forgejo Runner, and `onramp_host` remain infrastructure substrate.

## Future Provisioning Gate

Future provisioning gate: onramp-host infrastructure work must be implemented in a separate reviewed plan before any live infrastructure mutation. That plan must include public-safe scaffold updates, private values migration guidance if needed, `just validate`, reviewed just plan output, and explicit approval before `just apply`.

For live changes, run `just validate`, review `just plan`, and obtain explicit approval before `just apply`. To roll back the temporary SearXNG exception, disable `searxng_onramp`, remove or update the SearXNG DNS/Hermes private values, rerun plan, and apply only after approval.
