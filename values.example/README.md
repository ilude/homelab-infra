# homelab-infra values template

This directory is a public-safe template for a private `values/` repo.

`values/` should be a separate private Git repository, normally hosted on your private Forgejo instance, and is ignored by the public runbooks repo.

## Files

- `.env` — local credentials and bootstrap environment variables.
- `terraform.tfvars` — site-specific Proxmox/LXC/OpenTofu variables.
- `dns-records.local.json` — site-specific Technitium DNS zones and records.
- `ansible/inventory/local.yml` — site-specific Ansible inventory and role variables.

## Initialize

From the runbooks repo root:

```bash
just setup
```

Or clone an existing private values repo during setup:

```bash
just setup git@git.example.internal:owner/homelab-infra-values.git
```
