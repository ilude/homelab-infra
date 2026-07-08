# Documentation Index

Public-safe documentation for this homelab infrastructure runbook.

## Operator and platform docs

- [Hermes operator pilot PRD](hermes-operator-pilot-prd.md) defines the Hermes cockpit requirements, safety boundaries, and SearXNG pilot classification.
- [Onramp app-platform contract](onramp-app-platform-contract.md) defines the `homelab-infra`, `onramp-vNext`, and Hermes ownership split for onramp-host services.
- [Onramp SearXNG handoff](onramp-searxng-handoff.md) gives `onramp-vNext` the future SearXNG-on-Podman contract and records the current temporary `searxng_onramp` exception.
- [App-host runbook](onramp-host-runbook.md) covers `onramp_host` and `searxng_onramp` enable/disable, rollback, and live deployment validation.

## Workflow reminder

Use the repository workflow from the main [README](../README.md): validate with `just validate`, review infrastructure changes with `just plan`, and apply only after explicit approval with `just apply`.

Service diagnostics and steady-state Ansible configuration should use direct service inventory groups and endpoints, for example `ssh <user>@hermes.example.internal` or the service-local HTTPS URL. Proxmox host access is for lifecycle readiness, storage prep, explicit bootstrap/recovery, and host-boundary work, not routine in-service changes.
