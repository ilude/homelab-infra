# Private excluded-data repository

This repository is retained only for private data that is deliberately outside the BWS site-configuration snapshot:

- service-state backup archives and checksums
- database dumps and migration artifacts
- cached release artifacts
- OCI or object-data exports
- mutable Hermes state archives

Do not add site configuration or OpenTofu state here. BWS is authoritative for the rendered `.env`, tfvars, Ansible inventory, DNS records, and operator settings. SeaweedFS is authoritative for encrypted OpenTofu state.

The public runbook checkout ignores `values/`, so initialize this directory as its own private Git repository. See [`docs/bws-seaweedfs-state.md`](../docs/bws-seaweedfs-state.md) in the public runbook for bootstrap, recovery, and validation procedures.
