resource "terraform_data" "forgejo_storage_validation" {
  count = local.forgejo_enabled ? 1 : 0

  input = {
    dataset  = var.forgejo_data_dataset
    host_uid = var.forgejo_data_host_uid
    host_gid = var.forgejo_data_host_gid
  }

  lifecycle {
    precondition {
      condition = (
        var.forgejo_data_dataset != "" &&
        var.forgejo_data_host_uid >= 0 &&
        var.forgejo_data_host_gid >= 0
      )
      error_message = "Forgejo storage prep variables must define a dataset and non-negative host UID/GID values."
    }
  }
}

module "forgejo" {
  source = "./modules/debian-lxc"
  count  = local.forgejo_enabled ? 1 : 0

  description = var.forgejo_container_description
  node_name   = var.proxmox_node_name
  vm_id       = var.forgejo_container_vmid
  tags        = ["forgejo", "git", "opentofu"]

  cores     = var.forgejo_container_cores
  memory_mb = var.forgejo_container_memory_mb
  swap_mb   = var.forgejo_container_swap_mb

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.forgejo_container_disk_gb
  }

  hostname      = var.forgejo_container_hostname
  search_domain = var.forgejo_container_search_domain
  dns_servers   = var.forgejo_container_dns_servers
  ipv4_address  = var.forgejo_container_ipv4_address
  ipv4_gateway  = var.forgejo_container_ipv4_gateway

  root_password   = var.lxc_root_password
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge      = var.forgejo_container_bridge
    mac_address = var.forgejo_container_mac_address
    vlan_id     = var.forgejo_container_vlan_id
  }

  template_file_id = proxmox_download_file.debian_13_lxc_template[0].id

  startup = {
    order      = var.forgejo_startup_order
    up_delay   = var.forgejo_startup_up_delay
    down_delay = var.forgejo_startup_down_delay
  }

  depends_on = [terraform_data.forgejo_storage_validation]
}
