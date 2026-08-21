# Onramp App Platform Contract

## Purpose

This contract defines the boundary between `homelab-infra`, `onramp-vNext`, and Hermes for general Docker application services. It keeps this repository focused on durable infrastructure while allowing Hermes to operate across infrastructure and app-platform workflows. Cross-repository architecture decisions are governed by the 2026-07-26 Homelab Platform Architecture PRD, held in the Onclave repository at `docs/PRDS/2026-07-26-homelab-platform-architecture-PRD.md`.

The selected future direction is option 3: `homelab-infra remains the durable infrastructure substrate`, `onramp-vNext owns Docker app services`, and `Hermes operates across both` through approved repo-native commands. SearXNG is internal to the Onclave app workload; this repository does not own a standalone SearXNG deployment.

## Current operating reality

Architecture direction does not substitute for deployed tooling. Until an `onramp-vNext` repository and working deployment control plane are present, validated, and adopted, `homelab-infra` is the available owner for Docker services deployed to its managed `onramp_host`. Implement those services with the existing Ansible, BWS, shared Caddy, and service-state contracts. Do not block or redirect a current service request to `onramp-vNext` merely because this document names it as the future owner.

When `onramp-vNext` becomes operational, migrate eligible application workloads through an explicit cutover. Future ownership begins after that cutover, not when the architecture is proposed or documented.

## Ownership

`homelab-infra` currently owns durable infrastructure resources, first-class services, and Docker service deployment to its managed hosts: Proxmox resources, service LAN addressing, static infrastructure DNS, Caddy configuration, Ansible roles, application lifecycle, and OpenTofu state. BWS owns the configuration families, enabled-service list, and runtime secrets consumed by those workflows; SeaweedFS owns the encrypted OpenTofu state.

`onramp-vNext` is the intended future owner of Docker app services after its deployment tooling exists and the applicable workloads are cut over. That future scope includes application catalog entries, Compose or Podman workload definitions, app lifecycle, app-level health checks, and app-specific configuration that does not require infrastructure resource ownership. Onclave remains an app workload rather than a first-class infrastructure service.

Hermes is the operator cockpit. It may summarize status, run approved validation and planning commands, and guide the operator through approval gates. Hermes must not become a third source of truth for infrastructure or app deployment state.

## Provisioning Ownership

`homelab-infra` owns all Proxmox guest provisioning, including LXC and VM creation, sizing, addressing, and OpenTofu state. `onramp-vNext` targets hosts that already exist and does not create guests. Its public-MVP scope item `onramp host provision proxmox` is withdrawn.

Provisioning cannot be split between control planes because OpenTofu holds the state and will not see resources created externally.

## Catalog Ownership

`homelab-infra` is the current deployable service registry for its managed hosts. `onclave` is the alpha incubator for AI tooling and services. After `onramp-vNext` becomes operational, proven application services may be promoted into its catalog through an explicit migration. Incubating services carry no stability expectation.

## DNS Contract

`homelab-infra` may provision DNS needed for the onramp-host substrate and durable infrastructure services. Onramp app services should normally use an approved app-platform DNS convention, such as a wildcard or delegated subdomain, rather than one OpenTofu-managed static record per app.

Specific app DNS records can be promoted into `homelab-infra` only when a separate approved infrastructure plan justifies that they are durable platform resources or a temporary repo-owned exception. Onclave's internal SearXNG has no standalone DNS record in this repository.

## Caddy Contract

First-class infrastructure services in this repository continue to use service-local Caddy by default. Technitium must not become a general ingress proxy for unrelated app services.

Onramp owns Caddy or reverse-proxy configuration for Onramp app services by default. Onclave's internal SearXNG is not routed through the host Caddy instance. The Onramp service `port` field means the container/service port reachable on the Compose network; it must not be reinterpreted as a host-published port unless a later contract explicitly changes that convention.

Onclave does not publish AMQP on LAN or public interfaces. RabbitMQ AMQP and management bind to loopback only; clients outside the onramp host require an approved local transport or tunnel. The Onclave API uses the onramp host's shared Caddy instance.

## Secrets Contract

Infrastructure configuration families and runtime secrets belong in BWS. Encrypted OpenTofu state belongs in SeaweedFS, and the ignored `values/` repo retains only excluded backups, artifacts, dumps, mutable service-state data, and its applicable Forgejo workflow. The local `settings.local.json` contains only the BWS project/API locator; none of these contracts belong in tracked public files.

Bitwarden Secrets Manager is the single backend for Onramp app secrets. Infisical is one provider, not the source of truth. Services declare the secret names they require, not where those secrets live. Hermes may reference whether required secrets are configured, but it must not print secret values, tokens, private domains, private hostnames, or private IP addresses.

## State Contract

OpenTofu state in this repository tracks infrastructure resources owned by `homelab-infra` and is stored encrypted in SeaweedFS. Onramp app services are not managed by OpenTofu by default and must not be added to the BWS `HOMELAB_TERRAFORM_TFVARS` family, the BWS `HOMELAB_ANSIBLE_INVENTORY` family, or OpenTofu state unless a separate approved infrastructure plan promotes that service or resource into this repository.

Docker app deployment state currently belongs to the repository and runtime that actually deploy them, which is `homelab-infra` for services on its managed `onramp_host`. After an explicit cutover, migrated app deployment state belongs to `onramp-vNext` and its runtime. Hermes may aggregate state for operator visibility, but aggregated status is read-only evidence, not source-of-truth state.

## Approval Contract

`homelab-infra` mutation continues to require the reviewed workflow: `just validate`, reviewed `just plan`, and `just apply` only after explicit approval. Destroy, import, state surgery, router/firewall changes, or live service mutation require their own explicit approval.

Onramp app deployment approvals are owned by the Onramp workflow. Hermes can request approval and run approved commands only when the target repo and operation define a safe, repeatable path.

## Onramp Host Runtime

The default future onramp host is a Debian 13 VM running Podman. A VM provides stronger isolation and clearer operational boundaries for a general app substrate than nested containers in a Proxmox LXC.

Podman-in-LXC is experimental. It may be tested for lightweight workloads, but it requires explicit compatibility validation and must not be the default onramp-host direction for general app services.

## SearXNG boundary

SearXNG is an internal dependency of the Onclave app workload. Its image, secret, Compose definition, network, and runtime behavior remain owned by the Onclave application contract. `homelab-infra` consumes that contract through `onclave_onramp` and does not expose or manage a standalone SearXNG service.

## App Workload Decisions

Onclave deploys as an app workload on the homelab-managed `onramp_host`. Its source repository owns the host-agnostic app definition and image contract; this repository owns the selected host, private DNS inputs, secret delivery, and the role that consumes the definition. The consumption path must use digest-pinned images and the app definition's declared environment contract.

The Onclave source repository publishes a reusable app definition and immutable image contract. `onclave_onramp` verifies and consumes that definition, applies consumer-owned networking and storage bindings, and keeps source and image references digest-pinned. Do not replace this path with mutable images, local source builds, or duplicate Compose definitions.

The `onclave_onramp` service is a temporary exception. It exits when `onramp-vNext` can receive workloads. At that point, Onclave is evicted to `onramp-vNext`, and the Ansible role is deleted, not generalized.

Onclave exposes its API through the onramp host's shared Caddy instance. RabbitMQ AMQP and management remain loopback-only with no LAN or public listener. Internal Compose services continue to use `rabbitmq:5672`; clients outside the onramp host require an approved local transport or tunnel. PostgreSQL, MinIO, Ollama, SearXNG, and Docling remain internal to the workload network. `scripts/service-state.sh backup onclave_onramp` atomically creates an uncompressed device-local recovery archive for the Onclave deployment, Caddy snippet, adopted PostgreSQL data, and MinIO payloads. An active Onclave user service is unavailable only while the cold archive is created; Caddy stays running, background compression retains five archives total including the current snapshot, and rebuildable Ollama data is excluded.

Hermes remains a first-class service in this repository while it serves as the cross-platform operator cockpit. Reconsider its placement only when it can join the Onclave fabric as an agent without losing its managed artifact and state controls. Infisical, Technitium, Forgejo, Tailscale, Forgejo Runner, and `onramp_host` remain infrastructure substrate.

## Future Provisioning Gate

Future provisioning gate: onramp-host infrastructure work must be implemented in a separate reviewed plan before any live infrastructure mutation. That plan must include public-safe scaffold updates, BWS family migration guidance if needed, `just validate`, reviewed just plan output, and explicit approval before `just apply`.

For live changes, run `just validate`, review `just plan`, and obtain explicit approval before `just apply`. Onclave changes must preserve its internal SearXNG image, secret, network, and runtime contract.
