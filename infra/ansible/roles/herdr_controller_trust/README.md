# Herdr controller trust

The VM handoff replaces the shared ephemeral controller known_hosts file. This
role creates a separate return-handoff file from the host keys already verified
by the direct Herdr LXC handoff; it performs no network scan or Proxmox access.
