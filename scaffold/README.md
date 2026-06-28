# homelab-infra values template

This directory is a public-safe template for `values/`, the nested private Git repo that stores site values and state.

`values/` is ignored by the public runbooks repo. In normal use it has its own private remote, such as a Forgejo repository, and is committed/pushed separately from this repo.

## Files

- `.env` — local credentials and bootstrap environment variables.
- `terraform.tfvars` — site-specific Proxmox/LXC/OpenTofu variables, including the optional disabled-by-default Tailscale client LXC.
- `dns-records.local.json` — site-specific Technitium DNS zones and records.
- `ansible/inventory/local.yml` — site-specific Ansible inventory and role variables.

## Initialize

From the runbooks repo root:

```bash
cp settings.example.json settings.local.json  # optional local setup defaults
just setup
```

Or clone an existing private values repo, such as the Forgejo-hosted values repo, during setup:

```bash
just setup git@git.example.internal:owner/homelab-infra-values.git
```

After editing the copied files, run the normal validation entry point:

```bash
just validate
```

Keep `.env` in dotenv-style `KEY=value` or `export KEY=value` format. The runbooks parse it as data and reject shell execution patterns.
