resource "proxmox_virtual_environment_container" "forgejo_runner" {
  count = local.forgejo_runner_enabled ? 1 : 0

  description   = var.forgejo_runner_description
  node_name     = var.proxmox_node_name
  vm_id         = var.forgejo_runner_vmid
  unprivileged  = true
  started       = var.forgejo_runner_started
  start_on_boot = var.forgejo_runner_start_on_boot
  tags          = ["forgejo", "runner", "actions", "opentofu"]

  cpu {
    cores = var.forgejo_runner_cores
  }

  memory {
    dedicated = var.forgejo_runner_memory_mb
    swap      = var.forgejo_runner_swap_mb
  }

  features {
    nesting = true
  }

  disk {
    datastore_id = var.rootfs_datastore_id
    size         = var.forgejo_runner_disk_gb
  }

  initialization {
    hostname = var.forgejo_runner_hostname

    dns {
      domain  = var.forgejo_runner_search_domain
      servers = var.forgejo_runner_dns_servers
    }

    ip_config {
      ipv4 {
        address = var.forgejo_runner_ipv4_address
        gateway = var.forgejo_runner_ipv4_gateway
      }
    }

    user_account {
      password = var.lxc_root_password
      keys     = var.lxc_ssh_public_keys
    }
  }

  network_interface {
    name        = "eth0"
    bridge      = var.forgejo_runner_bridge
    mac_address = var.forgejo_runner_mac_address
    vlan_id     = var.forgejo_runner_vlan_id
  }

  operating_system {
    template_file_id = proxmox_download_file.debian_12_lxc_template[0].id
    type             = "debian"
  }

  startup {
    order      = var.forgejo_runner_startup_order
    up_delay   = var.forgejo_runner_startup_up_delay
    down_delay = var.forgejo_runner_startup_down_delay
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
