# Service update policy

Managed services should use deterministic version pins and the normal reviewed workflow:

```bash
just update
just validate
just plan
just apply
```

`just update` applies the release-age safety hold before changing supported pins. After any update, review the diff and plan before applying.

## Managed pins

A service belongs in `just update` when the repo can identify a specific upstream release and update a deterministic local pin. Examples include Forgejo and Forgejo runner.

For downloadable tools or archives, prefer a version plus checksum. If upstream artifacts are mutable or unversioned, cache the reviewed artifact in ignored private storage and install from that cache during `just apply`.

## Technitium

Technitium DNS is managed by Ansible and must not be upgraded by rerunning an upstream installer. The current implementation:

- Pins a version and portable tarball SHA256 in private values.
- Downloads the versioned archive from the Technitium archive endpoint.
- Optionally stages a controller-side archive cache configured with `technitium_artifact_path`.
- Compares the installed-version marker with the requested pin.
- Validates the archive layout and checksum before activation.
- Performs health checks and retains rollback state during activation.

Technitium is not currently a target of `just update`. To change it, update the private version/checksum together, then run `just validate`, review `just plan`, and apply only after approval. Do not use the upstream installer as a routine update mechanism.

## Other update boundaries

`just update` currently manages OpenTofu, TFLint, Forgejo, Forgejo runner, Docker Compose, and just pins. Caddy build inputs are version-pinned but do not yet have an automated update target. Tailscale package updates and general guest OS upgrades are also outside the `just update` workflow.

For components not managed by `just update`, document the reviewed pin or package policy explicitly and avoid ad hoc production upgrades.

## Guest security updates

Guest operating-system updates are intentionally **operator-initiated**, not unattended. The current policy is:

- apply guest package updates only through an approved Ansible change in the normal reviewed workflow;
- disable automatic reboot behavior; report any reboot requirement for a separately reviewed maintenance action;
- scope maintenance to explicitly selected services/guests and record restart impact before the change;
- do not couple guest package updates with a managed application release-pin change;
- keep Caddy and Tailscale within their existing explicit provenance/update paths rather than silently treating them as general OS updates;
- treat Technitium as a critical-DNS exception: use its version/checksum/health/rollback workflow, never a blanket package-upgrade action.

This policy is a design boundary, not an unattended-update implementation. Any future security-update role must add LXC and VM coverage, no-auto-reboot verification, restart/reboot reporting, and an explicit opt-in inventory contract before it is enabled.
