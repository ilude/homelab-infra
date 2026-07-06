resource "proxmox_virtual_environment_container" "infisical" {
  count = local.infisical_enabled ? 1 : 0

  description   = var.infisical_container_description
  node_name     = var.proxmox_node_name
  vm_id         = var.infisical_container_vmid
  unprivileged  = true
  started       = var.infisical_started
  start_on_boot = var.infisical_start_on_boot
  tags          = ["infisical", "secrets", "opentofu"]

  cpu {
    cores = var.infisical_container_cores
  }

  memory {
    dedicated = var.infisical_container_memory_mb
    swap      = var.infisical_container_swap_mb
  }

  features {
    nesting = true
  }

  disk {
    datastore_id = var.rootfs_datastore_id
    size         = var.infisical_container_disk_gb
  }

  initialization {
    hostname = var.infisical_container_hostname

    dns {
      domain  = var.infisical_container_search_domain
      servers = var.infisical_container_dns_servers
    }

    ip_config {
      ipv4 {
        address = var.infisical_container_ipv4_address
        gateway = var.infisical_container_ipv4_gateway
      }
    }

    user_account {
      password = var.lxc_root_password
      keys     = var.lxc_ssh_public_keys
    }
  }

  network_interface {
    name        = "eth0"
    bridge      = var.infisical_container_bridge
    mac_address = var.infisical_container_mac_address
  }

  operating_system {
    template_file_id = proxmox_download_file.debian_12_lxc_template[0].id
    type             = "debian"
  }

  startup {
    order      = var.infisical_startup_order
    up_delay   = var.infisical_startup_up_delay
    down_delay = var.infisical_startup_down_delay
  }

  wait_for_ip {
    ipv4 = true
  }

  lifecycle {
    ignore_changes = [
      initialization[0].user_account,
      operating_system[0].template_file_id,
    ]
  }
}
