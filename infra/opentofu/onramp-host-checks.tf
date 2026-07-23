locals {
  service_vmids = compact([
    tostring(var.technitium_container_vmid),
    tostring(var.forgejo_container_vmid),
    tostring(var.forgejo_runner_vmid),
    tostring(var.infisical_container_vmid),
    tostring(var.hermes_container_vmid),
    tostring(var.tailscale_client_vmid),
    tostring(var.onramp_host_vmid),
  ])

  service_static_ipv4_addresses = compact([
    var.technitium_container_ipv4_address == "dhcp" ? null : split("/", var.technitium_container_ipv4_address)[0],
    var.forgejo_container_ipv4_address == "dhcp" ? null : split("/", var.forgejo_container_ipv4_address)[0],
    var.forgejo_runner_ipv4_address == "dhcp" ? null : split("/", var.forgejo_runner_ipv4_address)[0],
    var.infisical_container_ipv4_address == "dhcp" ? null : split("/", var.infisical_container_ipv4_address)[0],
    var.hermes_container_ipv4_address == "dhcp" ? null : split("/", var.hermes_container_ipv4_address)[0],
    var.tailscale_client_ipv4_address == "dhcp" ? null : split("/", var.tailscale_client_ipv4_address)[0],
    split("/", var.onramp_host_ipv4_address)[0],
  ])
}

check "unique_service_vmids" {
  assert {
    condition     = length(local.service_vmids) == length(toset(local.service_vmids))
    error_message = "Service VMIDs, including onramp_host_vmid, must be unique."
  }
}

check "unique_service_static_ipv4_addresses" {
  assert {
    condition     = length(local.service_static_ipv4_addresses) == length(toset(local.service_static_ipv4_addresses))
    error_message = "Static service IPv4 addresses, including onramp_host_ipv4_address, must be unique."
  }
}

check "onramp_host_hardening_policy" {
  assert {
    condition = (
      !var.onramp_host_password_authentication &&
      !var.onramp_host_permit_root_login &&
      contains([true, false], var.onramp_host_allow_passwordless_sudo) &&
      length(var.onramp_host_allowed_ssh_cidrs) > 0
    )
    error_message = "onramp_host must keep password SSH disabled, root SSH disabled, an explicit sudo policy decision, and at least one SSH source CIDR."
  }

  assert {
    condition = (
      var.onramp_host_var_lv_gb + var.onramp_host_srv_lv_gb <=
      var.onramp_host_data_disk_gb * (100 - var.onramp_host_vg_min_free_percent) / 100
    )
    error_message = "onramp_host guest LVs must leave the configured minimum free percentage on the data VG."
  }
}
