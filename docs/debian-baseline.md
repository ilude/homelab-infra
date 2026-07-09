# Debian baseline split

This runbook currently uses a mixed Debian baseline:

- **LXCs** (Technitium, Forgejo, Infisical, Hermes, and related services) are installed from the Proxmox `debian-12` container templates represented by the `debian_template_*` OpenTofu variables.
- **`onramp_host`** is provisioned as a Debian 13 genericcloud VM.

Why this split is in use:

- Debian 12 LXC templates are lightweight and currently the stable baseline for most containerized service LXCs.
- Debian 13 genericcloud is used for onramp services because Podman workloads and rootless tooling are cleaner on that VM image path, with fewer constraints than LXC defaults.

A future migration of LXC hosts to Debian 13 should be a reviewed infrastructure change:

- Update private `values/terraform.tfvars` (`debian_template_*` family and related template inputs).
- Validate any service compatibility impact (Compose/system package behavior, rootless access assumptions).
- Re-run regular validation and planning before applying.
