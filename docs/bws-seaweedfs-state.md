# BWS configuration and SeaweedFS state

BWS is authoritative for site configuration. OpenTofu state is encrypted and stored in the versioned SeaweedFS S3 backend. The ignored `values/` repository remains only for excluded backup, artifact, dump, and mutable service-state data.

## Controller bootstrap

Create ignored `settings.local.json` with only the BWS locator:

```json
{
  "bws": {
    "project_id": "REPLACE_WITH_BWS_PROJECT_ID",
    "api_server": "https://vault.example.internal/api"
  }
}
```

Set `BITWARDEN_ACCESS_KEY` in the controller environment. Do not store it in `settings.local.json`, BWS snapshot values, `values/`, or managed-host files.

Run setup with an optional private excluded-data repository URL:

```bash
just setup
just setup git@git.example.internal:owner/homelab-infra-values.git
```

Setup builds the tooling image, checks that `values/` contains no obsolete configuration or local OpenTofu state, resolves BWS, and validates the generated settings.

## BWS snapshot contract

The routing manifest is `config/bws-routing.json`. It maps these BWS keys to existing validated file formats:

- `HOMELAB_ENV`
- `HOMELAB_TERRAFORM_TFVARS`
- `HOMELAB_ANSIBLE_INVENTORY`
- `HOMELAB_DNS_RECORDS`
- `HOMELAB_SETTINGS`

The inventory value is deterministic gzip plus base64 because the raw YAML can exceed the BWS value limit. Rendering restores the exact YAML bytes before validation. Runtime-only keys supply SeaweedFS S3 credentials, the OpenTofu encryption passphrase, and service-specific credentials such as the existing Onclave RabbitMQ values.

`scripts/run-infra.sh` starts an ephemeral tooling container, resolves only the runtime profile needed by the command, validates every required family, and writes mode-restricted compatibility files below container `/tmp`. The container is removed after the command, including on failure. Original `values/` backup and artifact paths remain mounted separately and are never copied into the snapshot.

Missing, empty, duplicate, malformed, or placeholder required values fail closed. Diagnostics name keys but do not print values.

## Normal workflow

```bash
just update
just plan
just apply
just validate
```

`just update` changes tracked pins and updates changed BWS file families only after the update command succeeds. `just plan` and `just apply` independently render BWS snapshots. Saved plan metadata includes a snapshot hash, so an intervening BWS change invalidates the plan.

Do not recreate `.env`, tfvars, inventory, DNS JSON, settings, or `terraform.tfstate` under `values/`. `scripts/values.sh check` rejects those obsolete sources.

## SeaweedFS state backend

`seaweedfs_onramp` runs the immutable-pinned SeaweedFS image as a rootless Podman workload on the existing `onramp_host`. Data persists under `/srv` on the existing host storage. The shared local Caddy instance exposes the dedicated HTTPS S3 name while SeaweedFS remains loopback-bound.

The dedicated state bucket has versioning enabled. Noncurrent state versions are retained substantially longer than historical `.tflock` versions, and expired lock delete markers are eligible for cleanup. OpenTofu uses native S3 conditional-write locking with `use_lockfile = true`.

State and saved plans use BWS-backed PBKDF2 plus AES-GCM encryption. Normal commands enforce encrypted reads and writes. The controller access key is not copied to the SeaweedFS host; only the S3 runtime identity is stored in the protected service directory.

For a targeted service repair:

```bash
scripts/apply-service.sh seaweedfs_onramp
```

After repair, verify direct HTTPS/S3 access, bucket versioning and lifecycle, an old object version, conditional-write rejection, restart persistence, and absent current lock before running OpenTofu.

## Recovery order

1. Stop all OpenTofu plans and applies.
2. Confirm that no process owns the state lock. Do not use `force-unlock` without that proof.
3. Restore the BWS locator and controller access key.
4. Restore or start the existing onramp host and persistent `/srv` filesystem.
5. Start SeaweedFS and verify direct S3 access, versioning, lifecycle, and state-object readability.
6. Compare remote lineage, serial, and resource count with the sanitized recovery metadata.
7. If the remote state is unusable, recover the exact verified state copy without editing its contents. Keep the original backend stopped until the recovered endpoint and a no-drift plan pass.

Maintain an independent encrypted state copy and an independently encrypted key-recovery copy outside SeaweedFS and outside the checkout. Verify both readbacks after creation. On Windows, a current-user DPAPI-protected copy is suitable for the local recovery boundary; another operator may choose an equivalent encrypted offline mechanism.

## Remaining `values/` boundary

Allowed private data includes:

- `artifacts/`
- `service-backups/`
- database dumps and migration handoffs
- OCI and object-data exports
- mutable Hermes state archives

These exclusions are not BWS configuration and are not OpenTofu state. Keep the nested repository private and continue its independent backup policy.
