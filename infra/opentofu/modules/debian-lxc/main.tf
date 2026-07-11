resource "proxmox_virtual_environment_container" "this" {
  description   = var.description
  node_name     = var.node_name
  vm_id         = var.vm_id
  unprivileged  = true
  started       = var.started
  start_on_boot = var.start_on_boot
  tags          = var.tags

  cpu {
    cores = var.cores
  }

  memory {
    dedicated = var.memory_mb
    swap      = var.swap_mb
  }

  features {
    keyctl  = var.features.keyctl
    nesting = var.features.nesting
  }

  dynamic "device_passthrough" {
    for_each = var.device_passthrough

    content {
      path = device_passthrough.value.path
      mode = device_passthrough.value.mode
    }
  }

  disk {
    datastore_id = var.disk.datastore_id
    size         = var.disk.size_gb
  }

  initialization {
    hostname = var.hostname

    dns {
      domain  = var.search_domain
      servers = var.dns_servers
    }

    ip_config {
      ipv4 {
        address = var.ipv4_address
        gateway = var.ipv4_gateway
      }
    }

    user_account {
      password = var.root_password
      keys     = var.ssh_public_keys
    }
  }

  network_interface {
    name        = var.network.name
    bridge      = var.network.bridge
    mac_address = var.network.mac_address
    vlan_id     = var.network.vlan_id
  }

  operating_system {
    template_file_id = var.template_file_id
    type             = var.os_type
  }

  startup {
    order      = var.startup.order
    up_delay   = var.startup.up_delay
    down_delay = var.startup.down_delay
  }

  dynamic "wait_for_ip" {
    for_each = var.wait_for_ipv4 ? [true] : []

    content {
      ipv4 = wait_for_ip.value
    }
  }

  # Bind mounts are a Proxmox-host lifecycle concern. This module has no bind-mount
  # input; ignoring this field prevents the API provider from deleting
  # SSH/pct-managed recovery mounts during refresh or apply.
  lifecycle {
    ignore_changes = [
      initialization[0].user_account,
      mount_point,
    ]
  }
}
