# Development Testing Environment

This document describes the isolated development environment used to test the
full homelab-infra project. It is both an operator runbook and an agent
contract. The actual development endpoint, network, addresses, credentials,
and state belong in the private `values/` repository and must not be copied
into tracked documentation.

## Purpose

The development environment provides disposable integration coverage beyond
static validation. It can provision the enabled services, configure them with
Ansible, exercise direct service access, test recovery paths, and be destroyed
and recreated for a consistent test run.

The development environment is separate from production. It must not reuse
production service state, DNS records, backups, tokens, or application data.

## Development environment tiers

The canonical `dev` site is the shared repository conformance environment. It
is used to test the generic service roles, OpenTofu resources, DNS/Caddy
patterns, state recovery, and LXC/VM behavior.

A site-specific development environment may be created beside a persistent
site when its configuration needs rehearsal:

```text
site-a       # persistent site configuration
site-a-dev   # disposable shadow of site-a
```

A `<site>-dev` environment is appropriate for unusual networking, storage,
DNS, service selection, migration, or rollback changes. It inherits the
site's intended shape but has independent VMIDs, addresses, hostnames,
credentials, state, and lifecycle policy. Do not create one for every site by
default; create it when site-specific integration coverage justifies the
additional resources.

The site name is an identifier, not a policy. Lifecycle and safety behavior
come from site metadata. The shared `dev` site is special because it is the
default repository testing target, not because all development environments
must use the same values.

## Development contract

Private values must define the following site-specific contract:

| Setting | Development value |
| --- | --- |
| Proxmox API endpoint | Reverse-proxied development API endpoint |
| Proxmox node | Dedicated development node |
| Network bridge | Development bridge, normally `vmbr0` |
| VLAN | Dedicated development VLAN |
| IPv4 network | Dedicated RFC1918 development subnet |
| Address allocation | Static addresses from the reserved development range |
| Gateway | Development subnet gateway |
| Bootstrap DNS | Existing resolver(s) reachable from the dev subnet |
| Service DNS | Development Technitium after it is healthy |
| Root disk datastore | Selected development datastore |
| Template datastore | Selected datastore supporting `vztmpl` |
| VMID range | Reserved development VMID range |
| Name prefix | `dev-` for guest names and hostnames |

The public scaffold must use placeholders and RFC 5737 examples. Private
values provide the real values through `values/terraform.tfvars`,
`values/.env`, DNS records, and private inventory settings.

## Source of truth

Infrastructure shape comes from private site values and the OpenTofu
variables. Service selection comes from the selected site's private settings
file and is checked against `infra/services.json`. Dynamic Ansible inventory is
derived from those values by `infra/ansible/inventory/tfvars.py`.

The repository-root `settings.local.json` remains operator metadata for the
private values repository and local tooling. It must not be the source of a
site's service selection. Each site owns its enabled-service list and policy
metadata under `values/sites/<site>/`.

Do not hand-maintain a second inventory containing duplicate VMIDs, addresses,
hostnames, or runtime choices. If a value determines infrastructure shape, it
belongs in private Terraform values and must be passed through the dynamic
inventory.

The public files provide the reusable implementation:

- `infra/services.json` defines service registry membership and dependencies.
- `infra/opentofu/` declares guests, storage, networking, and lifecycle.
- `infra/ansible/roles/` configures services inside guests.
- `infra/ansible/playbooks/` provides orchestration and ordering.
- `scripts/migrate-values.py` maintains private-value compatibility.
- `scaffold/` documents public-safe starter values.

## Migrating a legacy values layout

Existing private values repositories may still have their environment files at
the values root. Preview the move into a site directory before changing files:

```text
python scripts/migrate-site-values.py --site prod
```

The migration tool requires an explicit `--apply` to move files. It creates the
site metadata, moves state/inventory/DNS/secret files together, and removes the
legacy service list from the root operator settings. The apply operation rolls
back completed moves if a later move or settings update fails. Back up the
private values repository first and review its status before applying the
migration. Run the migration for development separately from production.

## Lifecycle

The environment is recreated from scratch for a consistent test run.

1. Prepare or migrate the private dev values repository with `just setup`.
2. Select the required services in the private settings file.
3. Run `just validate`.
4. Run `just plan` and review the dev-only resource changes.
5. Run `just apply` only after explicit approval.
6. Test the guests through their direct SSH, HTTP, HTTPS, and DNS endpoints.
7. Record results without exposing credentials or private inventory.
8. Tear down the dev resources only after explicit approval.
9. Remove or rotate disposable credentials and recreate the environment for the
   next clean run.

Never use the development inventory with production values or production state.
Never run a dev apply while the selected values repository points at a
production remote or backend.

## Bootstrap ordering

Technitium is configured before it is used as the service resolver. During
bootstrap, guests use the configured bootstrap resolver. After Technitium is
healthy, create or synchronize the development DNS records and point subsequent
guest configuration at the dev Technitium address.

For a service-local Caddy deployment, use the development hostname and the
existing DNS-01 pattern. Do not expose service ports directly when the service
contract requires local Caddy. DNS changes must be produced by the existing
Ansible DNS orchestration, not by OpenTofu resources.

## Adding a service to the development environment

Adding a service is a repository change plus a private-values change. The
following sequence is required.

### 1. Register the service

Add or update the service entry in `infra/services.json` with:

- stable service name;
- state capability and restore order;
- OpenTofu resource addresses and replacement addresses;
- service playbooks and dependencies;
- dynamic inventory host and group mapping;
- VMID, address, runtime, domain, user, and extra variable mappings where
  applicable.

Disabled services should still have deterministic empty inventory groups. Do
not select a service merely because its registry entry exists.

### 2. Declare infrastructure shape

Add the required public-safe OpenTofu variables, modules, checks, and outputs.
Private Terraform values must define, as applicable:

- `dev-` hostname;
- VMID in the reserved dev range;
- static address and CIDR;
- development gateway and DNS servers;
- `vmbr0` and the development VLAN tag;
- LXC or VM runtime;
- root disk datastore and size;
- Debian template or VM image pins;
- startup ordering and dependencies.

Validate unique VMIDs and unique static addresses before applying.

### 3. Wire dynamic inventory

Update `infra/ansible/inventory/tfvars.py` registry mappings rather than adding
hard-coded host definitions. Add tests covering:

- enabled service selection;
- disabled service group preservation;
- LXC and VM host variables;
- runtime-specific users and become behavior;
- address, hostname, domain, and VMID propagation.

### 4. Add service orchestration

Add or extend the service playbook and role. Keep resource declaration in
OpenTofu and guest configuration in Ansible. The role should be idempotent and
must include:

- pinned artifacts and checksums where downloads are required;
- explicit secret inputs from private values;
- service-local health checks;
- restart handlers rather than ad hoc restarts;
- rollback or failure-safe behavior;
- direct-access diagnostics;
- LXC and VM assumptions documented or tested.

Do not add `local-exec` service configuration to OpenTofu.

### 5. Add DNS and HTTPS wiring

Add public-safe scaffold placeholders and private dev records as needed. DNS
records are synchronized through the Technitium Ansible workflow. For
browser-facing services, prefer an app plus service-local Caddy in the same
guest unless the service belongs on the shared onramp host.

Test both the local service endpoint and the intended development HTTPS route.
Do not print DNS tokens, private hostnames, or certificate material in test
output.

### 6. Add migration and scaffold support

If the service adds private values, update:

- `scaffold/.env.example`;
- `scaffold/terraform.tfvars` when applicable;
- `scaffold/ansible/inventory/local.yml`;
- `scripts/parse-env.py` allowed keys;
- `scripts/migrate-values.py` generation and migration logic;
- `settings.example.json` if service selection changes.

Generated secrets belong in private values and must be idempotent and silent.

### 7. Add tests

At minimum, add:

- registry and dynamic-inventory tests;
- OpenTofu variable or structural tests;
- Ansible role contract and YAML tests;
- public-safety fixtures;
- service health and configuration assertions;
- first-apply and repeat-apply behavior tests;
- backup, restore, and failure cleanup tests for stateful services;
- disposable guest smoke coverage where the service has systemd, networking,
  storage, or integration behavior that static tests cannot prove.

### 8. Validate and review

Run the public command surface:

```text
just validate
just plan
```

Review the plan for unexpected production references, wrong VLANs, non-dev
names, duplicate addresses, destructive changes, and unintended state or
credential paths. Apply only with explicit approval and only when the private
values repository is confirmed to be the isolated development environment.

## Agent safety rules

Agents working on the development environment must:

- keep tracked files public-safe;
- use private values for real endpoints, names, addresses, credentials, and
  state;
- prefer direct service endpoints for diagnostics;
- avoid production DNS, routers, firewalls, and service guests;
- never reuse production backups or application databases;
- never run `tofu apply`, destroy, restore, or state surgery without explicit
  approval;
- use `just validate`, `just plan`, and approved `just apply` rather than ad hoc
  mutation commands;
- redact command output and test artifacts;
- preserve a disposable reset path after every integration run.
