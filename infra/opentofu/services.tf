locals {
  enabled_services = toset(var.enabled_services)

  technitium_enabled       = contains(local.enabled_services, "technitium")
  forgejo_enabled          = contains(local.enabled_services, "forgejo")
  tailscale_client_enabled = contains(local.enabled_services, "tailscale_client") && var.tailscale_client_enabled
  forgejo_runner_enabled   = contains(local.enabled_services, "forgejo_runner")
  infisical_enabled        = contains(local.enabled_services, "infisical")
  hermes_enabled           = contains(local.enabled_services, "hermes")

  lxc_template_enabled = local.technitium_enabled || local.forgejo_enabled || local.tailscale_client_enabled || local.forgejo_runner_enabled || local.infisical_enabled || local.hermes_enabled
}

moved {
  from = proxmox_download_file.debian_12_lxc_template
  to   = proxmox_download_file.debian_12_lxc_template[0]
}

moved {
  from = proxmox_virtual_environment_container.technitium_dns
  to   = proxmox_virtual_environment_container.technitium_dns[0]
}

moved {
  from = proxmox_virtual_environment_container.forgejo
  to   = proxmox_virtual_environment_container.forgejo[0]
}
