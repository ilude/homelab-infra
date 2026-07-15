variable "enabled_services" {
  description = "Services OpenTofu should build and maintain. Service selection is normally supplied from settings.local.json by just plan. Null uses infra/services.json default_services."
  type        = list(string)
  default     = null
}


variable "proxmox_endpoint" {
  description = "Proxmox VE API endpoint. Set in terraform.tfvars."
  type        = string
}

variable "proxmox_insecure" {
  description = "Allow the Proxmox provider to trust the PVE self-signed certificate. Set in terraform.tfvars."
  type        = bool
}

variable "proxmox_api_token" {
  description = "Proxmox API token, e.g. terraform@pve!provider=secret. Prefer PROXMOX_VE_API_TOKEN or terraform.tfvars."
  type        = string
  default     = null
  sensitive   = true
}

variable "proxmox_username" {
  description = "Proxmox username for password auth, e.g. root@pam. Prefer PROXMOX_VE_USERNAME or terraform.tfvars."
  type        = string
  default     = null
  sensitive   = true
}

variable "proxmox_password" {
  description = "Proxmox password for password auth. Prefer PROXMOX_VE_PASSWORD or terraform.tfvars."
  type        = string
  default     = null
  sensitive   = true
}

variable "proxmox_node_name" {
  description = "Proxmox node where the Technitium LXC should run. Set in terraform.tfvars."
  type        = string
}

variable "technitium_container_vmid" {
  description = "Proxmox VMID for the Technitium DNS LXC. Set in terraform.tfvars."
  type        = number
}

variable "technitium_container_hostname" {
  description = "Hostname for the Technitium DNS LXC. Set in terraform.tfvars."
  type        = string
}

variable "technitium_container_description" {
  description = "Description for the Technitium DNS LXC. Set in terraform.tfvars if you want a site-specific label."
  type        = string
  default     = "Technitium DNS primary resolver managed by OpenTofu."
}

variable "technitium_container_ipv4_address" {
  description = "Static IPv4 address/CIDR for the Technitium DNS LXC. Use an address outside DHCP scope. Set in terraform.tfvars."
  type        = string

  validation {
    condition     = can(cidrhost(var.technitium_container_ipv4_address, 0))
    error_message = "technitium_container_ipv4_address must be a valid IPv4 CIDR address, for example 192.0.2.10/24."
  }
}

variable "technitium_container_ipv4_gateway" {
  description = "IPv4 gateway for the Technitium DNS LXC. Set in terraform.tfvars."
  type        = string
}

variable "technitium_container_dns_servers" {
  description = "DNS servers used by the LXC before it becomes the primary resolver. Set in terraform.tfvars."
  type        = list(string)
}

variable "technitium_container_search_domain" {
  description = "DNS search domain for the LXC. Set in terraform.tfvars."
  type        = string
}

variable "technitium_container_bridge" {
  description = "Proxmox bridge for the LXC interface. Set in terraform.tfvars."
  type        = string
}

variable "technitium_container_vlan_id" {
  description = "Optional VLAN tag for the Technitium DNS LXC interface. Null leaves the interface untagged."
  type        = number
  default     = null

  validation {
    condition     = var.technitium_container_vlan_id == null || (var.technitium_container_vlan_id >= 1 && var.technitium_container_vlan_id <= 4094)
    error_message = "technitium_container_vlan_id must be null or a VLAN ID from 1 through 4094."
  }
}

variable "rootfs_datastore_id" {
  description = "Proxmox datastore for the LXC root filesystem. Set in terraform.tfvars."
  type        = string
}

variable "template_datastore_id" {
  description = "Proxmox datastore for downloaded LXC templates. Set in terraform.tfvars."
  type        = string
}

variable "debian_13_lxc_template_url" {
  description = "Verified Debian 13 standard LXC template URL. Set in terraform.tfvars."
  type        = string

  validation {
    condition     = var.debian_13_lxc_template_url == "http://download.proxmox.com/images/system/debian-13-standard_13.1-2_amd64.tar.zst"
    error_message = "debian_13_lxc_template_url must use the reviewed Debian 13 LXC template pin."
  }
}

variable "debian_13_lxc_template_file_name" {
  description = "File name for the verified Debian 13 LXC template. Set in terraform.tfvars."
  type        = string

  validation {
    condition     = var.debian_13_lxc_template_file_name == "debian-13-standard_13.1-2_amd64.tar.zst"
    error_message = "debian_13_lxc_template_file_name must use the reviewed Debian 13 LXC template pin."
  }
}

variable "debian_13_lxc_template_checksum_algorithm" {
  description = "Checksum algorithm for the verified Debian 13 LXC template."
  type        = string

  validation {
    condition     = var.debian_13_lxc_template_checksum_algorithm == "sha512"
    error_message = "debian_13_lxc_template_checksum_algorithm must be sha512."
  }
}

variable "debian_13_lxc_template_checksum" {
  description = "SHA-512 checksum from the Debian 13 Proxmox appliance metadata."
  type        = string

  validation {
    condition     = var.debian_13_lxc_template_checksum == "5aec4ab2ac5c16c7c8ecb87bfeeb10213abe96db6b85e2463585cea492fc861d7c390b3f9c95629bf690b95e9dfe1037207fc69c0912429605f208d5cb2621f8"
    error_message = "debian_13_lxc_template_checksum must match the reviewed Debian 13 LXC template pin."
  }
}

variable "lxc_root_password" {
  description = "Initial root password for the LXC. Store only in terraform.tfvars or environment injection."
  type        = string
  sensitive   = true
}

variable "lxc_ssh_public_keys" {
  description = "SSH public keys to install for root in the LXC."
  type        = list(string)
  default     = []
}

variable "technitium_container_cores" {
  description = "CPU cores for the Technitium DNS LXC. Set in terraform.tfvars."
  type        = number
}

variable "technitium_container_memory_mb" {
  description = "Dedicated memory for the Technitium DNS LXC. Set in terraform.tfvars."
  type        = number
}

variable "technitium_container_swap_mb" {
  description = "Swap for the Technitium DNS LXC. Set in terraform.tfvars."
  type        = number
}

variable "technitium_container_disk_gb" {
  description = "Root filesystem size in GB. Set in terraform.tfvars."
  type        = number
}

variable "technitium_cluster_enabled" {
  description = "Initialize the primary and secondary Technitium instances as a cluster."
  type        = bool
  default     = false
}

variable "technitium_cluster_domain" {
  description = "Immutable DNS domain used by the Technitium cluster. Choose it before enabling clustering."
  type        = string
  default     = "dns-cluster.example.internal"

  validation {
    condition     = can(regex("^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])$", var.technitium_cluster_domain))
    error_message = "technitium_cluster_domain must be a fully qualified DNS name."
  }
}

variable "technitium_virtual_ipv4_address" {
  description = "Floating IPv4 CIDR advertised by Keepalived for LAN DNS clients."
  type        = string
  default     = "192.0.2.53/24"

  validation {
    condition     = can(cidrhost(var.technitium_virtual_ipv4_address, 0))
    error_message = "technitium_virtual_ipv4_address must be a valid IPv4 CIDR address."
  }
}

variable "secondary_proxmox_endpoint" {
  description = "Proxmox VE API endpoint for the standalone secondary provider. Set in terraform.tfvars before enabling technitium_secondary."
  type        = string
  default     = "https://proxmox-secondary.example.invalid:8006/"

  validation {
    condition     = can(regex("^https://", var.secondary_proxmox_endpoint))
    error_message = "secondary_proxmox_endpoint must be an HTTPS Proxmox VE API endpoint."
  }
}

variable "secondary_proxmox_insecure" {
  description = "Allow the secondary Proxmox provider to trust its self-signed certificate."
  type        = bool
  default     = false
}

variable "secondary_proxmox_api_token" {
  description = "API token for the standalone secondary Proxmox provider. Store it only in private values or environment injection."
  type        = string
  default     = null
  sensitive   = true
}

variable "secondary_proxmox_node_name" {
  description = "Node on the standalone secondary Proxmox provider that hosts the Technitium secondary LXC."
  type        = string
  default     = "pve-secondary"
}

variable "secondary_proxmox_rootfs_datastore_id" {
  description = "Datastore on the secondary Proxmox provider for the Technitium secondary LXC root filesystem."
  type        = string
  default     = "local-lvm"
}

variable "secondary_proxmox_template_datastore_id" {
  description = "Datastore on the secondary Proxmox provider for downloaded LXC templates."
  type        = string
  default     = "local"
}

variable "technitium_secondary_container_vmid" {
  description = "Proxmox VMID for the secondary Technitium DNS LXC."
  type        = number
  default     = 102

  validation {
    condition     = var.technitium_secondary_container_vmid > 0 && var.technitium_secondary_container_vmid < 1000000000
    error_message = "technitium_secondary_container_vmid must be a positive Proxmox VMID."
  }
}

variable "technitium_secondary_container_hostname" {
  description = "Hostname for the secondary Technitium DNS LXC."
  type        = string
  default     = "technitium-secondary"
}

variable "technitium_secondary_container_description" {
  description = "Description for the secondary Technitium DNS LXC."
  type        = string
  default     = "Technitium DNS secondary resolver managed by OpenTofu."
}

variable "technitium_secondary_container_ipv4_address" {
  description = "Static IPv4 address/CIDR for the secondary Technitium DNS LXC."
  type        = string
  default     = "192.0.2.11/24"

  validation {
    condition     = can(cidrhost(var.technitium_secondary_container_ipv4_address, 0))
    error_message = "technitium_secondary_container_ipv4_address must be a valid IPv4 CIDR address, for example 192.0.2.11/24."
  }
}

variable "technitium_secondary_container_ipv4_gateway" {
  description = "IPv4 gateway for the secondary Technitium DNS LXC."
  type        = string
  default     = "192.0.2.1"
}

variable "technitium_secondary_container_dns_servers" {
  description = "DNS servers used by the secondary Technitium LXC before it becomes a resolver."
  type        = list(string)
  default     = ["1.1.1.1", "9.9.9.9"]
}

variable "technitium_secondary_container_search_domain" {
  description = "DNS search domain for the secondary Technitium LXC."
  type        = string
  default     = "example.internal"
}

variable "technitium_secondary_container_bridge" {
  description = "Proxmox bridge for the secondary Technitium LXC interface."
  type        = string
  default     = "vmbr0"
}

variable "technitium_secondary_container_vlan_id" {
  description = "Optional VLAN tag for the secondary Technitium LXC interface. Null leaves the interface untagged."
  type        = number
  default     = null

  validation {
    condition     = var.technitium_secondary_container_vlan_id == null || (var.technitium_secondary_container_vlan_id >= 1 && var.technitium_secondary_container_vlan_id <= 4094)
    error_message = "technitium_secondary_container_vlan_id must be null or a VLAN ID from 1 through 4094."
  }
}

variable "technitium_secondary_container_cores" {
  description = "CPU cores for the secondary Technitium DNS LXC."
  type        = number
  default     = 1
}

variable "technitium_secondary_container_memory_mb" {
  description = "Dedicated memory for the secondary Technitium DNS LXC."
  type        = number
  default     = 1024
}

variable "technitium_secondary_container_swap_mb" {
  description = "Swap for the secondary Technitium DNS LXC."
  type        = number
  default     = 512
}

variable "technitium_secondary_container_disk_gb" {
  description = "Root filesystem size in GB for the secondary Technitium DNS LXC."
  type        = number
  default     = 8
}

variable "forgejo_container_vmid" {
  description = "Proxmox VMID for the Forgejo LXC. Set in terraform.tfvars. Import existing CTs before applying this resource."
  type        = number
}

variable "forgejo_container_hostname" {
  description = "Hostname for the Forgejo LXC. Set in terraform.tfvars."
  type        = string
}

variable "forgejo_container_description" {
  description = "Description for the Forgejo LXC."
  type        = string
  default     = "Forgejo git service managed by OpenTofu."
}

variable "forgejo_container_ipv4_address" {
  description = "IPv4 address/CIDR for the Forgejo LXC, or dhcp when the router supplies a static DHCP reservation."
  type        = string

  validation {
    condition     = var.forgejo_container_ipv4_address == "dhcp" || can(cidrhost(var.forgejo_container_ipv4_address, 0))
    error_message = "forgejo_container_ipv4_address must be dhcp or a valid IPv4 CIDR address."
  }
}

variable "forgejo_container_ipv4_gateway" {
  description = "IPv4 gateway for the Forgejo LXC. Use null when forgejo_container_ipv4_address is dhcp."
  type        = string
  default     = null
}

variable "forgejo_container_mac_address" {
  description = "MAC address for the Forgejo LXC, used by the router static DHCP reservation."
  type        = string

  validation {
    condition     = can(regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", var.forgejo_container_mac_address))
    error_message = "forgejo_container_mac_address must use colon-separated hex octets, for example BC:24:11:00:00:00."
  }
}

variable "forgejo_lan_ip" {
  description = "Expected LAN IP for Forgejo, without CIDR. Used for outputs and DNS/proxy documentation when the LXC uses DHCP reservation."
  type        = string
}

variable "forgejo_server_name" {
  description = "DNS hostname users should use for Forgejo. Set in terraform.tfvars."
  type        = string
}

variable "forgejo_container_dns_servers" {
  description = "DNS servers used by the Forgejo LXC. Set in terraform.tfvars."
  type        = list(string)
}

variable "forgejo_container_search_domain" {
  description = "DNS search domain for the Forgejo LXC. Set in terraform.tfvars."
  type        = string
}

variable "forgejo_container_bridge" {
  description = "Proxmox bridge for the Forgejo LXC interface. Set in terraform.tfvars."
  type        = string
}

variable "forgejo_container_vlan_id" {
  description = "Optional VLAN tag for the Forgejo LXC interface. Null leaves the interface untagged."
  type        = number
  default     = null

  validation {
    condition     = var.forgejo_container_vlan_id == null || (var.forgejo_container_vlan_id >= 1 && var.forgejo_container_vlan_id <= 4094)
    error_message = "forgejo_container_vlan_id must be null or a VLAN ID from 1 through 4094."
  }
}

variable "forgejo_container_cores" {
  description = "CPU cores for the Forgejo LXC."
  type        = number
}

variable "forgejo_container_memory_mb" {
  description = "Dedicated memory for the Forgejo LXC."
  type        = number
}

variable "forgejo_container_swap_mb" {
  description = "Swap for the Forgejo LXC."
  type        = number
}

variable "forgejo_container_disk_gb" {
  description = "Root filesystem size in GB for the Forgejo LXC."
  type        = number
}

variable "forgejo_data_dataset" {
  description = "ZFS dataset that backs Forgejo data. Ansible storage prep creates it idempotently on the Proxmox host before OpenTofu apply."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.:-]+(/[A-Za-z0-9_.:-]+)+$", var.forgejo_data_dataset))
    error_message = "forgejo_data_dataset must be a ZFS dataset path containing only letters, numbers, dot, underscore, colon, dash, and slash."
  }
}

variable "forgejo_data_host_path" {
  description = "Proxmox host path bind-mounted into the Forgejo LXC."
  type        = string

  validation {
    condition     = can(regex("^/[A-Za-z0-9_./:-]+$", var.forgejo_data_host_path))
    error_message = "forgejo_data_host_path must be an absolute path without whitespace or shell metacharacters."
  }
}

variable "forgejo_data_mount_path" {
  description = "Mount path inside the Forgejo LXC."
  type        = string
  default     = "/var/lib/forgejo"
}

variable "forgejo_data_host_uid" {
  description = "Host UID owner for the Forgejo bind mount. 100000 maps to root inside the default unprivileged LXC."
  type        = number
  default     = 100000
}

variable "forgejo_data_host_gid" {
  description = "Host GID owner for the Forgejo bind mount. 100000 maps to root inside the default unprivileged LXC."
  type        = number
  default     = 100000
}

variable "forgejo_startup_order" {
  description = "Proxmox startup order for the Forgejo LXC."
  type        = string
  default     = "2"
}

variable "forgejo_startup_up_delay" {
  description = "Seconds to wait after starting the Forgejo LXC before starting the next guest."
  type        = string
  default     = "20"
}

variable "forgejo_startup_down_delay" {
  description = "Seconds to wait after shutting down the Forgejo LXC before shutting down the next guest."
  type        = string
  default     = "20"
}

variable "forgejo_runner_vmid" {
  description = "Proxmox VMID for the Forgejo Actions runner LXC."
  type        = number
  default     = 109
}

variable "forgejo_runner_hostname" {
  description = "Hostname for the Forgejo Actions runner LXC."
  type        = string
  default     = "forgejo-runner"
}

variable "forgejo_runner_description" {
  description = "Description for the Forgejo Actions runner LXC."
  type        = string
  default     = "Forgejo Actions runner managed by OpenTofu."
}

variable "forgejo_runner_ipv4_address" {
  description = "IPv4 address/CIDR for the Forgejo Actions runner LXC, or dhcp when the router supplies a static DHCP reservation."
  type        = string
  default     = "dhcp"

  validation {
    condition     = var.forgejo_runner_ipv4_address == "dhcp" || can(cidrhost(var.forgejo_runner_ipv4_address, 0))
    error_message = "forgejo_runner_ipv4_address must be dhcp or a valid IPv4 CIDR address."
  }
}

variable "forgejo_runner_ipv4_gateway" {
  description = "IPv4 gateway for the Forgejo Actions runner LXC. Use null when forgejo_runner_ipv4_address is dhcp."
  type        = string
  default     = null
}

variable "forgejo_runner_mac_address" {
  description = "MAC address for the Forgejo Actions runner LXC, useful when the router supplies a static DHCP reservation."
  type        = string
  default     = "BC:24:11:00:00:02"

  validation {
    condition     = can(regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", var.forgejo_runner_mac_address))
    error_message = "forgejo_runner_mac_address must use colon-separated hex octets, for example BC:24:11:00:00:02."
  }
}

variable "forgejo_runner_dns_servers" {
  description = "DNS servers used by the Forgejo Actions runner LXC."
  type        = list(string)
  default     = ["1.1.1.1", "9.9.9.9"]
}

variable "forgejo_runner_search_domain" {
  description = "DNS search domain for the Forgejo Actions runner LXC."
  type        = string
  default     = "example.internal"
}

variable "forgejo_runner_bridge" {
  description = "Proxmox bridge for the Forgejo Actions runner LXC interface."
  type        = string
  default     = "vmbr0"
}

variable "forgejo_runner_vlan_id" {
  description = "Optional VLAN tag for the Forgejo Actions runner LXC interface. Null leaves the interface untagged."
  type        = number
  default     = null

  validation {
    condition     = var.forgejo_runner_vlan_id == null || (var.forgejo_runner_vlan_id >= 1 && var.forgejo_runner_vlan_id <= 4094)
    error_message = "forgejo_runner_vlan_id must be null or a VLAN ID from 1 through 4094."
  }
}

variable "forgejo_runner_cores" {
  description = "CPU cores for the Forgejo Actions runner LXC."
  type        = number
  default     = 2
}

variable "forgejo_runner_memory_mb" {
  description = "Dedicated memory for the Forgejo Actions runner LXC."
  type        = number
  default     = 2048
}

variable "forgejo_runner_swap_mb" {
  description = "Swap for the Forgejo Actions runner LXC."
  type        = number
  default     = 512
}

variable "forgejo_runner_disk_gb" {
  description = "Root filesystem size in GB for the Forgejo Actions runner LXC."
  type        = number
  default     = 16
}

variable "forgejo_runner_started" {
  description = "Whether OpenTofu should start the Forgejo Actions runner LXC after creation."
  type        = bool
  default     = true
}

variable "forgejo_runner_start_on_boot" {
  description = "Whether Proxmox should start the Forgejo Actions runner LXC on host boot."
  type        = bool
  default     = true
}

variable "forgejo_runner_startup_order" {
  description = "Proxmox startup order for the Forgejo Actions runner LXC."
  type        = string
  default     = "4"
}

variable "forgejo_runner_startup_up_delay" {
  description = "Seconds to wait after starting the Forgejo Actions runner LXC before starting the next guest."
  type        = string
  default     = "10"
}

variable "forgejo_runner_startup_down_delay" {
  description = "Seconds to wait after shutting down the Forgejo Actions runner LXC before shutting down the next guest."
  type        = string
  default     = "10"
}

variable "infisical_container_vmid" {
  description = "Proxmox VMID for the Infisical LXC."
  type        = number
  default     = 110
}

variable "infisical_container_hostname" {
  description = "Hostname for the Infisical LXC."
  type        = string
  default     = "infisical"
}

variable "infisical_container_description" {
  description = "Description for the Infisical LXC."
  type        = string
  default     = "Infisical secrets service managed by OpenTofu."
}

variable "infisical_container_ipv4_address" {
  description = "IPv4 address/CIDR for the Infisical LXC, or dhcp when the router supplies a static DHCP reservation."
  type        = string
  default     = "dhcp"

  validation {
    condition     = var.infisical_container_ipv4_address == "dhcp" || can(cidrhost(var.infisical_container_ipv4_address, 0))
    error_message = "infisical_container_ipv4_address must be dhcp or a valid IPv4 CIDR address."
  }
}

variable "infisical_container_ipv4_gateway" {
  description = "IPv4 gateway for the Infisical LXC. Use null when infisical_container_ipv4_address is dhcp."
  type        = string
  default     = null
}

variable "infisical_container_mac_address" {
  description = "MAC address for the Infisical LXC, useful when the router supplies a static DHCP reservation."
  type        = string
  default     = "BC:24:11:00:00:03"

  validation {
    condition     = can(regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", var.infisical_container_mac_address))
    error_message = "infisical_container_mac_address must use colon-separated hex octets, for example BC:24:11:00:00:03."
  }
}

variable "infisical_lan_ip" {
  description = "Expected LAN IP for Infisical, without CIDR. Used for outputs and DNS documentation when the LXC uses DHCP reservation."
  type        = string
  default     = "192.0.2.70"
}

variable "infisical_server_name" {
  description = "DNS hostname users should use for Infisical."
  type        = string
  default     = "infisical.example.internal"
}

variable "infisical_container_dns_servers" {
  description = "DNS servers used by the Infisical LXC."
  type        = list(string)
  default     = ["192.0.2.1"]
}

variable "infisical_container_search_domain" {
  description = "DNS search domain for the Infisical LXC."
  type        = string
  default     = "example.internal"
}

variable "infisical_container_bridge" {
  description = "Proxmox bridge for the Infisical LXC interface."
  type        = string
  default     = "vmbr0"
}

variable "infisical_container_vlan_id" {
  description = "Optional VLAN tag for the Infisical LXC interface. Null leaves the interface untagged."
  type        = number
  default     = null

  validation {
    condition     = var.infisical_container_vlan_id == null || (var.infisical_container_vlan_id >= 1 && var.infisical_container_vlan_id <= 4094)
    error_message = "infisical_container_vlan_id must be null or a VLAN ID from 1 through 4094."
  }
}

variable "infisical_container_cores" {
  description = "CPU cores for the Infisical LXC."
  type        = number
  default     = 2
}

variable "infisical_container_memory_mb" {
  description = "Dedicated memory for the Infisical LXC."
  type        = number
  default     = 4096
}

variable "infisical_container_swap_mb" {
  description = "Swap for the Infisical LXC."
  type        = number
  default     = 1024
}

variable "infisical_container_disk_gb" {
  description = "Root filesystem size in GB for the Infisical LXC."
  type        = number
  default     = 20
}

variable "infisical_started" {
  description = "Whether OpenTofu should start the Infisical LXC after creation."
  type        = bool
  default     = true
}

variable "infisical_start_on_boot" {
  description = "Whether Proxmox should start the Infisical LXC on host boot."
  type        = bool
  default     = true
}

variable "infisical_startup_order" {
  description = "Proxmox startup order for the Infisical LXC."
  type        = string
  default     = "5"
}

variable "infisical_startup_up_delay" {
  description = "Seconds to wait after starting the Infisical LXC before starting the next guest."
  type        = string
  default     = "20"
}

variable "infisical_startup_down_delay" {
  description = "Seconds to wait after shutting down the Infisical LXC before shutting down the next guest."
  type        = string
  default     = "20"
}

variable "hermes_container_vmid" {
  description = "Proxmox VMID for the Hermes management LXC."
  type        = number
  default     = 111
}

variable "hermes_container_hostname" {
  description = "Hostname for the Hermes management LXC."
  type        = string
  default     = "hermes"
}

variable "hermes_container_description" {
  description = "Description for the Hermes management LXC."
  type        = string
  default     = "Hermes management LXC managed by OpenTofu."
}

variable "hermes_container_ipv4_address" {
  description = "IPv4 address/CIDR for the Hermes LXC, or dhcp when the router supplies a static DHCP reservation."
  type        = string
  default     = "dhcp"

  validation {
    condition     = var.hermes_container_ipv4_address == "dhcp" || can(cidrhost(var.hermes_container_ipv4_address, 0))
    error_message = "hermes_container_ipv4_address must be dhcp or a valid IPv4 CIDR address."
  }
}

variable "hermes_container_ipv4_gateway" {
  description = "IPv4 gateway for the Hermes LXC. Use null when hermes_container_ipv4_address is dhcp."
  type        = string
  default     = null
}

variable "hermes_container_mac_address" {
  description = "MAC address for the Hermes LXC, useful when the router supplies a static DHCP reservation."
  type        = string
  default     = "BC:24:11:00:00:04"

  validation {
    condition     = can(regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", var.hermes_container_mac_address))
    error_message = "hermes_container_mac_address must use colon-separated hex octets, for example BC:24:11:00:00:04."
  }
}

variable "hermes_lan_ip" {
  description = "Expected LAN IP for Hermes, without CIDR. Used for outputs and DNS documentation when the LXC uses DHCP reservation."
  type        = string
  default     = "192.0.2.71"
}

variable "hermes_server_name" {
  description = "DNS hostname users should use for Hermes."
  type        = string
  default     = "hermes.example.internal"
}

variable "hermes_container_dns_servers" {
  description = "DNS servers used by the Hermes LXC."
  type        = list(string)
  default     = ["192.0.2.1"]
}

variable "hermes_container_search_domain" {
  description = "DNS search domain for the Hermes LXC."
  type        = string
  default     = "example.internal"
}

variable "hermes_container_bridge" {
  description = "Proxmox bridge for the Hermes LXC interface."
  type        = string
  default     = "vmbr0"
}

variable "hermes_container_vlan_id" {
  description = "Optional VLAN tag for the Hermes LXC interface. Null leaves the interface untagged."
  type        = number
  default     = null

  validation {
    condition     = var.hermes_container_vlan_id == null || (var.hermes_container_vlan_id >= 1 && var.hermes_container_vlan_id <= 4094)
    error_message = "hermes_container_vlan_id must be null or a VLAN ID from 1 through 4094."
  }
}

variable "hermes_container_cores" {
  description = "CPU cores for the Hermes LXC."
  type        = number
  default     = 2
}

variable "hermes_container_memory_mb" {
  description = "Dedicated memory for the Hermes LXC."
  type        = number
  default     = 2048
}

variable "hermes_container_swap_mb" {
  description = "Swap for the Hermes LXC."
  type        = number
  default     = 512
}

variable "hermes_container_disk_gb" {
  description = "Root filesystem size in GB for the Hermes LXC."
  type        = number
  default     = 64
}

variable "hermes_started" {
  description = "Whether OpenTofu should start the Hermes LXC after creation."
  type        = bool
  default     = true
}

variable "hermes_runtime_user" {
  description = "Non-root Hermes runtime/operator user managed by Ansible."
  type        = string
  default     = "anvil"

  validation {
    condition     = can(regex("^[a-z_][a-z0-9_-]{0,31}$", var.hermes_runtime_user)) && var.hermes_runtime_user != "root"
    error_message = "hermes_runtime_user must be a valid non-root Linux user name."
  }
}

variable "hermes_start_on_boot" {
  description = "Whether Proxmox should start the Hermes LXC on host boot."
  type        = bool
  default     = true
}

variable "hermes_startup_order" {
  description = "Proxmox startup order for the Hermes LXC."
  type        = string
  default     = "6"
}

variable "hermes_startup_up_delay" {
  description = "Seconds to wait after starting the Hermes LXC before starting the next guest."
  type        = string
  default     = "10"
}

variable "hermes_startup_down_delay" {
  description = "Seconds to wait after shutting down the Hermes LXC before shutting down the next guest."
  type        = string
  default     = "10"
}

variable "onramp_host_vmid" {
  description = "Proxmox VMID for the optional Debian 13 Podman onramp-host VM. Set in terraform.tfvars before enabling onramp_host."
  type        = number
  default     = 112

  validation {
    condition     = var.onramp_host_vmid > 0 && var.onramp_host_vmid < 1000000000
    error_message = "onramp_host_vmid must be a positive Proxmox VMID."
  }
}

variable "onramp_host_hostname" {
  description = "Hostname for the optional onramp-host VM."
  type        = string
  default     = "onramp-host"

  validation {
    condition     = can(regex("^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$", var.onramp_host_hostname))
    error_message = "onramp_host_hostname must be a valid single-label DNS hostname."
  }
}

variable "onramp_host_description" {
  description = "Description for the optional Debian 13 Podman onramp-host VM."
  type        = string
  default     = "Debian 13 Podman onramp host for Onramp-managed services."
}

variable "onramp_host_image_datastore_id" {
  description = "Proxmox datastore for the Debian 13 cloud image imported for onramp-host VM creation."
  type        = string
  default     = "local"
}

variable "onramp_host_image_url" {
  description = "Debian 13 genericcloud qcow2 image URL used to create a clean cloud-init onramp-host VM."
  type        = string
  default     = "https://cloud.debian.org/images/cloud/trixie/20260623-2518/debian-13-genericcloud-amd64-20260623-2518.qcow2"

  validation {
    condition     = can(regex("^https://", var.onramp_host_image_url))
    error_message = "onramp_host_image_url must be an HTTPS URL for a Debian 13 cloud image."
  }
}

variable "onramp_host_image_file_name" {
  description = "File name for the imported Debian 13 genericcloud qcow2 image."
  type        = string
  default     = "debian-13-genericcloud-amd64-20260623-2518.qcow2"

  validation {
    condition     = can(regex("^[A-Za-z0-9._-]+\\.qcow2$", var.onramp_host_image_file_name))
    error_message = "onramp_host_image_file_name must be a qcow2 file name."
  }
}

variable "onramp_host_image_checksum_algorithm" {
  description = "Checksum algorithm for the imported onramp-host cloud image."
  type        = string
  default     = "sha512"

  validation {
    condition     = contains(["md5", "sha1", "sha224", "sha256", "sha384", "sha512"], var.onramp_host_image_checksum_algorithm)
    error_message = "onramp_host_image_checksum_algorithm must be a provider-supported digest algorithm."
  }
}

variable "onramp_host_image_checksum" {
  description = "Lowercase hexadecimal checksum for the imported onramp-host cloud image."
  type        = string
  default     = "df2bd468b08566c0409a7982d6489d73499ad22f9a28646b538c2f21d08f15040a5e4737952ca209e9ad4488cd00793191791be9f135dee93082c86fcca3300c"

  validation {
    condition = (
      can(regex("^[0-9a-f]+$", var.onramp_host_image_checksum)) &&
      length(var.onramp_host_image_checksum) == lookup({
        md5 = 32, sha1 = 40, sha224 = 56, sha256 = 64, sha384 = 96, sha512 = 128
      }, var.onramp_host_image_checksum_algorithm, -1)
    )
    error_message = "onramp_host_image_checksum must match the selected algorithm as lowercase hexadecimal."
  }
}

variable "onramp_host_datastore_id" {
  description = "Datastore for the onramp-host VM disk and cloud-init drive."
  type        = string
  default     = "local-lvm"
}

variable "onramp_host_ipv4_address" {
  description = "Static IPv4 address/CIDR for the onramp-host VM. Use an address outside DHCP scope."
  type        = string
  default     = "192.0.2.72/24"

  validation {
    condition     = can(cidrhost(var.onramp_host_ipv4_address, 0))
    error_message = "onramp_host_ipv4_address must be a valid IPv4 CIDR address, for example 192.0.2.72/24."
  }
}

variable "onramp_host_ipv4_gateway" {
  description = "IPv4 gateway for the onramp-host VM."
  type        = string
  default     = "192.0.2.1"
}

variable "onramp_host_dns_servers" {
  description = "DNS servers used by the onramp-host VM."
  type        = list(string)
  default     = ["192.0.2.1"]
}

variable "onramp_host_search_domain" {
  description = "DNS search domain for the onramp-host VM."
  type        = string
  default     = "example.internal"
}

variable "onramp_host_bridge" {
  description = "Proxmox bridge for the onramp-host VM interface."
  type        = string
  default     = "vmbr0"
}

variable "onramp_host_vlan_id" {
  description = "Optional VLAN tag for the onramp-host VM interface. Null leaves the interface untagged."
  type        = number
  default     = null

  validation {
    condition     = var.onramp_host_vlan_id == null || (var.onramp_host_vlan_id >= 1 && var.onramp_host_vlan_id <= 4094)
    error_message = "onramp_host_vlan_id must be null or a VLAN ID from 1 through 4094."
  }
}

variable "onramp_host_cores" {
  description = "CPU cores for the onramp-host VM."
  type        = number
  default     = 2
}

variable "onramp_host_memory_mb" {
  description = "Dedicated memory for the onramp-host VM."
  type        = number
  default     = 4096
}

variable "onramp_host_disk_gb" {
  description = "Root disk size in GB for the onramp-host VM."
  type        = number
  default     = 32
}

variable "onramp_host_cloud_init_user" {
  description = "Initial non-root cloud-init user for SSH/bootstrap on the onramp-host VM."
  type        = string
  default     = "anvil"

  validation {
    condition     = can(regex("^[a-z_][a-z0-9_-]{0,31}$", var.onramp_host_cloud_init_user))
    error_message = "onramp_host_cloud_init_user must be a valid Linux user name."
  }
}

variable "onramp_host_ssh_public_keys" {
  description = "SSH public keys authorized for the onramp-host cloud-init user. Store real keys in private values. Falls back to lxc_ssh_public_keys when empty."
  type        = list(string)
  default     = []
}

variable "onramp_host_password_authentication" {
  description = "Whether SSH password authentication should remain enabled on the onramp-host. Keep false by default."
  type        = bool
  default     = false
}

variable "onramp_host_permit_root_login" {
  description = "Whether SSH root login should remain enabled on the onramp-host. Keep false by default."
  type        = bool
  default     = false
}

variable "onramp_host_deploy_user" {
  description = "Non-root user Onramp should use for app deployment on the onramp-host VM."
  type        = string
  default     = "anvil"

  validation {
    condition     = can(regex("^[a-z_][a-z0-9_-]{0,31}$", var.onramp_host_deploy_user))
    error_message = "onramp_host_deploy_user must be a valid Linux user name."
  }
}

variable "onramp_host_deploy_dir" {
  description = "Non-secret deployment directory owned by onramp_host_deploy_user for Onramp-managed services."
  type        = string
  default     = "/srv/onramp"

  validation {
    condition     = can(regex("^/[A-Za-z0-9_./:-]+$", var.onramp_host_deploy_dir))
    error_message = "onramp_host_deploy_dir must be an absolute path without whitespace or shell metacharacters."
  }
}

variable "onramp_host_allow_passwordless_sudo" {
  description = "Allow the onramp-host deploy user minimal passwordless sudo for Podman/user-service readiness operations."
  type        = bool
  default     = true
}

variable "onramp_host_allowed_ssh_cidrs" {
  description = "Private source CIDRs allowed to reach onramp-host SSH when host firewall is enabled. Use placeholders in tracked scaffold."
  type        = list(string)
  default     = ["192.0.2.0/24"]

  validation {
    condition     = alltrue([for cidr in var.onramp_host_allowed_ssh_cidrs : can(cidrhost(cidr, 0))])
    error_message = "onramp_host_allowed_ssh_cidrs must contain valid IPv4 CIDR ranges."
  }
}

variable "onramp_host_started" {
  description = "Whether OpenTofu should start the onramp-host VM after creation."
  type        = bool
  default     = true
}

variable "onramp_host_start_on_boot" {
  description = "Whether Proxmox should start the onramp-host VM on host boot."
  type        = bool
  default     = true
}

variable "onramp_host_startup_order" {
  description = "Proxmox startup order for the onramp-host VM."
  type        = string
  default     = "7"
}

variable "onramp_host_startup_up_delay" {
  description = "Seconds to wait after starting the onramp-host VM before starting the next guest."
  type        = string
  default     = "20"
}

variable "onramp_host_startup_down_delay" {
  description = "Seconds to wait after shutting down the onramp-host VM before shutting down the next guest."
  type        = string
  default     = "20"
}

variable "tailscale_client_enabled" {
  description = "Create the Tailscale client LXC. Keep false for backup-only documentation until a reviewed plan should create it."
  type        = bool
  default     = false
}

variable "tailscale_client_vmid" {
  description = "Proxmox VMID for the Tailscale client LXC. Set in terraform.tfvars before enabling tailscale_client_enabled."
  type        = number
  default     = 108
}

variable "tailscale_client_hostname" {
  description = "Hostname for the Tailscale client LXC."
  type        = string
  default     = "tailscale-client"
}

variable "tailscale_client_description" {
  description = "Description for the Tailscale client LXC."
  type        = string
  default     = "Tailscale client LXC managed by OpenTofu."
}

variable "tailscale_client_ipv4_address" {
  description = "IPv4 address/CIDR for the Tailscale client LXC, or dhcp when the router supplies a static DHCP reservation."
  type        = string
  default     = "dhcp"

  validation {
    condition     = var.tailscale_client_ipv4_address == "dhcp" || can(cidrhost(var.tailscale_client_ipv4_address, 0))
    error_message = "tailscale_client_ipv4_address must be dhcp or a valid IPv4 CIDR address."
  }
}

variable "tailscale_client_ipv4_gateway" {
  description = "IPv4 gateway for the Tailscale client LXC. Use null when tailscale_client_ipv4_address is dhcp."
  type        = string
  default     = null
}

variable "tailscale_client_mac_address" {
  description = "MAC address for the Tailscale client LXC, useful when the router supplies a static DHCP reservation."
  type        = string
  default     = "BC:24:11:00:00:01"

  validation {
    condition     = can(regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", var.tailscale_client_mac_address))
    error_message = "tailscale_client_mac_address must use colon-separated hex octets, for example BC:24:11:00:00:01."
  }
}

variable "tailscale_client_dns_servers" {
  description = "DNS servers used by the Tailscale client LXC before Tailscale DNS is configured."
  type        = list(string)
  default     = ["1.1.1.1", "9.9.9.9"]
}

variable "tailscale_client_search_domain" {
  description = "DNS search domain for the Tailscale client LXC."
  type        = string
  default     = "example.internal"
}

variable "tailscale_client_bridge" {
  description = "Proxmox bridge for the Tailscale client LXC interface."
  type        = string
  default     = "vmbr0"
}

variable "tailscale_client_vlan_id" {
  description = "Optional VLAN tag for the Tailscale client LXC interface. Null leaves the interface untagged."
  type        = number
  default     = null

  validation {
    condition     = var.tailscale_client_vlan_id == null || (var.tailscale_client_vlan_id >= 1 && var.tailscale_client_vlan_id <= 4094)
    error_message = "tailscale_client_vlan_id must be null or a VLAN ID from 1 through 4094."
  }
}

variable "tailscale_client_cores" {
  description = "CPU cores for the Tailscale client LXC."
  type        = number
  default     = 1
}

variable "tailscale_client_memory_mb" {
  description = "Dedicated memory for the Tailscale client LXC."
  type        = number
  default     = 512
}

variable "tailscale_client_swap_mb" {
  description = "Swap for the Tailscale client LXC."
  type        = number
  default     = 256
}

variable "tailscale_client_disk_gb" {
  description = "Root filesystem size in GB for the Tailscale client LXC."
  type        = number
  default     = 4
}

variable "tailscale_client_started" {
  description = "Whether OpenTofu should start the Tailscale client LXC after creation."
  type        = bool
  default     = true
}

variable "tailscale_client_start_on_boot" {
  description = "Whether Proxmox should start the Tailscale client LXC on host boot."
  type        = bool
  default     = true
}

variable "tailscale_client_startup_order" {
  description = "Proxmox startup order for the Tailscale client LXC."
  type        = string
  default     = "3"
}

variable "tailscale_client_startup_up_delay" {
  description = "Seconds to wait after starting the Tailscale client LXC before starting the next guest."
  type        = string
  default     = "10"
}

variable "tailscale_client_startup_down_delay" {
  description = "Seconds to wait after shutting down the Tailscale client LXC before shutting down the next guest."
  type        = string
  default     = "10"
}

# Consumed by Ansible dynamic inventory rather than OpenTofu resources.
# tflint-ignore: terraform_unused_declarations
variable "searxng_server_name" {
  description = "DNS hostname for the temporary SearXNG onramp workload. Ansible/DNS consume this value."
  type        = string
  default     = "searxng.apps.example.net"
}

# Consumed by Ansible dynamic inventory rather than OpenTofu resources.
# tflint-ignore: terraform_unused_declarations
variable "searxng_public_url" {
  description = "Public HTTPS URL for the temporary SearXNG onramp workload. Hermes can consume this value."
  type        = string
  default     = "https://searxng.apps.example.net"
}

# Consumed by Ansible dynamic inventory rather than OpenTofu resources.
# tflint-ignore: terraform_unused_declarations
variable "searxng_container_image" {
  description = "Digest-pinned SearXNG OCI image used by the onramp workload."
  type        = string
  default     = "docker.io/searxng/searxng:2026.7.2-67973783d@sha256:33aa33278be6c0be379b95f7c91cd455c18141295291c2e5a396454761df7bbb"

  validation {
    condition     = can(regex("^docker\\.io/searxng/searxng:2026\\.7\\.2-[0-9a-f]+@sha256:[0-9a-f]{64}$", var.searxng_container_image))
    error_message = "searxng_container_image must be a digest-pinned 2026.7.2 SearXNG image."
  }
}

# Consumed by Ansible dynamic inventory rather than OpenTofu resources.
# tflint-ignore: terraform_unused_declarations
variable "searxng_container_port" {
  description = "Loopback port exposed by the rootless SearXNG container for Caddy."
  type        = number
  default     = 8080
}

# Consumed by Ansible dynamic inventory rather than OpenTofu resources.
# tflint-ignore: terraform_unused_declarations
variable "searxng_bind_address" {
  description = "Host address that receives the rootless SearXNG container port. Keep this loopback-only."
  type        = string
  default     = "127.0.0.1"
}

# Consumed by Ansible dynamic inventory rather than OpenTofu resources.
# tflint-ignore: terraform_unused_declarations
variable "searxng_instance_name" {
  description = "Display name for the SearXNG instance."
  type        = string
  default     = "Homelab SearXNG"
}

# Consumed by Ansible dynamic inventory rather than OpenTofu resources.
# tflint-ignore: terraform_unused_declarations
variable "searxng_enable_public_url" {
  description = "Whether SearXNG should advertise searxng_public_url in its settings."
  type        = bool
  default     = true
}
