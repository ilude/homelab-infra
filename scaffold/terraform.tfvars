# Copy to values/terraform.tfvars and fill in local values.

proxmox_endpoint  = "https://proxmox.example.internal:8006/"
proxmox_insecure  = true
proxmox_node_name = "pve"

# Prefer values/.env for secrets:
#   PROXMOX_VE_API_TOKEN
#   TF_VAR_lxc_root_password
#   TF_VAR_lxc_ssh_public_keys
lxc_root_password = "REPLACE_WITH_A_LONG_RANDOM_PASSWORD"
lxc_ssh_public_keys = [
  "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA_REPLACE_ME user@host",
]


technitium_container_vmid          = 106
technitium_container_hostname      = "technitium-dns"
technitium_container_description   = "Technitium DNS primary resolver managed by OpenTofu."
technitium_container_ipv4_address  = "192.0.2.54/24"
technitium_container_ipv4_gateway  = "192.0.2.1"
technitium_container_dns_servers   = ["1.1.1.1", "9.9.9.9"]
technitium_container_search_domain = "example.internal"
technitium_container_bridge        = "vmbr0"
technitium_container_vlan_id       = null

rootfs_datastore_id   = "local-lvm"
template_datastore_id = "local"
# All LXC services use this verified Debian 13 baseline.
debian_13_lxc_template_url                = "http://download.proxmox.com/images/system/debian-13-standard_13.1-2_amd64.tar.zst"
debian_13_lxc_template_file_name          = "debian-13-standard_13.1-2_amd64.tar.zst"
debian_13_lxc_template_checksum_algorithm = "sha512"
debian_13_lxc_template_checksum           = "5aec4ab2ac5c16c7c8ecb87bfeeb10213abe96db6b85e2463585cea492fc861d7c390b3f9c95629bf690b95e9dfe1037207fc69c0912429605f208d5cb2621f8"

technitium_container_cores     = 1
technitium_container_memory_mb = 1024
technitium_container_swap_mb   = 512
technitium_container_disk_gb   = 8

# Optional Technitium cluster node on a standalone secondary Proxmox host.
# Enable by adding technitium_secondary to settings.local.json services.
technitium_cluster_enabled                   = false
technitium_cluster_domain                    = "dns-cluster.example.internal"
technitium_virtual_ipv4_address              = "192.0.2.53/24"
secondary_proxmox_insecure                   = true
secondary_proxmox_node_name                  = "pve-secondary"
secondary_proxmox_rootfs_datastore_id        = "local-lvm"
secondary_proxmox_template_datastore_id      = "local"
technitium_secondary_container_vmid          = 206
technitium_secondary_container_hostname      = "technitium-dns-2"
technitium_secondary_container_description   = "Technitium DNS secondary resolver managed by OpenTofu."
technitium_secondary_container_ipv4_address  = "192.0.2.55/24"
technitium_secondary_container_ipv4_gateway  = "192.0.2.1"
technitium_secondary_container_dns_servers   = ["1.1.1.1", "9.9.9.9"]
technitium_secondary_container_search_domain = "example.internal"
technitium_secondary_container_bridge        = "vmbr0"
technitium_secondary_container_vlan_id       = null

technitium_secondary_container_cores     = 1
technitium_secondary_container_memory_mb = 1024
technitium_secondary_container_swap_mb   = 512
technitium_secondary_container_disk_gb   = 8

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
forgejo_container_vlan_id       = null

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
forgejo_runner_vlan_id       = null

forgejo_runner_cores     = 2
forgejo_runner_memory_mb = 2048
forgejo_runner_swap_mb   = 512
forgejo_runner_disk_gb   = 16

forgejo_runner_started       = true
forgejo_runner_start_on_boot = true

# Optional Infisical secrets service. Enable legacy LXC by adding infisical to settings.local.json services,
# or enable rootless onramp deployment by adding infisical_onramp with onramp_host.
infisical_container_vmid          = 110
infisical_container_hostname      = "infisical"
infisical_container_description   = "Infisical secrets service managed by OpenTofu."
infisical_container_ipv4_address  = "dhcp"
infisical_container_ipv4_gateway  = null
infisical_container_mac_address   = "BC:24:11:00:00:03"
infisical_lan_ip                  = "192.0.2.70"
infisical_server_name             = "infisical.example.internal"
infisical_container_dns_servers   = ["192.0.2.1"]
infisical_container_search_domain = "example.internal"
infisical_container_bridge        = "vmbr0"
infisical_container_vlan_id       = null

infisical_container_cores     = 2
infisical_container_memory_mb = 4096
infisical_container_swap_mb   = 1024
infisical_container_disk_gb   = 20


infisical_started       = true
infisical_start_on_boot = true

# Optional Hermes management LXC. Enable by adding hermes to settings.local.json services.
hermes_container_vmid          = 111
hermes_container_hostname      = "hermes"
hermes_container_description   = "Hermes management LXC managed by OpenTofu."
hermes_container_ipv4_address  = "dhcp"
hermes_container_ipv4_gateway  = null
hermes_container_mac_address   = "BC:24:11:00:00:04"
hermes_lan_ip                  = "192.0.2.71"
hermes_server_name             = "hermes.example.internal"
hermes_container_dns_servers   = ["192.0.2.1"]
hermes_container_search_domain = "example.internal"
hermes_container_bridge        = "vmbr0"
hermes_container_vlan_id       = null

hermes_container_cores     = 2
hermes_container_memory_mb = 2048
hermes_container_swap_mb   = 512
hermes_container_disk_gb   = 64

hermes_runtime_user  = "anvil"
hermes_started       = true
hermes_start_on_boot = true

# Optional Debian 13 Podman onramp-host VM for Onramp-managed services. Enable by adding onramp_host to settings.local.json services.
# The onramp host is created from a clean Debian 13 genericcloud image, not from a mutable local template.
onramp_host_vmid                     = 112
onramp_host_rebuild_revision         = "two-disk-v1"
onramp_host_hostname                 = "onramp-host"
onramp_host_description              = "Debian 13 Podman onramp host for Onramp-managed services."
onramp_host_image_datastore_id       = "local"
onramp_host_image_url                = "https://cloud.debian.org/images/cloud/trixie/20260623-2518/debian-13-genericcloud-amd64-20260623-2518.qcow2"
onramp_host_image_file_name          = "debian-13-genericcloud-amd64-20260623-2518.qcow2"
onramp_host_image_checksum_algorithm = "sha512"
onramp_host_image_checksum           = "df2bd468b08566c0409a7982d6489d73499ad22f9a28646b538c2f21d08f15040a5e4737952ca209e9ad4488cd00793191791be9f135dee93082c86fcca3300c"
onramp_host_datastore_id             = "local-lvm"
onramp_host_data_datastore_id        = "vmstorage"
onramp_host_data_device              = "/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi1"
onramp_host_ipv4_address             = "192.0.2.72/24"
onramp_host_ipv4_gateway             = "192.0.2.1"
onramp_host_dns_servers              = ["192.0.2.1"]
onramp_host_search_domain            = "example.internal"
onramp_host_bridge                   = "vmbr0"
onramp_host_vlan_id                  = null

onramp_host_cores               = 2
onramp_host_memory_mb           = 4096
onramp_host_disk_gb             = 32
onramp_host_data_disk_gb        = 512
onramp_host_var_lv_gb           = 96
onramp_host_srv_lv_gb           = 352
onramp_host_vg_min_free_percent = 10

onramp_host_cloud_init_user = "anvil"
# Defaults to lxc_ssh_public_keys when empty.
onramp_host_ssh_public_keys         = []
onramp_host_password_authentication = false
onramp_host_permit_root_login       = false
onramp_host_deploy_user             = "anvil"
onramp_host_deploy_dir              = "/srv/onramp"
onramp_host_allow_passwordless_sudo = true
onramp_host_allowed_ssh_cidrs       = ["192.0.2.0/24"]
onramp_host_started                 = true
onramp_host_start_on_boot           = true

# Optional SearXNG workload on the onramp host. Enable by adding searxng_onramp and onramp_host to settings.local.json services.
searxng_server_name       = "searxng.apps.example.net"
searxng_public_url        = "https://searxng.apps.example.net"
searxng_container_image   = "docker.io/searxng/searxng:2026.7.2-67973783d@sha256:33aa33278be6c0be379b95f7c91cd455c18141295291c2e5a396454761df7bbb"
searxng_container_port    = 8080
searxng_bind_address      = "127.0.0.1"
searxng_instance_name     = "Homelab SearXNG"
searxng_enable_public_url = true

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
tailscale_client_vlan_id       = null

tailscale_client_cores     = 1
tailscale_client_memory_mb = 512
tailscale_client_swap_mb   = 256
tailscale_client_disk_gb   = 4

tailscale_client_started       = true
tailscale_client_start_on_boot = true
