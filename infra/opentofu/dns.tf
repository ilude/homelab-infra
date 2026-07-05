# Technitium DNS records are applied after Ansible configures the DNS LXC.
# Keep DNS record files validated during `just validate`, but do not call the
# Technitium API from OpenTofu: fresh installs need the LXC and Technitium
# service to exist before API mutation is possible.
