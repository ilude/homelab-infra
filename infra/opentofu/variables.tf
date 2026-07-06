variable "enabled_services" {
  description = "Services OpenTofu should build and maintain. Service selection is normally supplied from settings.local.json by just plan."
  type        = list(string)
  default     = ["technitium", "forgejo"]

  validation {
    condition = alltrue([
      for service in var.enabled_services : contains(["technitium", "forgejo", "tailscale_client", "forgejo_runner", "infisical", "hermes"], service)
    ])
    error_message = "enabled_services may contain only technitium, forgejo, tailscale_client, forgejo_runner, infisical, and hermes."
  }
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

variable "debian_template_url" {
  description = "Debian 12 standard LXC template URL. Set in terraform.tfvars."
  type        = string
}

variable "debian_template_file_name" {
  description = "File name for the downloaded Debian 12 LXC template. Set in terraform.tfvars."
  type        = string
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
