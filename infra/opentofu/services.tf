locals {
  service_registry         = jsondecode(file("${path.module}/../services.json"))
  service_names            = keys(local.service_registry.services)
  enabled_services         = toset(coalesce(var.enabled_services, local.service_registry.default_services))
  invalid_enabled_services = setsubtract(local.enabled_services, toset(local.service_names))

  technitium_enabled           = contains(local.enabled_services, "technitium")
  technitium_secondary_enabled = contains(local.service_names, "technitium_secondary") && contains(local.enabled_services, "technitium_secondary")
  forgejo_enabled              = contains(local.enabled_services, "forgejo")
  tailscale_client_enabled     = contains(local.enabled_services, "tailscale_client") && var.tailscale_client_enabled
  forgejo_runner_enabled       = contains(local.enabled_services, "forgejo_runner")
  infisical_enabled            = contains(local.enabled_services, "infisical")
  hermes_enabled               = contains(local.enabled_services, "hermes")
  onramp_host_enabled          = contains(local.enabled_services, "onramp_host")

  lxc_template_enabled = local.technitium_enabled || local.forgejo_enabled || local.tailscale_client_enabled || local.forgejo_runner_enabled || local.infisical_enabled || local.hermes_enabled
}

resource "terraform_data" "enabled_services_validation" {
  input = local.enabled_services

  lifecycle {
    precondition {
      condition     = length(local.invalid_enabled_services) == 0
      error_message = "enabled_services may contain only ${join(", ", local.service_names)}."
    }
  }
}

moved {
  from = proxmox_download_file.debian_12_lxc_template[0]
  to   = proxmox_download_file.debian_13_lxc_template[0]
}

moved {
  from = proxmox_virtual_environment_container.technitium_dns
  to   = proxmox_virtual_environment_container.technitium_dns[0]
}

moved {
  from = proxmox_virtual_environment_container.forgejo
  to   = proxmox_virtual_environment_container.forgejo[0]
}

moved {
  from = proxmox_virtual_environment_container.technitium_dns[0]
  to   = module.technitium_dns[0].proxmox_virtual_environment_container.this
}

moved {
  from = proxmox_virtual_environment_container.forgejo[0]
  to   = module.forgejo[0].proxmox_virtual_environment_container.this
}

moved {
  from = proxmox_virtual_environment_container.tailscale_client[0]
  to   = module.tailscale_client[0].proxmox_virtual_environment_container.this
}

moved {
  from = proxmox_virtual_environment_container.forgejo_runner[0]
  to   = module.forgejo_runner[0].proxmox_virtual_environment_container.this
}

moved {
  from = proxmox_virtual_environment_container.infisical[0]
  to   = module.infisical[0].proxmox_virtual_environment_container.this
}

moved {
  from = proxmox_virtual_environment_container.hermes[0]
  to   = module.hermes[0].proxmox_virtual_environment_container.this
}
