resource "proxmox_download_file" "debian_13_lxc_template_secondary" {
  provider = proxmox.secondary
  count    = local.technitium_secondary_enabled ? 1 : 0

  checksum            = var.debian_13_lxc_template_checksum
  checksum_algorithm  = var.debian_13_lxc_template_checksum_algorithm
  content_type        = "vztmpl"
  datastore_id        = var.secondary_proxmox_template_datastore_id
  file_name           = var.debian_13_lxc_template_file_name
  node_name           = var.secondary_proxmox_node_name
  url                 = var.debian_13_lxc_template_url
  overwrite           = false
  overwrite_unmanaged = false
}

module "technitium_secondary_dns" {
  source = "./modules/debian-lxc"
  count  = local.technitium_secondary_enabled ? 1 : 0

  providers = {
    proxmox = proxmox.secondary
  }

  description = var.technitium_secondary_container_description
  node_name   = var.secondary_proxmox_node_name
  vm_id       = var.technitium_secondary_container_vmid
  tags        = ["dns", "technitium", "secondary", "opentofu"]

  cores     = var.technitium_secondary_container_cores
  memory_mb = var.technitium_secondary_container_memory_mb
  swap_mb   = var.technitium_secondary_container_swap_mb

  disk = {
    datastore_id = var.secondary_proxmox_rootfs_datastore_id
    size_gb      = var.technitium_secondary_container_disk_gb
  }

  hostname      = var.technitium_secondary_container_hostname
  search_domain = var.technitium_secondary_container_search_domain
  dns_servers   = var.technitium_secondary_container_dns_servers
  ipv4_address  = var.technitium_secondary_container_ipv4_address
  ipv4_gateway  = var.technitium_secondary_container_ipv4_gateway

  root_password   = var.lxc_root_password
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge  = var.technitium_secondary_container_bridge
    vlan_id = var.technitium_secondary_container_vlan_id
  }

  template_file_id = proxmox_download_file.debian_13_lxc_template_secondary[0].id

  startup = {
    order      = "1"
    up_delay   = "15"
    down_delay = "15"
  }
}
