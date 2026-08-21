# Forgejo bind-mount lifecycle

Forgejo's data bind mount is owned by Ansible at the Proxmox host boundary, not by the Proxmox API provider. OpenTofu still creates the Forgejo LXC with API-token authentication, but the Forgejo module declares no `mount_points`. The shared LXC resource ignores `mount_point` changes because no module-managed bind mounts remain; this prevents a later refresh or apply from deleting the SSH-managed mount.

`forgejo_data_host_path`, `forgejo_data_mount_path`, and the Forgejo VMID are owned by the BWS `HOMELAB_TERRAFORM_TFVARS` family. The tooling container renders that family to a temporary compatibility workspace; dynamic inventory promotes the rendered values to the PVE lifecycle play without copying them into a separate Ansible inventory source. Storage preparation assigns the mapped-root owner only when it creates the dataset. Later applies preserve the service-managed owner set inside the LXC.

During `infra/ansible/playbooks/forgejo.yml`, Ansible:

1. waits for the LXC on the configured Proxmox node;
2. validates the VMID and strict absolute host/guest paths;
3. requires the host path to exist as a real directory;
4. inspects `pct config` and accepts only the expected `mp0` mapping;
5. fails without overwriting when the slot, host path, or guest path conflicts;
6. attaches a missing mapping with argv-based `pct set`, reboots only after a change, and waits for readiness again; and
7. only then begins the normal direct-service SSH handoff.

The operation is idempotent: an exact mapping causes neither `pct set` nor reboot. Do not repair conflicts with ad hoc `pct` commands. Correct the reviewed BWS configuration or the conflicting Proxmox configuration through an explicitly approved recovery, then rerun the normal `just plan` and approved `just apply` workflow. Backup and restore procedures remain documented in [service state backup and restore](service-state-backup.md).
