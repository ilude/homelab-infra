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

variable "technitium_api_url" {
  description = "Technitium DNS Server API URL. Set in terraform.tfvars."
  type        = string
}

variable "dns_records_file" {
  description = "Path to the local Technitium DNS records JSON file. The real file belongs in values/; see scaffold/dns-records.local.json."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_./-]+\\.json$", var.dns_records_file)) && !startswith(var.dns_records_file, "/")
    error_message = "dns_records_file must be a relative JSON path containing only letters, numbers, dot, slash, underscore, and dash."
  }
}

variable "technitium_api_token" {
  description = "Technitium API token. Prefer TECHNITIUM_API_TOKEN or terraform.tfvars/.env injection."
  type        = string
  default     = null
  sensitive   = true
}

variable "proxmox_node_name" {
  description = "Proxmox node where the Technitium LXC should run. Set in terraform.tfvars."
  type        = string
}

variable "container_vmid" {
  description = "Proxmox VMID for the Technitium DNS LXC. Set in terraform.tfvars."
  type        = number
}

variable "container_hostname" {
  description = "Hostname for the Technitium DNS LXC. Set in terraform.tfvars."
  type        = string
}

variable "container_description" {
  description = "Description for the Technitium DNS LXC. Set in terraform.tfvars if you want a site-specific label."
  type        = string
  default     = "Technitium DNS primary resolver managed by OpenTofu."
}

variable "container_ipv4_address" {
  description = "Static IPv4 address/CIDR for the Technitium DNS LXC. Use an address outside DHCP scope. Set in terraform.tfvars."
  type        = string

  validation {
    condition     = can(cidrhost(var.container_ipv4_address, 0))
    error_message = "container_ipv4_address must be a valid IPv4 CIDR address, for example 192.0.2.10/24."
  }
}

variable "container_ipv4_gateway" {
  description = "IPv4 gateway for the Technitium DNS LXC. Set in terraform.tfvars."
  type        = string
}

variable "container_dns_servers" {
  description = "DNS servers used by the LXC before it becomes the primary resolver. Set in terraform.tfvars."
  type        = list(string)
}

variable "container_search_domain" {
  description = "DNS search domain for the LXC. Set in terraform.tfvars."
  type        = string
}

variable "container_bridge" {
  description = "Proxmox bridge for the LXC interface. Set in terraform.tfvars."
  type        = string
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

variable "container_root_password" {
  description = "Initial root password for the LXC. Store only in terraform.tfvars or environment injection."
  type        = string
  sensitive   = true
}

variable "container_ssh_public_keys" {
  description = "SSH public keys to install for root in the LXC."
  type        = list(string)
  default     = []
}

variable "container_cores" {
  description = "CPU cores for the Technitium DNS LXC. Set in terraform.tfvars."
  type        = number
}

variable "container_memory_mb" {
  description = "Dedicated memory for the Technitium DNS LXC. Set in terraform.tfvars."
  type        = number
}

variable "container_swap_mb" {
  description = "Swap for the Technitium DNS LXC. Set in terraform.tfvars."
  type        = number
}

variable "container_disk_gb" {
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
  description = "ZFS dataset that backs Forgejo data. The local-exec provisioner creates it idempotently on PVE_HOST."
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
