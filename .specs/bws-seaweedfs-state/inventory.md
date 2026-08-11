# Sanitized Configuration and Placement Map

## Configuration families

| BWS key | Compatibility output | Existing validators and consumers |
|---|---|---|
| `HOMELAB_ENV` | `values/.env` in a temporary workspace | dotenv parser, controller environment, OpenTofu providers, Ansible service environment |
| `HOMELAB_TERRAFORM_TFVARS` | `values/terraform.tfvars` in a temporary workspace | OpenTofu variable loader, dynamic Ansible inventory, storage preparation |
| `HOMELAB_ANSIBLE_INVENTORY` | `values/ansible/inventory/local.yml` in a temporary workspace | Ansible inventory, roles, service readiness checks, backend routing fields |
| `HOMELAB_DNS_RECORDS` | `values/dns-records.local.json` in a temporary workspace | Technitium DNS validator and synchronization playbook |
| `HOMELAB_SETTINGS` | `settings.local.json` in a temporary workspace | enabled-service and private values-repository selection |

The inventory family is deterministically gzip-compressed and base64-encoded only to fit the BWS value limit. The rendered bytes are the original validated YAML. Other families are stored as exact text.

Runtime-only BWS keys provide the SeaweedFS S3 identity, OpenTofu state-encryption passphrase, and existing Onclave RabbitMQ credentials. `BITWARDEN_ACCESS_KEY` remains controller-only.

## BWS convention

The established BWS project already used by this deployment is authoritative. Canonical site snapshot keys use the `HOMELAB_` prefix. Service runtime keys retain their service-specific names. The ignored local `settings.local.json` contains only the BWS project and API-server locator. It contains no site configuration values or credentials.

## SeaweedFS placement

SeaweedFS runs as a digest-pinned rootless Podman workload on the existing managed `onramp_host`. Its data directory is on the existing persistent `/srv` filesystem. The shared onramp Caddy instance provides a dedicated HTTPS name while the S3 process remains loopback-bound. No guest, disk, Proxmox resource, router, or external storage is added.

Bootstrap and recovery order:

1. Restore the ignored BWS locator and controller access key.
2. Render the temporary configuration snapshot.
3. Restore or start the existing onramp host and its persistent `/srv` filesystem.
4. Start SeaweedFS and verify the versioned state bucket.
5. Run OpenTofu only after backend readability and locking checks pass.
6. Use the independent encrypted state and key recovery copies if BWS or SeaweedFS cannot be recovered.

## Excluded private data

The existing `values/` repository remains the location for service-state backups, artifacts, dumps, OCI data, and mutable Hermes state archives. Those paths are not rendered from BWS and are not migrated by this plan.
