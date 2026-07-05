# Copy to values/terraform.tfvars and fill in local values.

proxmox_endpoint  = "https://proxmox.example.internal:8006/"
proxmox_insecure  = true
proxmox_node_name = "pve"

# Prefer values/.env for secrets:
#   PROXMOX_VE_API_TOKEN
#   TF_VAR_container_root_password
#   TF_VAR_container_ssh_public_keys
container_root_password = "REPLACE_WITH_A_LONG_RANDOM_PASSWORD"
container_ssh_public_keys = [
  "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA_REPLACE_ME user@host",
]


container_vmid          = 106
container_hostname      = "technitium-dns"
container_description   = "Technitium DNS primary resolver managed by OpenTofu."
container_ipv4_address  = "192.0.2.53/24"
container_ipv4_gateway  = "192.0.2.1"
container_dns_servers   = ["1.1.1.1", "9.9.9.9"]
container_search_domain = "example.internal"
container_bridge        = "vmbr0"

rootfs_datastore_id       = "local-lvm"
template_datastore_id     = "local"
debian_template_url       = "http://download.proxmox.com/images/system/debian-12-standard_12.12-1_amd64.tar.zst"
debian_template_file_name = "debian-12-standard_12.12-1_amd64.tar.zst"

container_cores     = 1
container_memory_mb = 1024
container_swap_mb   = 512
container_disk_gb   = 8

forgejo_container_vmid          = 107
forgejo_container_hostname      = "forgejo"
forgejo_container_description   = "Forgejo git service managed by OpenTofu."
forgejo_container_ipv4_address  = "dhcp"
forgejo_container_ipv4_gateway  = null
forgejo_container_mac_address   = "BC:24:11:00:00:00"
forgejo_lan_ip                  = "192.0.2.62"
forgejo_server_name             = "git.example.internal"
forgejo_container_dns_servers   = ["192.0.2.1"]
forgejo_container_search_domain = "example.internal"
forgejo_container_bridge        = "vmbr0"

forgejo_container_cores     = 2
forgejo_container_memory_mb = 2048
forgejo_container_swap_mb   = 512
forgejo_container_disk_gb   = 8

forgejo_data_dataset    = "tank/forgejo"
forgejo_data_host_path  = "/tank/forgejo"
forgejo_data_mount_path = "/var/lib/forgejo"

# Optional Forgejo Actions runner LXC. Enable by adding forgejo_runner to settings.local.json services.
forgejo_runner_vmid          = 109
forgejo_runner_hostname      = "forgejo-runner"
forgejo_runner_description   = "Forgejo Actions runner managed by OpenTofu."
forgejo_runner_ipv4_address  = "dhcp"
forgejo_runner_ipv4_gateway  = null
forgejo_runner_mac_address   = "BC:24:11:00:00:02"
forgejo_runner_dns_servers   = ["192.0.2.1"]
forgejo_runner_search_domain = "example.internal"
forgejo_runner_bridge        = "vmbr0"

forgejo_runner_cores     = 2
forgejo_runner_memory_mb = 2048
forgejo_runner_swap_mb   = 512
forgejo_runner_disk_gb   = 16

forgejo_runner_started       = true
forgejo_runner_start_on_boot = true

# Optional Tailscale client LXC. Leave disabled until a reviewed plan should create it.
tailscale_client_enabled       = false
tailscale_client_vmid          = 108
tailscale_client_hostname      = "tailscale-client"
tailscale_client_description   = "Tailscale client LXC managed by OpenTofu."
tailscale_client_ipv4_address  = "dhcp"
tailscale_client_ipv4_gateway  = null
tailscale_client_mac_address   = "BC:24:11:00:00:01"
tailscale_client_dns_servers   = ["1.1.1.1", "9.9.9.9"]
tailscale_client_search_domain = "example.internal"
tailscale_client_bridge        = "vmbr0"

tailscale_client_cores     = 1
tailscale_client_memory_mb = 512
tailscale_client_swap_mb   = 256
tailscale_client_disk_gb   = 4

tailscale_client_started       = true
tailscale_client_start_on_boot = true
