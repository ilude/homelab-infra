resource "proxmox_virtual_environment_container" "tailscale_client" {
  count = local.tailscale_client_enabled ? 1 : 0

  description   = var.tailscale_client_description
  node_name     = var.proxmox_node_name
  vm_id         = var.tailscale_client_vmid
  unprivileged  = true
  started       = var.tailscale_client_started
  start_on_boot = var.tailscale_client_start_on_boot
  tags          = ["tailscale", "vpn", "opentofu"]

  cpu {
    cores = var.tailscale_client_cores
  }

  memory {
    dedicated = var.tailscale_client_memory_mb
    swap      = var.tailscale_client_swap_mb
  }

  features {
    keyctl  = true
    nesting = true
  }

  device_passthrough {
    path = "/dev/net/tun"
    mode = "0666"
  }

  disk {
    datastore_id = var.rootfs_datastore_id
    size         = var.tailscale_client_disk_gb
  }

  initialization {
    hostname = var.tailscale_client_hostname

    dns {
      domain  = var.tailscale_client_search_domain
      servers = var.tailscale_client_dns_servers
    }

    ip_config {
      ipv4 {
        address = var.tailscale_client_ipv4_address
        gateway = var.tailscale_client_ipv4_gateway
      }
    }

    user_account {
      password = var.lxc_root_password
      keys     = var.lxc_ssh_public_keys
    }
  }

  network_interface {
    name        = "eth0"
    bridge      = var.tailscale_client_bridge
    mac_address = var.tailscale_client_mac_address
    vlan_id     = var.tailscale_client_vlan_id
  }

  operating_system {
    template_file_id = proxmox_download_file.debian_12_lxc_template[0].id
    type             = "debian"
  }

  startup {
    order      = var.tailscale_client_startup_order
    up_delay   = var.tailscale_client_startup_up_delay
    down_delay = var.tailscale_client_startup_down_delay
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
