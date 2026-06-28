resource "terraform_data" "forgejo_data_dataset" {
  input = {
    dataset    = var.forgejo_data_dataset
    mountpoint = var.forgejo_data_host_path
    uid        = var.forgejo_data_host_uid
    gid        = var.forgejo_data_host_gid
  }

  provisioner "local-exec" {
    interpreter = ["/usr/bin/env", "bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      : "$${PVE_HOST:?PVE_HOST is required}"
      ssh -- "$${PVE_HOST}" bash -s -- \
        "$${FORGEJO_DATA_DATASET}" \
        "$${FORGEJO_DATA_HOST_PATH}" \
        "$${FORGEJO_DATA_HOST_UID}" \
        "$${FORGEJO_DATA_HOST_GID}" <<'REMOTE'
      set -euo pipefail
      dataset="$1"
      mountpoint="$2"
      uid="$3"
      gid="$4"

      if ! zfs list -- "$dataset" >/dev/null 2>&1; then
        zfs create -o "mountpoint=$mountpoint" -- "$dataset"
      fi
      mkdir -p -- "$mountpoint"
      chown -- "$uid:$gid" "$mountpoint"
      chmod 0750 -- "$mountpoint"
      REMOTE
    EOT

    environment = {
      FORGEJO_DATA_DATASET   = var.forgejo_data_dataset
      FORGEJO_DATA_HOST_PATH = var.forgejo_data_host_path
      FORGEJO_DATA_HOST_UID  = tostring(var.forgejo_data_host_uid)
      FORGEJO_DATA_HOST_GID  = tostring(var.forgejo_data_host_gid)
    }
  }
}

resource "proxmox_virtual_environment_container" "forgejo" {
  depends_on = [terraform_data.forgejo_data_dataset]

  description   = var.forgejo_container_description
  node_name     = var.proxmox_node_name
  vm_id         = var.forgejo_container_vmid
  unprivileged  = true
  started       = true
  start_on_boot = true
  tags          = ["forgejo", "git", "opentofu"]

  cpu {
    cores = var.forgejo_container_cores
  }

  memory {
    dedicated = var.forgejo_container_memory_mb
    swap      = var.forgejo_container_swap_mb
  }

  features {
    nesting = true
  }

  disk {
    datastore_id = var.rootfs_datastore_id
    size         = var.forgejo_container_disk_gb
  }

  mount_point {
    volume = var.forgejo_data_host_path
    path   = var.forgejo_data_mount_path
  }

  initialization {
    hostname = var.forgejo_container_hostname

    dns {
      domain  = var.forgejo_container_search_domain
      servers = var.forgejo_container_dns_servers
    }

    ip_config {
      ipv4 {
        address = var.forgejo_container_ipv4_address
        gateway = var.forgejo_container_ipv4_gateway
      }
    }

    user_account {
      password = var.container_root_password
      keys     = var.container_ssh_public_keys
    }
  }

  network_interface {
    name        = "eth0"
    bridge      = var.forgejo_container_bridge
    mac_address = var.forgejo_container_mac_address
  }

  operating_system {
    template_file_id = proxmox_download_file.debian_12_lxc_template.id
    type             = "debian"
  }

  startup {
    order      = var.forgejo_startup_order
    up_delay   = var.forgejo_startup_up_delay
    down_delay = var.forgejo_startup_down_delay
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
