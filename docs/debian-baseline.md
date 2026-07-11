# Debian baseline

All Proxmox LXC services use the verified Debian 13 standard template:

- URL: `http://download.proxmox.com/images/system/debian-13-standard_13.1-2_amd64.tar.zst`
- filename: `debian-13-standard_13.1-2_amd64.tar.zst`
- checksum: SHA-512 `5aec4ab2ac5c16c7c8ecb87bfeeb10213abe96db6b85e2463585cea492fc861d7c390b3f9c95629bf690b95e9dfe1037207fc69c0912429605f208d5cb2621f8`

The official Proxmox HTTP transport remains integrity-protected: OpenTofu verifies the pinned SHA-512 checksum sourced from the signed Proxmox appliance index when downloading the template. Do not weaken or remove checksum validation. Existing `debian_template_*` private inputs migrate to the `debian_13_lxc_template_*` names. The managed download resource moves to its Debian 13 address, while each LXC keeps `template_file_id` observed so the next reviewed plan proposes container replacement for the operating-system change.

`onramp_host` is separate from the LXC baseline and uses a pinned Debian 13 genericcloud VM image:

- URL: `https://cloud.debian.org/images/cloud/trixie/20260623-2518/debian-13-genericcloud-amd64-20260623-2518.qcow2`
- filename: `debian-13-genericcloud-amd64-20260623-2518.qcow2`
- checksum: SHA-512 `df2bd468b08566c0409a7982d6489d73499ad22f9a28646b538c2f21d08f15040a5e4737952ca209e9ad4488cd00793191791be9f135dee93082c86fcca3300c`

## Existing deployment migration

Values migration replaces the onramp image only when both values match the former mutable pair:

- URL: `https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2`
- filename: `debian-13-genericcloud-amd64.qcow2`

It then writes the exact Debian 13 URL, filename, checksum algorithm, and SHA-512 checksum above only when checksum fields are absent or still equal the managed defaults. URL-only matches, filename-only matches, partial integrity groups, and custom checksum groups remain unchanged and operator-owned.

Before running `just setup` or its values migration, retain the private `values/` repository. Then run `just validate` and `just plan`; review the plan before any approved apply.
