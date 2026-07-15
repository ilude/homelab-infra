provider "proxmox" {
  endpoint = var.proxmox_endpoint
  insecure = var.proxmox_insecure

  # Prefer environment variables or terraform.tfvars for credentials:
  #   PROXMOX_VE_API_TOKEN="terraform@pve!token=<secret>"
  # or:
  #   PROXMOX_VE_USERNAME="root@pam"
  #   PROXMOX_VE_PASSWORD="..."
  api_token = var.proxmox_api_token
  username  = var.proxmox_username
  password  = var.proxmox_password
}

provider "proxmox" {
  alias = "secondary"

  endpoint  = var.secondary_proxmox_endpoint
  insecure  = var.secondary_proxmox_insecure
  api_token = var.secondary_proxmox_api_token
}
