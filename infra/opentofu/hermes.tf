resource "proxmox_virtual_environment_container" "hermes" {
  count = local.hermes_enabled ? 1 : 0

  description   = var.hermes_container_description
  node_name     = var.proxmox_node_name
  vm_id         = var.hermes_container_vmid
  unprivileged  = true
  started       = var.hermes_started
  start_on_boot = var.hermes_start_on_boot
  tags          = ["hermes", "management", "opentofu"]

  cpu {
    cores = var.hermes_container_cores
  }

  memory {
    dedicated = var.hermes_container_memory_mb
    swap      = var.hermes_container_swap_mb
  }

  features {
    nesting = true
  }

  disk {
    datastore_id = var.rootfs_datastore_id
    size         = var.hermes_container_disk_gb
  }

  initialization {
    hostname = var.hermes_container_hostname

    dns {
      domain  = var.hermes_container_search_domain
      servers = var.hermes_container_dns_servers
    }

    ip_config {
      ipv4 {
        address = var.hermes_container_ipv4_address
        gateway = var.hermes_container_ipv4_gateway
      }
    }

    user_account {
      password = var.lxc_root_password
      keys     = var.lxc_ssh_public_keys
    }
  }

  network_interface {
    name        = "eth0"
    bridge      = var.hermes_container_bridge
    mac_address = var.hermes_container_mac_address
    vlan_id     = var.hermes_container_vlan_id
  }

  operating_system {
    template_file_id = proxmox_download_file.debian_12_lxc_template[0].id
    type             = "debian"
  }

  startup {
    order      = var.hermes_startup_order
    up_delay   = var.hermes_startup_up_delay
    down_delay = var.hermes_startup_down_delay
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
