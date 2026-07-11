# Documentation Index

Public-safe documentation for this homelab infrastructure runbook.

## Operator and platform docs

- [Hermes operator pilot PRD](hermes-operator-pilot-prd.md) defines the Hermes cockpit requirements, safety boundaries, and SearXNG pilot classification.
- [Managed service-state backup and restore](service-state-backup.md) covers private `values/` backups for Hermes memory/soul state and other managed service state.
- [Forgejo bind-mount lifecycle](forgejo-bind-mount.md) documents the SSH/pct-managed recovery boundary and fail-closed ownership contract.
- [Hermes state backup and restore](hermes-state-backup.md) keeps the Hermes-specific compatibility notes.
- [Hermes tuning](hermes-tuning.md) documents managed compression and delegation settings.
- [Onramp app-platform contract](onramp-app-platform-contract.md) defines the `homelab-infra`, `onramp-vNext`, and Hermes ownership split for onramp-host services.
- [Debian baseline](debian-baseline.md) documents the verified Debian 13 LXC baseline and the separately pinned Debian 13 onramp-host image.
- [Onramp SearXNG handoff](onramp-searxng-handoff.md) gives `onramp-vNext` the future SearXNG-on-Podman contract and records the current temporary `searxng_onramp` exception.
- [App-host runbook](onramp-host-runbook.md) covers `onramp_host` and `searxng_onramp` enable/disable, rollback, and live deployment validation.
- [Service update policy](service-update-policy.md) defines the managed update workflow and the target model for Technitium version/checksum management.

## Workflow reminder

Use the repository workflow from the main [README](../README.md): check managed version pins with `just update`, validate with `just validate`, review infrastructure changes with `just plan`, and apply only after explicit approval with `just apply`.

Service diagnostics and steady-state Ansible configuration should use direct service inventory groups and endpoints, for example `ssh <user>@hermes.example.internal` or the service-local HTTPS URL. Proxmox host access is for lifecycle readiness, storage prep, explicit bootstrap/recovery, and host-boundary work, not routine in-service changes.
