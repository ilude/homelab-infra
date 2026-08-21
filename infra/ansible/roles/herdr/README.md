# Herdr direct role

This role runs over the direct Herdr SSH connection after the PVE bootstrap and
host-key handoff. It keeps the operator home persistent, installs only the
Docker CLI, manages the pinned Herdr binary, installs Pi with pnpm, and creates
the dedicated outbound ed25519 identity.
