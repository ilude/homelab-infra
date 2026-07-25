# Documentation Index

Public-safe documentation for this homelab infrastructure runbook.

## Operator and platform docs

- [Hermes operator pilot PRD](hermes-operator-pilot-prd.md) defines the Hermes cockpit requirements, safety boundaries, and SearXNG pilot classification.
- [Managed service-state backup and restore](service-state-backup.md) covers private `values/` backups for Hermes memory/soul state and other managed service state.
- [Hermes state backup and restore](hermes-state-backup.md) keeps the Hermes-specific compatibility notes.
- [Hermes tuning](hermes-tuning.md) documents managed compression and delegation settings.
- [Hermes Control operations](hermes-control-operations.md) documents the private companion-stack lifecycle, verification, token rotation, and rollback boundaries.
- [Onramp app-platform contract](onramp-app-platform-contract.md) defines the `homelab-infra`, `onramp-vNext`, and Hermes ownership split for onramp-host services.
- [Debian baseline split](debian-baseline.md) explains the current LXC/host Debian versions, rationale, and the reviewed migration path.
- [Onramp SearXNG handoff](onramp-searxng-handoff.md) gives `onramp-vNext` the future SearXNG-on-Podman contract and records the current temporary `searxng_onramp` exception.
- [App-host runbook](onramp-host-runbook.md) covers `onramp_host` and `searxng_onramp` enable/disable, rollback, and live deployment validation.
- [Service update policy](service-update-policy.md) defines the managed update workflow, current service boundaries, and Technitium version/checksum management.
- [Development testing environment](development-environment.md) documents disposable integration testing and the agent workflow for adding services.

## Repository review

- [Repository audit (2026-07-19)](repository-audit-2026-07-19.md) reviews the tracked projects, layout, documentation, validation, security boundaries, recovery workflows, and prioritized improvements at commit `524ac1f`.
- [Upstream gap and suitability review (2026-07-22)](upstream-gap-review-2026-07-19.md) groups all 43 upstream-only commits into final capability series, maps corrective follow-ups, and records fork adoption decisions with commit-level evidence in an appendix.
- [Upstream commit review](upstream-commit-review.md) tracks the 2026-07-14 upstream changes and their applicability to this fork.

## Workflow reminder

Use the repository workflow from the main [README](../README.md): check managed version pins with `just update`, validate with `just validate`, review infrastructure changes with `just plan`, and apply only after explicit approval with `just apply`.

Service diagnostics and steady-state Ansible configuration should use direct service inventory groups and endpoints, for example `ssh <user>@hermes.example.internal` or the service-local HTTPS URL. Proxmox host access is for lifecycle readiness, storage prep, explicit bootstrap/recovery, and host-boundary work, not routine in-service changes.
