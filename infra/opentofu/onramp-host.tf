resource "proxmox_download_file" "debian_13_onramp_host_image" {
  count = local.onramp_host_enabled ? 1 : 0

  checksum            = var.onramp_host_image_checksum
  checksum_algorithm  = var.onramp_host_image_checksum_algorithm
  content_type        = "import"
  datastore_id        = var.onramp_host_image_datastore_id
  file_name           = var.onramp_host_image_file_name
  node_name           = var.proxmox_node_name
  url                 = var.onramp_host_image_url
  overwrite           = false
  overwrite_unmanaged = false
}

resource "terraform_data" "onramp_host_rebuild" {
  count = local.onramp_host_enabled && var.onramp_host_rebuild_revision != "" ? 1 : 0

  triggers_replace = var.onramp_host_rebuild_revision
}

resource "proxmox_virtual_environment_vm" "onramp_host" {
  count = local.onramp_host_enabled ? 1 : 0

  name        = var.onramp_host_hostname
  description = var.onramp_host_description
  node_name   = var.proxmox_node_name
  vm_id       = var.onramp_host_vmid
  tags        = ["onramp-host", "debian", "podman", "opentofu"]

  started         = var.onramp_host_started
  on_boot         = var.onramp_host_start_on_boot
  stop_on_destroy = true

  agent {
    enabled = false
  }

  cpu {
    cores = var.onramp_host_cores
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = var.onramp_host_memory_mb
  }

  disk {
    datastore_id = var.onramp_host_datastore_id
    import_from  = proxmox_download_file.debian_13_onramp_host_image[0].id
    interface    = "scsi0"
    size         = var.onramp_host_disk_gb
  }

  disk {
    datastore_id = var.onramp_host_data_datastore_id
    interface    = "scsi1"
    size         = var.onramp_host_data_disk_gb
  }

  initialization {
    datastore_id = var.onramp_host_datastore_id

    dns {
      domain  = var.onramp_host_search_domain
      servers = var.onramp_host_dns_servers
    }

    ip_config {
      ipv4 {
        address = var.onramp_host_ipv4_address
        gateway = var.onramp_host_ipv4_gateway
      }
    }

    user_account {
      username = var.onramp_host_cloud_init_user
      keys     = length(var.onramp_host_ssh_public_keys) > 0 ? var.onramp_host_ssh_public_keys : var.lxc_ssh_public_keys
    }
  }

  network_device {
    bridge  = var.onramp_host_bridge
    vlan_id = var.onramp_host_vlan_id
  }

  operating_system {
    type = "l26"
  }

  serial_device {}

  vga {
    type = "serial0"
  }

  startup {
    order      = var.onramp_host_startup_order
    up_delay   = var.onramp_host_startup_up_delay
    down_delay = var.onramp_host_startup_down_delay
  }

  lifecycle {
    replace_triggered_by = [terraform_data.onramp_host_rebuild]
  }
}
