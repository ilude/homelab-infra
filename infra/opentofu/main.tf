resource "proxmox_download_file" "debian_12_lxc_template" {
  count = local.lxc_template_enabled ? 1 : 0

  content_type        = "vztmpl"
  datastore_id        = var.template_datastore_id
  file_name           = var.debian_template_file_name
  node_name           = var.proxmox_node_name
  url                 = var.debian_template_url
  overwrite           = false
  overwrite_unmanaged = false
}

resource "proxmox_virtual_environment_container" "technitium_dns" {
  count = local.technitium_enabled ? 1 : 0

  description   = var.technitium_container_description
  node_name     = var.proxmox_node_name
  vm_id         = var.technitium_container_vmid
  unprivileged  = true
  started       = true
  start_on_boot = true
  tags          = ["dns", "technitium", "opentofu"]

  cpu {
    cores = var.technitium_container_cores
  }

  memory {
    dedicated = var.technitium_container_memory_mb
    swap      = var.technitium_container_swap_mb
  }

  features {
    nesting = true
  }

  disk {
    datastore_id = var.rootfs_datastore_id
    size         = var.technitium_container_disk_gb
  }

  initialization {
    hostname = var.technitium_container_hostname

    dns {
      domain  = var.technitium_container_search_domain
      servers = var.technitium_container_dns_servers
    }

    ip_config {
      ipv4 {
        address = var.technitium_container_ipv4_address
        gateway = var.technitium_container_ipv4_gateway
      }
    }

    user_account {
      password = var.lxc_root_password
      keys     = var.lxc_ssh_public_keys
    }
  }

  network_interface {
    name    = "eth0"
    bridge  = var.technitium_container_bridge
    vlan_id = var.technitium_container_vlan_id
  }

  operating_system {
    template_file_id = proxmox_download_file.debian_12_lxc_template[0].id
    type             = "debian"
  }

  startup {
    order      = "1"
    up_delay   = "15"
    down_delay = "15"
  }

  wait_for_ip {
    ipv4 = true
  }
}
