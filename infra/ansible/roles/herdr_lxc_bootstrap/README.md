# Herdr LXC bootstrap

This role is the PVE-only lifecycle handoff for Herdr. It creates the dedicated
operator and its initial SSH and sudo access through `pct exec`. Steady-state
configuration belongs to the direct Herdr roles.
