# Copy to values/terraform.tfvars and fill in local values.

proxmox_endpoint  = "https://proxmox.example.internal:8006/"
proxmox_insecure  = true
proxmox_node_name = "pve"

# Prefer values/.env for secrets:
#   PROXMOX_VE_API_TOKEN
#   TF_VAR_container_root_password
#   TF_VAR_container_ssh_public_keys
#   TF_VAR_technitium_api_token
container_root_password = "REPLACE_WITH_A_LONG_RANDOM_PASSWORD"
container_ssh_public_keys = [
  "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA_REPLACE_ME user@host",
]

technitium_api_url = "http://192.0.2.53:5380/api"
dns_records_file   = "../../values/dns-records.local.json"

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
