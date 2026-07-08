---
created: 2026-07-07
status: completed
completed: 2026-07-08
---

# Plan: Manage SearXNG on onramp_host

## Objective

Move the SearXNG pilot from a deferred Onramp handoff into this repository for now: provision SearXNG as a rootless Podman workload on the existing `onramp_host`, publish it through the onramp host reverse-proxy boundary, add DNS automation, and wire Hermes to the resulting SearXNG URL without exposing private values.

## Context

The current docs classify SearXNG as an `onramp-vNext` app-platform service and explicitly say this repo only prepares the `onramp_host` VM. The operator now wants `homelab-infra` to take over SearXNG setup temporarily. That changes the ownership boundary and must update implementation, docs, scaffold, migration, and validation together.

Relevant current repo facts:

- `onramp_host` is an optional Debian 13 VM with rootless Podman readiness in `infra/ansible/roles/onramp_host`.
- `onramp_host` already allows approved reverse-proxy ports 80/443 in the host firewall defaults.
- DNS records are synchronized from `values/dns-records.local.json` by `infra/ansible/playbooks/technitium-dns.yml`.
- Hermes already has `HERMES_WEB_SEARXNG_URL` in `scaffold/.env.example` and migration allowlists, but the repo does not deploy SearXNG or populate the endpoint automatically.
- `settings.py` has service dependency support, so a new service can depend on `onramp_host` and optionally coordinate with `technitium`/`hermes` behavior.

## Complexity classification

Complex. This touches Ansible roles/playbooks, settings/service orchestration, private values migration/scaffold, DNS data, Hermes runtime env, docs, tests, and optional live deployment. It also changes a previously documented ownership boundary.

## Approaches considered

| Approach | Summary | Pros | Cons | Verdict |
|---|---|---|---|---|
| A. Fold SearXNG into `onramp_host` | Always deploy SearXNG whenever `onramp_host` is enabled | Least service-selection work | Makes onramp substrate and app workload inseparable; harder to disable/remove SearXNG; surprises users who only want Podman host | Rejected |
| B. Add `searxng_onramp` service in this repo | New settings service depends on `onramp_host`; role deploys rootless Podman SearXNG and host Caddy; migration/scaffold wire DNS/Hermes | Explicit ownership, reversible, testable, can be temporary, matches repo service-selection model | More files and validation | Selected |
| C. Keep Onramp handoff only | Update docs, no deployment | Preserves old boundary | Does not satisfy request | Rejected |

## Selected design

Add a new optional service named `searxng_onramp`.

- `settings.py`: add service with playbook `infra/ansible/playbooks/searxng-onramp.yml` and dependency on `onramp_host`.
- Ansible target: direct `onramp_host` inventory group, using `become: true` only for host-level packages/Caddy and `become_user: {{ onramp_host_deploy_user }}` for rootless Podman files/actions.
- Runtime layout under `{{ onramp_host_deploy_dir }}/searxng`.
- Container runtime: rootless Podman via `podman-compose` or Quadlet, with no default public host-published app port except loopback for the reverse proxy.
- Reverse proxy: install/configure Caddy on the onramp host, proxying `https://{{ searxng_server_name }}` to the SearXNG container on loopback. Use existing `caddy_email`/`caddy_cloudflare_api_token` pattern for DNS-01 if HTTPS is enabled.
- DNS: add `searxng_server_name` mapped to the onramp host IP in scaffold and domain bootstrap/migration helpers so Technitium DNS sync owns the record while this repo owns the temporary service.
- Hermes: set/render `HERMES_WEB_SEARXNG_URL` from `searxng_public_url` when `searxng_onramp` and `hermes` are enabled. Do not print the private URL in logs beyond sanitized summaries.
- Secrets: add `SEARXNG_SECRET_KEY` to scaffold and generated secret migration. Keep it only in `values/.env`; do not commit real values.

## Explicit deferrals

- No `just apply` or live SearXNG deployment without explicit approval.
- No router/firewall changes beyond the already-managed onramp-host UFW rules.
- No Infisical integration for SearXNG secrets in this slice.
- No Onramp repo changes; docs should state this is a temporary repo-owned SearXNG deployment.
- No Hermes plugin implementation beyond passing the SearXNG endpoint through existing `HERMES_WEB_SEARXNG_URL` runtime config.

## Task breakdown

| Task | Files | Type | Depends on |
|---|---|---|---|
| T1: Add service registry and value model | `scripts/settings.py`, `settings.example.json`, `infra/ansible/inventory/tfvars.py`, scaffold files | feature | -- |
| T2: Add SearXNG onramp Ansible role/playbook | `infra/ansible/playbooks/searxng-onramp.yml`, `infra/ansible/roles/searxng_onramp/**` | feature | T1 |
| T3: Wire DNS and Hermes endpoint generation | `scaffold/dns-records.local.json`, `scripts/bootstrap-domain.py`, `scripts/migrate-values.py`, Hermes templates/tasks as needed | feature | T1 |
| T4: Update docs and ownership contract | `README.md`, `docs/onramp-*.md`, `docs/hermes-operator-pilot-prd.md`, `AGENTS.md` if needed | docs | T1-T3 |
| T5: Add tests and validation checks | `tests/test_settings.py`, `tests/test_service_registry_parity.py`, `tests/test_ansible_safety.py`, new focused tests as needed | tests | T1-T4 |
| V1: Source validation | helper/unit/syntax/public-safety checks | validation | T1-T5 |
| F1: Repo-wide validation | `just validate` | final validation | V1 |
| F2: Plan/deployment gate | `just plan` summary; `just apply` only after approval | manual/live gate | F1 |

## Execution waves

### Wave 1: Service model and public values

- Add `searxng_onramp` to `scripts/settings.py` with dependency on `onramp_host`.
- Add public-safe defaults/placeholders:
  - `SEARXNG_SECRET_KEY` in `scaffold/.env.example`.
  - `searxng_server_name`, `searxng_public_url`, container image/version/port variables in scaffold inventory or role defaults.
  - DNS placeholder record `searxng.apps.example.net` pointing at the placeholder onramp-host IP.
- Update migrations to generate `SEARXNG_SECRET_KEY` idempotently and preserve `HERMES_WEB_SEARXNG_URL`.

Acceptance criteria:

- `scripts/python.sh scripts/settings.py --settings settings.example.json validate` exits 0.
- `scripts/python.sh scripts/settings.py --settings settings.example.json ansible-playbooks --all` includes `searxng-onramp.yml`.
- `scripts/python.sh -m unittest tests.test_settings tests.test_service_registry_parity` exits 0.
- Public safety passes.

### Wave 2: SearXNG role/playbook

- Add `infra/ansible/playbooks/searxng-onramp.yml` targeting `onramp_host` directly.
- Add `infra/ansible/roles/searxng_onramp` with:
  - required var assertions;
  - rootless deployment directory management;
  - SearXNG config template with secret values under `no_log`;
  - Podman compose or Quadlet deployment as `onramp_host_deploy_user`;
  - Caddy install/build/config for `searxng_server_name`;
  - handlers for SearXNG and Caddy restarts;
  - health checks against loopback and public URL when safe.
- Ensure no SearXNG app port is exposed on all interfaces except reverse-proxy ports.

Acceptance criteria:

- `ansible-playbook --syntax-check` passes for `searxng-onramp.yml` using scaffold inventory/settings.
- `ansible-lint infra/ansible` passes.
- YAML-aware tests confirm no forbidden `pct`, no secret logging, explicit owner/group/mode, and no broad host-published app port.

### Wave 3: DNS and Hermes automation

- Update `scripts/bootstrap-domain.py` so domain setup can derive `searxng.apps.<domain>` or a documented equivalent and write DNS/Hermes private values.
- Update DNS scaffold and migration so existing private values gain the SearXNG DNS record only when `searxng_onramp`/`onramp_host` values are present and placeholders can be derived safely.
- Update Hermes env rendering to include `HERMES_WEB_SEARXNG_URL` when set.

Acceptance criteria:

- Public scaffold DNS validates with `python infra/ansible/scripts/apply-technitium-dns.py --check scaffold/dns-records.local.json`.
- Tests cover domain bootstrap/migration behavior using temp public-safe values.
- Hermes dashboard env template renders the SearXNG URL without printing secrets.

### Wave 4: Docs and regression coverage

- Update docs to state that SearXNG is temporarily managed by `homelab-infra` on `onramp_host`.
- Replace old “Onramp owns SearXNG” absolutes with historical/default-boundary language plus current exception.
- Add rollback notes: disable `searxng_onramp`, remove DNS/Hermes values, rerun plan/apply after approval.

Acceptance criteria:

- `rg -n "searxng_onramp|HERMES_WEB_SEARXNG_URL|searxng.apps.example" README.md docs scaffold scripts infra tests` shows consistent public-safe references.
- `scripts/public-safety-check.sh` passes.

## Validation contract

Required before archive:

```bash
scripts/python.sh -m unittest discover -s tests -p 'test_*.py'
scripts/public-safety-check.sh
scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=scaffold/terraform.tfvars INFRA_SETTINGS_FILE=settings.example.json; ansible-inventory -i scaffold/ansible/inventory/local.yml -i infra/ansible/inventory/tfvars.py --list >/dev/null; ansible-playbook -i scaffold/ansible/inventory/local.yml -i infra/ansible/inventory/tfvars.py --syntax-check infra/ansible/playbooks/site.yml infra/ansible/playbooks/storage-prep.yml $(python scripts/settings.py --settings settings.example.json ansible-playbooks --all); ansible-lint infra/ansible'
just validate
git diff --check
```

Optional live validation only after explicit approval:

```bash
just plan
# review creates/updates/replaces/deletes
just apply
```

Post-apply checks, if approved:

- SearXNG service active on `onramp_host`.
- `https://searxng.apps.example.net` or private equivalent resolves through Technitium and returns HTTP 200/302.
- Hermes environment contains `HERMES_WEB_SEARXNG_URL` and the dashboard/runtime can use the endpoint if the Hermes plugin exists.

## Manual/deployment gates

- Source implementation and validation: agent-runnable.
- `just plan`: safe/read-only and agent-runnable when requested.
- `just apply`: requires explicit user approval because it can deploy/modify live services, DNS, and Hermes config.
- Any changed host-key replacement, router/firewall mutation outside managed UFW, or destructive resource change requires explicit approval.

## Execution checklist

- [x] T1: Service registry and value model implemented
  - Status: completed
  - Evidence: 2026-07-08; updated settings service registry, OpenTofu service allowlist, tfvars inventory, scaffold env/tfvars/inventory/DNS; focused settings command passed.
- [x] T2: SearXNG role/playbook implemented
  - Status: completed
  - Evidence: 2026-07-08; added infra/ansible/playbooks/searxng-onramp.yml and infra/ansible/roles/searxng_onramp with rootless Podman, loopback compose binding, Caddy templates, no_log secret templates.
- [x] T3: DNS and Hermes automation implemented
  - Status: completed
  - Evidence: 2026-07-08; updated bootstrap-domain, migrate-values, scaffold DNS, and Hermes dashboard env rendering for HERMES_WEB_SEARXNG_URL.
- [x] T4: Docs and ownership contract updated
  - Status: completed
  - Evidence: 2026-07-08; updated README and docs/onramp-* plus Hermes PRD for temporary searxng_onramp ownership and rollback.
- [x] T5: Regression tests added
  - Status: completed
  - Evidence: 2026-07-08; added focused unittest coverage for settings dependency, inventory vars, migration/bootstrap DNS, and Ansible safety; focused unittest set passed.
- [x] V1: Source validation passed
  - Status: completed
  - Evidence: 2026-07-08; `scripts/python.sh -m unittest discover -s tests -p 'test_*.py'`, `scripts/public-safety-check.sh`, DNS scaffold check, ansible syntax/lint contract, and `git diff --check` passed.
- [x] F1: Repo-wide `just validate` passed
  - Status: completed
  - Evidence: 2026-07-08; `just validate` passed after repair loop added SEARXNG_SECRET_KEY to scripts/parse-env.py allowlist.
- [x] F2: Deployment gate skipped or completed with approval
  - Status: completed
  - Evidence: 2026-07-08; live `just plan`/`just apply` classified optional/not required for source archive; no explicit approval requested or used, no live mutation run.
- [x] F3: Archive preflight complete
  - Status: completed
  - Evidence: 2026-07-08; implementation, required validation, repo-wide validation, deployment-not-required decision, checklist, and archive target `.specs/archive/searxng-onramp/plan.md` verified.

## Success criteria

- `searxng_onramp` is an explicit optional service with an `onramp_host` dependency.
- SearXNG deploys on `onramp_host` using rootless Podman and does not expose a broad app port outside the reverse-proxy boundary.
- Technitium DNS sync can manage the SearXNG public name through public-safe scaffold/private values.
- Hermes gets `HERMES_WEB_SEARXNG_URL` automatically from private values/config when SearXNG is enabled.
- Docs accurately describe the temporary ownership exception and rollback path.
- `just validate` passes.

## Workflow Eval Record

- outcome: completed-and-archived
- archive_status: archived
- archive_path: .specs/archive/searxng-onramp/plan.md
- validation_commands:
  - `scripts/python.sh -m unittest discover -s tests -p 'test_*.py'` passed
  - `scripts/public-safety-check.sh` passed
  - `scripts/run-infra.sh python infra/ansible/scripts/apply-technitium-dns.py --check scaffold/dns-records.local.json` passed
  - `scripts/run-infra.sh bash -euo pipefail -c 'source /opt/ansible/bin/activate; export ANSIBLE_TFVARS_FILE=scaffold/terraform.tfvars INFRA_SETTINGS_FILE=settings.example.json; ansible-inventory -i scaffold/ansible/inventory/local.yml -i infra/ansible/inventory/tfvars.py --list >/dev/null; ansible-playbook -i scaffold/ansible/inventory/local.yml -i infra/ansible/inventory/tfvars.py --syntax-check infra/ansible/playbooks/site.yml infra/ansible/playbooks/storage-prep.yml $(python scripts/settings.py --settings settings.example.json ansible-playbooks --all); ansible-lint infra/ansible'` passed
  - `just validate` passed
  - `git diff --check` passed with CRLF normalization warnings only
- manual_deployment_gate: not required; optional live `just plan`/`just apply` skipped because no explicit approval and source validation satisfied archive criteria
- checklist_completion_state: all items checked
- friction:
  - category: validation-repair; severity: low; evidence: public-safety initially flagged test fixtures and parse-env rejected SEARXNG_SECRET_KEY; impact: required allowlist/test-fixture comments; recommended_change: add new env keys to parse-env with scaffold changes; candidate_test: scaffold parse-env validation
  - category: ansible-lint-repair; severity: low; evidence: role defaults/register vars needed role prefix; impact: renamed role-internal variables; recommended_change: prefix new role internals from first implementation pass; candidate_test: ansible-lint
- missing_evidence: none
- improvement_candidates: consider a tiny helper for adding optional service env keys consistently across scaffold, parse-env, and migrations
- eval_confidence: high
- post_run_reviewers: deterministic-only; attempted evidence-auditor/workflow-friction-analyst subagents were unavailable in this environment and produced no artifact
- execution_outcome: completed
- panel_quality_label: unknown; reason: no separate review panel evidence in this run; confidence: medium

## Handoff notes

- Keep tracked examples generic: `searxng.apps.example.net`, `192.0.2.72`, and `example.internal` only.
- Do not commit real SearXNG hostnames, IPs, secrets, or live DNS inventory.
- Prefer direct SSH/Ansible to `onramp_host`; do not use Proxmox for in-VM app configuration.
- Do not run `just apply` without explicit approval.
