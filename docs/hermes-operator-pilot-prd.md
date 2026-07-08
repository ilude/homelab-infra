# PRD: Hermes Operator Pilot for Homelab Infrastructure

## Summary

This pilot defines Hermes as an operator cockpit for `homelab-infra` without making Hermes a second source of truth. The selected architecture is option 3: `homelab-infra remains the durable infrastructure substrate`, `onramp-vNext owns Docker app services`, and `Hermes operates across both` through their approved native workflows.

For the first plugin-backend pilot, SearXNG should be treated as an Onramp app-platform service by default. The recommended onramp-host direction is a Debian 13 VM running Podman. Podman-in-LXC is experimental and should not be the default substrate for durable onramp hosting.

No live mutation is in scope for this PRD. Provisioning a Debian 13 VM, Deploying SearXNG, and Wiring the Hermes web-searxng plugin are deferred until separate reviewed implementation plans exist.

## Problem

The homelab infrastructure workflow is repo-driven and intentionally cautious: source changes are reviewed in the public runbook repo, private site values live in the ignored `values/` repo, infrastructure changes are reviewed with `just plan`, and live mutation happens only through `just apply` after approval.

Hermes is now available as a managed LXC with a browser-facing dashboard. The next product question is how to use Hermes as an operator cockpit for this repository without bypassing the audited runbook workflow, leaking private values, or turning the infra repo into a general application catalog.

## Goals

- Provide a safe operator surface for the standard homelab workflow: inspect status, validate, plan, apply after approval, and summarize outcomes.
- Keep `homelab-infra` as the source of truth for durable infrastructure and first-class services.
- Keep `onramp-vNext` as the owner for general Docker app services and app catalog behavior.
- Keep private site data in `values/` and prevent secrets, real domains, real IPs, and state from entering tracked public files or operator summaries.
- Let Hermes use repo-native commands instead of ad hoc live mutation.
- Establish a clear boundary between durable infrastructure services and general Docker application services.
- Support future plugin backends, such as search services, without forcing every backend into a first-class LXC unless justified.

## Non-goals and deferrals

- Do not replace OpenTofu, Ansible, or the reviewed `just` workflow.
- Do not make Hermes mutate production infrastructure without explicit operator approval.
- Do not make Technitium or the DNS LXC a general ingress proxy.
- Do not store or display secrets in Hermes transcripts, logs, docs, or tracked files.
- Do not turn this repo into an arbitrary app catalog by default.
- Do not require Onramp to be complete before Hermes can provide useful repo operations.
- No live mutation is in scope for this MVP.
- Provisioning a Debian 13 VM is deferred.
- Deploying SearXNG is deferred.
- Wiring the Hermes web-searxng plugin is deferred.

## Users and scenarios

### Primary user: homelab operator

The operator wants to manage Proxmox LXCs, DNS, HTTPS, Git hosting, secrets, and supporting services through a repeatable workflow with clear review points.

### Secondary user: repo automation

Repo automation may run validation, planning, deployment, and status checks, but must preserve the same approval and safety boundaries as the local workflow.

### Scenario: review a proposed infrastructure change

1. Operator asks Hermes for current status.
2. Hermes checks repository status, enabled services, private values wiring, and recent validation state.
3. Hermes runs or recommends `just validate`.
4. Hermes runs `just plan` only when requested.
5. Hermes summarizes creates, updates, replacements, deletes, and destructive changes without exposing private values.

### Scenario: apply a reviewed plan

1. Operator explicitly approves applying the current plan.
2. Hermes runs the repo-native apply workflow.
3. Apply verifies saved plan metadata before mutation.
4. Hermes summarizes result and points the operator to private `values/` repo state that may need commit and push.

### Scenario: add a Hermes plugin backend

1. Operator requests a backend such as search.
2. Hermes classifies whether it is a Hermes-local dependency, durable infrastructure service, or app-platform service.
3. Durable infrastructure follows this repo's OpenTofu plus Ansible plus service-local Caddy pattern.
4. App-platform services live in Onramp or an app-services host, with Hermes consuming the approved URL.

## Requirements

### Workflow requirements

- Hermes must use public repo commands for normal operations: `just validate`, `just plan`, and `just apply`.
- Hermes must show plan summaries before any live mutation.
- Hermes must require explicit approval before `just apply`, destroy, state surgery, or router/firewall mutation.
- Hermes must detect stale or missing plan artifacts and require a fresh `just plan` rather than reusing or editing saved plans.
- Hermes must summarize private `values/` repo follow-up without printing secrets or real site inventory.

### Safety requirements

- Tracked files must remain public-safe and use placeholders such as `example.internal` and RFC 5737 addresses.
- Real endpoints, LAN IPs, domains, DNS records, hostnames, credentials, generated secrets, OpenTofu state, and plans must remain in `values/` or local ignored files.
- Generated secrets must be written idempotently and never printed in command output or summaries.
- Hermes dashboard access must remain authenticated and proxied through service-local Caddy.
- Browser-facing infrastructure services should bind application processes to loopback behind service-local Caddy unless a service has a specific reason to expose a port.

### Infrastructure ownership requirements

- OpenTofu owns Proxmox LXC shape, VMIDs, networking, storage attachments, and service enablement resources.
- Ansible owns in-LXC service installation and configuration.
- Technitium DNS record sync remains in Ansible, after Technitium is installed and reachable.
- `values/terraform.tfvars` remains the source of truth for infrastructure-derived service shape.
- Inventory should derive service hosts, VMIDs, and addresses from tfvars instead of duplicating them manually.

### App-platform boundary requirements

- First-class infrastructure services may live in `homelab-infra` when they need Proxmox resources, static DNS, secrets integration, and lifecycle management as durable platform services.
- General Docker application services should be evaluated for Onramp or an app-services host before being added as first-class LXCs.
- Plugin backend services for Hermes should be classified before implementation:
  - Hermes-local dependency: colocated with Hermes only when it is not useful outside Hermes.
  - Durable platform service: own LXC, OpenTofu, Ansible, Caddy, DNS.
  - App-platform service: deployed by `onramp-vNext` or an app-services host, with Hermes consuming its URL.
- The service `port` convention remains container/service port reachable on the Compose network, not a host-published port unless explicitly documented.

## SearXNG pilot decision

SearXNG is the first expected search backend pilot for Hermes. The default classification is app-platform service, because search is a general application capability rather than a durable infrastructure primitive. `onramp-vNext owns Docker app services` remains the target boundary.

Current exception: `homelab-infra` temporarily owns `searxng_onramp` on `onramp_host`. The service is rootless Podman behind host-local Caddy, has Technitium DNS input, and passes `HERMES_WEB_SEARXNG_URL` to Hermes. This keeps the pilot moving without making SearXNG a first-class LXC or a permanent Hermes-local dependency.

`homelab-infra remains the durable infrastructure substrate` for the onramp host itself, DNS contract, and this temporary SearXNG exception. `Hermes operates across both` by reading or invoking the approved workflow in each repository rather than inventing a third deployment path.

The default runtime target is a Debian 13 VM running Podman. Podman-in-LXC is experimental because nested containers in Proxmox LXCs require additional kernel, namespace, mount, and fuse trade-offs. Arch or CachyOS VMs are not the default because a rolling-release host is a poor fit for durable homelab app infrastructure unless a specific runtime feature requires it.

## Observability and audit requirements

- Hermes should capture command, repo, status, and sanitized summaries for operator actions.
- Live mutation summaries must include what changed, validation run, known gaps, and next steps.
- Failed workflows must report root cause and next safe command without dumping sensitive logs.
- Future workflow telemetry should make plan, review, and execution quality auditable without reconstructing full transcripts.

## Acceptance criteria

- A user can open the Hermes dashboard and request a sanitized repo status summary for `homelab-infra`.
- A user can ask Hermes to run validation through the standard command surface and receive a pass/fail summary with safe next steps.
- A user can ask Hermes to run `just plan` and receive a summarized plan showing creates, updates, replacements, deletes, and destructive changes.
- Hermes refuses or pauses for approval before any live mutation command.
- Hermes does not print secrets, tokens, real domains, real IPs, private DNS records, or private inventory in summaries.
- Adding a plugin backend includes an explicit classification decision: Hermes-local, durable platform service, or app-platform service.
- For the search backend pilot, the PRD records that SearXNG belongs in Onramp or an app-services host by default, with the current `searxng_onramp` implementation treated as a temporary `homelab-infra` exception rather than a first-class LXC.

## Dependencies

- Hermes management LXC and dashboard deployment.
- Private `values/` repo with current tfvars, inventory, DNS records, environment values, and OpenTofu state.
- Working local tooling container for `just validate`, `just plan`, and `just apply`.
- Forgejo and private values repo workflow if remote deployment or monitoring is in scope.
- `onramp-vNext` direction if plugin backends are treated as app-platform services, plus a handoff path for retiring the temporary `searxng_onramp` exception.

## Risks

- Hermes could become a second control plane if it bypasses repo workflows.
- Plugin backend services could create service sprawl if each small dependency becomes a first-class LXC.
- App-platform and infra-runbook boundaries could become unclear between Onramp and `homelab-infra`.
- Private values could leak through summaries, logs, dashboard output, or copied command output.
- Disabled services that still exist in state could confuse operators unless the UI distinguishes configured, enabled, deployed, reachable, and maintained states.

## Open questions

- Which Hermes actions are in scope for the first pilot: status only, validate, plan, apply, private values commits, or Forgejo workflow monitoring?
- Should Hermes trigger `just apply` locally, trigger Forgejo Actions, or support both with different approval paths?
- What is the minimum audit trail required for an operator-approved apply?
- Which onramp-host provisioning shape should a future infrastructure plan expose to `onramp-vNext`?
- How should Hermes safely support edits to `values/` without exposing private values in transcripts or summaries?
- What recovery path should be documented when Hermes is unavailable but infrastructure needs maintenance?
