variable "description" {
  description = "Human-readable description shown in the Proxmox UI."
  type        = string
}

variable "node_name" {
  description = "Proxmox node that hosts the LXC."
  type        = string
}

variable "vm_id" {
  description = "Proxmox VMID for the LXC."
  type        = number
}

variable "started" {
  description = "Whether the LXC should be started."
  type        = bool
  default     = true
}

variable "start_on_boot" {
  description = "Whether the LXC starts automatically when the Proxmox host boots."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Proxmox tags applied to the LXC."
  type        = list(string)
}

variable "cores" {
  description = "CPU cores allocated to the LXC."
  type        = number
}

variable "memory_mb" {
  description = "Dedicated memory in MiB."
  type        = number
}

variable "swap_mb" {
  description = "Swap in MiB."
  type        = number
}

variable "features" {
  description = "Container features. keyctl left null keeps the Proxmox default."
  type = object({
    keyctl  = optional(bool)
    nesting = optional(bool, true)
  })
  default = {}
}

variable "device_passthrough" {
  description = "Host devices passed through to the LXC."
  type = list(object({
    path = string
    mode = optional(string)
  }))
  default = []
}

variable "disk" {
  description = "Root filesystem disk settings."
  type = object({
    datastore_id = string
    size_gb      = number
  })
}

variable "hostname" {
  description = "Hostname assigned inside the LXC."
  type        = string
}

variable "search_domain" {
  description = "DNS search domain for the LXC."
  type        = string
}

variable "dns_servers" {
  description = "DNS servers used by the LXC."
  type        = list(string)
}

variable "ipv4_address" {
  description = "IPv4 address in CIDR notation, or dhcp."
  type        = string
}

variable "ipv4_gateway" {
  description = "IPv4 gateway for the LXC."
  type        = string
}

variable "root_password" {
  description = "Root password for the LXC."
  type        = string
  sensitive   = true
}

variable "ssh_public_keys" {
  description = "SSH public keys installed for root."
  type        = list(string)
}

variable "network" {
  description = "Network interface settings. mac_address left null keeps the Proxmox-generated MAC."
  type = object({
    name        = optional(string, "eth0")
    bridge      = string
    mac_address = optional(string)
    vlan_id     = optional(number)
  })
}

variable "template_file_id" {
  description = "Proxmox file ID of the OS template used to create the LXC."
  type        = string
}

variable "os_type" {
  description = "Operating system type reported to Proxmox."
  type        = string
  default     = "debian"
}

variable "startup" {
  description = "Proxmox startup order and delays."
  type = object({
    order      = string
    up_delay   = string
    down_delay = string
  })
}

variable "wait_for_ipv4" {
  description = "Whether to wait for an IPv4 address before considering the LXC created."
  type        = bool
  default     = true
}
