---
status: reviewed
scope: current-tracked-source-package-and-future-live-rollout
---

# Plan: Herdr remote Debian 13 LXC

## Review decision

**Status: reviewed.** The current tracked-source package is complete. It includes the OpenTofu resource, service registry and fixture, Herdr Ansible playbook and roles, onramp relay changes, focused tests, public documentation, scaffold examples, and this plan. This is not a docs-only change and does not defer implementation work to another coding task.

The future live rollout has no planned deletes. It must stop rather than silently remove or broaden an existing service, key, trust file, or transport boundary.

## Outcome and fixed contract

Provide one optional Debian 13, x86_64, unprivileged Herdr LXC with disabled nesting, persistent non-root operator state, hardened direct SSH, the pinned Herdr binary, Pi `0.84.1`, and the bundled Herdr Pi integration. Herdr reaches the existing rootless Podman workload on `onramp_host` through Docker SSH stdio. No TCP Docker API, Docker daemon, privileged LXC, or LXC nesting is allowed.

The operator logs directly into Herdr as the non-root operator. Pi and `herdr integration install pi` run inside the Herdr LXC as that operator. The Docker context and SSH alias are both exactly `herdr-onramp`, and the endpoint is `ssh://herdr-onramp`.

The generated transport ed25519 private key is created and retained only in the Herdr operator home. Only its public half is passed to onramp for a separate forced-command key entry. BWS supplies the operator login public keys; it does not supply or store the generated transport private key. Herdr stores its persistent `known_hosts.herdr-onramp` and SSH config in its own operator home.

## Authoritative pins and boundaries

- Herdr URL: `https://github.com/herdrdev/herdr/releases/download/v0.8.2/herdr-linux-x86_64`
- Herdr SHA256: `976150a14d490c94b243ea2e1a7eb2dfb67f12e36b182db90936f6728e6aecf4`
- Pi version: `0.84.1`
- Pi package manager: pnpm only
- Docker context: `herdr-onramp`
- SSH alias: `herdr-onramp`
- Docker endpoint: `ssh://herdr-onramp`
- Remote command: exact `docker system dial-stdio`
- Relay target: rootless `/run/user/<uid>/podman/podman.sock`
- Public examples: `herdr.example.internal` and `192.0.2.0/24`

The operator login boundary is direct SSH to the Herdr service endpoint as the non-root operator. Proxmox host SSH and `pct exec` are limited to LXC lifecycle readiness, bootstrap, recovery, and host-boundary work. The transport key is not an operator shell credential. The onramp deploy account is a separate host-management boundary.

## Explicit exclusions

- TCP Docker or Podman APIs.
- A Herdr-managed Docker daemon.
- A Bitwarden access key or OAuth material on Herdr or any managed host.
- A privileged or nested LXC.
- Workstation-side Pi or Herdr integration installation.
- Copying the generated transport private key to BWS, the controller, the workstation, or onramp.
- Changes to `searxng_onramp`.
- A second site-configuration source under `scaffold/` or `values/`.
- Changes to the sibling Onclave repository.
- Router or firewall changes outside the reviewed Herdr and onramp host SSH rules.

## Current tracked-source change inventory

This is the exact source package reviewed by this plan. Creates and updates are listed by path; no implementation, test, BWS, or live-state path is omitted from the inventory.

### Creates

#### OpenTofu

- `infra/opentofu/herdr.tf` - optional Herdr LXC resource using the shared Debian 13 template, unprivileged mode, and disabled nesting.
- `infra/opentofu/herdr-checks.tf` - Herdr SSH hardening and source-CIDR checks.

#### Herdr Ansible playbook and roles

- `infra/ansible/playbooks/herdr.yml`
- `infra/ansible/roles/herdr/README.md`
- `infra/ansible/roles/herdr/defaults/main.yml`
- `infra/ansible/roles/herdr/meta/argument_specs.yml`
- `infra/ansible/roles/herdr/tasks/main.yml`
- `infra/ansible/roles/herdr_controller_trust/README.md`
- `infra/ansible/roles/herdr_controller_trust/defaults/main.yml`
- `infra/ansible/roles/herdr_controller_trust/meta/argument_specs.yml`
- `infra/ansible/roles/herdr_controller_trust/tasks/main.yml`
- `infra/ansible/roles/herdr_lxc_bootstrap/README.md`
- `infra/ansible/roles/herdr_lxc_bootstrap/defaults/main.yml`
- `infra/ansible/roles/herdr_lxc_bootstrap/meta/argument_specs.yml`
- `infra/ansible/roles/herdr_lxc_bootstrap/tasks/main.yml`
- `infra/ansible/roles/herdr_onramp_access/README.md`
- `infra/ansible/roles/herdr_onramp_access/defaults/main.yml`
- `infra/ansible/roles/herdr_onramp_access/meta/argument_specs.yml`
- `infra/ansible/roles/herdr_onramp_access/tasks/main.yml`
- `infra/ansible/roles/herdr_remote_context/README.md`
- `infra/ansible/roles/herdr_remote_context/defaults/main.yml`
- `infra/ansible/roles/herdr_remote_context/meta/argument_specs.yml`
- `infra/ansible/roles/herdr_remote_context/tasks/main.yml`
- `infra/ansible/roles/herdr_remote_context/templates/known_hosts.j2`
- `infra/ansible/roles/herdr_remote_context/templates/ssh_config.j2`

#### Focused tests

- `tests/test_herdr_inventory.py`
- `tests/test_herdr_opentofu.py`
- `tests/test_herdr_runtime.py`
- `tests/test_herdr_onramp_contract.py`

#### Public documentation

- `docs/herdr-remote-lxc.md`

### Updates

#### OpenTofu, registry, and fixture

- `infra/opentofu/onramp-host-checks.tf` - include Herdr VMID and static address uniqueness checks.
- `infra/opentofu/outputs.tf` - expose Herdr VMID, LAN IP, and operator SSH target.
- `infra/opentofu/services.tf` - enable Herdr from the service selection and include it in Debian LXC template selection.
- `infra/opentofu/variables.tf` - add Herdr resource, network, operator, and SSH policy inputs.
- `infra/services.json` - register Herdr, its `onramp_host` dependency, direct-LXC execution resource, inventory mapping, and playbook.
- `tests/fixtures/site-config/terraform.tfvars` - add public-safe Herdr fixture values.

#### Onramp relay

- `infra/ansible/roles/onramp_host/defaults/main.yml` - define the root-owned Podman Docker stdio relay path and socket feature.
- `infra/ansible/roles/onramp_host/meta/argument_specs.yml` - validate the relay path input.
- `infra/ansible/roles/onramp_host/tasks/main.yml` - install `socat`, install the root-owned relay, enable the rootless Podman socket, and verify a Unix socket without a Docker daemon or TCP listener.
- `infra/ansible/roles/onramp_host/templates/podman-docker-stdio.j2` - accept only `docker system dial-stdio` and connect to the rootless Podman socket.

#### Repository documentation and examples

- `README.md` - add Herdr to the service responsibilities and link the Herdr contract.
- `scaffold/README.md` - keep the example public-safe and identify BWS as authoritative, with the Herdr-local `herdr-onramp` context and key boundary.
- `.specs/herdr-remote-lxc/plan.md` - this reviewed complete-package plan.

### Deletes

- None.

There is no stale prerequisite claim: `infra/ansible/playbooks/herdr.yml`, the Herdr roles, the runtime tests, and the onramp contract test are present in the current package. No future coding task is required by this plan.

## Future live change inventory

The following is the exact expected first rollout against live state. Existing matching objects are verified and left unchanged; existing mismatches are updated only within this boundary.

### Creates

- BWS service selection for `herdr` and its required `onramp_host` dependency, if absent.
- One Herdr Debian 13, x86_64, unprivileged, no-nesting LXC from the OpenTofu resource.
- The non-root Herdr operator, persistent home, BWS-provided operator login public keys, locked password, and sudo bootstrap boundary.
- The pinned Herdr release after URL and SHA256 verification.
- Pi `0.84.1` through pnpm and the bundled Pi integration, both inside Herdr as the operator.
- The generated Herdr transport ed25519 key pair in the Herdr operator home. The private file remains only there.
- Herdr's persistent SSH config, `known_hosts.herdr-onramp`, and `herdr-onramp` Docker context in the Herdr operator home.
- Onramp relay prerequisites when absent: `socat`, the root-owned fixed-command relay, rootless Podman socket activation, and Unix-socket verification.
- A separate onramp authorized-key file and SSHD scope for the generated public key, with the exact forced relay command.
- The Herdr hostname/DNS record in the authoritative BWS family if absent and required by the service configuration.

### Updates

- BWS Herdr inventory/configuration values: hostname, operator, operator login public keys, disabled password/root SSH policy, allowed source CIDRs, and service dependency selection.
- The Herdr LXC SSH policy and firewall to keep password SSH and root SSH disabled and allow only the reviewed source CIDRs.
- The onramp deploy user's separate Herdr key file or SSHD drop-in only when the exact restricted entry is absent or mismatched. The generic deploy authorized_keys file is not rewritten by the Herdr access role.
- Herdr's persistent SSH config and known_hosts file only when their exact alias, endpoint, identity, strict trust, or verified host-key contents are mismatched.
- The Herdr-local Docker context only when its endpoint is not exactly `ssh://herdr-onramp`.
- The BWS DNS record only when the existing Herdr record does not match the approved service value.

### Deletes

- None.

An existing TCP API, Docker daemon, broad shell key, privileged/nested LXC, changed host key, or unrelated `searxng_onramp` change is a stop condition. It requires a separate reviewed remediation plan and is not deleted or rewritten here.

## Future live preflight and execution order

### Preflight

1. Confirm the BWS snapshot and service selection without printing values or secrets.
2. Confirm a current backup or recovery copy for every existing onramp relay, SSH key file, SSHD drop-in, Herdr home, or Herdr key set that will be changed. First-time Herdr provisioning has no replacement backup requirement.
3. Verify the tracked source paths above and the exact contract values, especially `herdr-onramp`, the fixed command, no nesting, and the public-only handoff.
4. Download the pinned Herdr binary to an ephemeral file, verify the pinned SHA256, and activate it only after verification.
5. Verify that the direct Herdr endpoint and the onramp endpoint resolve through the approved inventory and that authoritative host keys are available. Do not use `ssh-keyscan` or ambient known_hosts files.
6. Run the reviewed OpenTofu plan and inspect every create, update, and delete. The expected resource change is one Herdr LXC create and no deletes. Do not run an unrelated global rollout.

### Execution

1. Apply the approved Herdr/onramp dependency canary through the public workflow.
2. Run `infra/ansible/playbooks/herdr.yml`. Its PVE play is limited to lifecycle bootstrap; steady-state Herdr configuration uses direct Herdr SSH.
3. Install Pi and `herdr integration install pi` inside Herdr as the operator.
4. Generate the transport key in Herdr, publish only its public fact to onramp, install the restricted onramp entry, then write Herdr's persistent known_hosts, SSH config, and Docker context.
5. Keep the operator's normal access path as direct SSH to Herdr. Do not move Pi or the generated private key to the workstation.

## Future post-deploy checks

- Direct SSH to Herdr succeeds as the non-root operator with strict host-key checking.
- The Herdr binary reports `0.8.2` and matches the pinned SHA256.
- The Herdr home, transport private key, known_hosts, and SSH config have the expected owner/modes and survive restart.
- Pi reports `0.84.1`, pnpm is used, the bundled integration is installed, and the exact extension path exists inside Herdr.
- `docker --context herdr-onramp version` reaches rootless Podman from Herdr.
- The onramp key rejects an interactive shell and every command other than `docker system dial-stdio`.
- The relay is root-owned and fixed, the Podman socket is Unix-only, and no Docker daemon or TCP API is present.
- The LXC is unprivileged with nesting disabled and Herdr SSH policy remains key-only with root login disabled.
- `searxng_onramp` has no plan or configuration diff.

Redact hostnames, addresses, public keys, private keys, tokens, and command output. Keep only sanitized pass/fail evidence in an approved private location.

## Backup and rollback

Before changing existing state, record the reviewed OpenTofu plan and create the approved recovery copy. Do not copy the Herdr transport private key to the controller, BWS, workstation, onramp, tracked files, or evidence. A host/LXC snapshot or approved private recovery boundary must preserve the Herdr home when an existing home or key set is being changed.

If a precondition fails before mutation, correct the precondition and rerun the targeted read-only check. Do not bypass a failed source, schema, digest, or host-key check with an alternate installer or trust store.

If live mutation partially succeeds, stop broader rollout and recover only the affected boundary:

- Restore the prior onramp relay, separate authorized-key file, and SSHD drop-in from the approved recovery copy when they were changed.
- Restore the prior Herdr SSH config, known_hosts, context endpoint, and operator-home state when they were changed.
- Remove the new onramp public-key entry only after confirming it did not replace a pre-existing entry. The corresponding private key remains or is removed only within the Herdr LXC under the approved recovery boundary.
- Retain the new LXC by default. Do not destroy it under this plan.
- Restore BWS service selection and DNS values only to the recorded prior values when the new service is not healthy.

Rollback is complete only when the original service endpoints pass, the onramp has no unintended TCP API or broad shell key, Herdr's direct operator endpoint is healthy, and `searxng_onramp` is unchanged. Any LXC destroy or state surgery requires a separate reviewed plan and explicit approval.

## Validation boundary for this task

This task uses only targeted source checks:

- Read-only path/reference inspection confirms the Herdr playbook, all listed roles/templates, tests, OpenTofu files, registry, fixture, and documentation paths exist.
- Text inspection confirms `herdr-onramp` is the only explicit Herdr Docker context and SSH alias, Pi and integration installation are inside Herdr as the operator, the private transport key stays in Herdr, and only its public half reaches onramp.
- Public-safety inspection is limited to changed public files: generic hostnames, RFC 5737 addresses, no private keys, no tokens, no BWS access key, and ASCII punctuation.
- The diff check is limited to the tracked paths listed above and confirms no implementation, test, BWS, or live-state path outside that inventory was changed.

No infrastructure, BWS, live SSH, Ansible, Docker, Proxmox, `just plan`, `just apply`, or final `just validate` operation is part of this task. The future rollout must run the repository's final `just validate` exactly once after all future implementation and live work is complete.

## Execution record for this task

- Implementation and tests: not edited.
- BWS and live state: not changed.
- Targeted text and public-safety inspections: completed; no stale generic context/alias, non-ASCII text, or private-key/token pattern was found in the changed public files.
- Git diff check: not run; the active file-only harness provided no shell or Git command runner.
- `just plan`: not run.
- `just apply`: not run.
- Final `just validate`: not run.
