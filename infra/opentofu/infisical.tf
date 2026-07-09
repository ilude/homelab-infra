module "infisical" {
  source = "./modules/debian-lxc"
  count  = local.infisical_enabled ? 1 : 0

  description   = var.infisical_container_description
  node_name     = var.proxmox_node_name
  vm_id         = var.infisical_container_vmid
  started       = var.infisical_started
  start_on_boot = var.infisical_start_on_boot
  tags          = ["infisical", "secrets", "opentofu"]

  cores     = var.infisical_container_cores
  memory_mb = var.infisical_container_memory_mb
  swap_mb   = var.infisical_container_swap_mb

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.infisical_container_disk_gb
  }

  hostname      = var.infisical_container_hostname
  search_domain = var.infisical_container_search_domain
  dns_servers   = var.infisical_container_dns_servers
  ipv4_address  = var.infisical_container_ipv4_address
  ipv4_gateway  = var.infisical_container_ipv4_gateway

  root_password   = var.lxc_root_password
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge      = var.infisical_container_bridge
    mac_address = var.infisical_container_mac_address
    vlan_id     = var.infisical_container_vlan_id
  }

  template_file_id = proxmox_download_file.debian_12_lxc_template[0].id

  startup = {
    order      = var.infisical_startup_order
    up_delay   = var.infisical_startup_up_delay
    down_delay = var.infisical_startup_down_delay
  }
}
