module "herdr" {
  source = "./modules/debian-lxc"
  count  = local.herdr_enabled ? 1 : 0

  description   = var.herdr_container_description
  node_name     = var.proxmox_node_name
  vm_id         = var.herdr_container_vmid
  started       = var.herdr_started
  start_on_boot = var.herdr_start_on_boot
  tags          = ["herdr", "management", "opentofu"]

  cores     = var.herdr_container_cores
  memory_mb = var.herdr_container_memory_mb
  swap_mb   = var.herdr_container_swap_mb

  features = {
    nesting = false
  }

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.herdr_container_disk_gb
  }

  hostname      = var.herdr_container_hostname
  search_domain = var.herdr_container_search_domain
  dns_servers   = var.herdr_container_dns_servers
  ipv4_address  = var.herdr_container_ipv4_address
  ipv4_gateway  = var.herdr_container_ipv4_gateway

  root_password   = var.lxc_root_password
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge      = var.herdr_container_bridge
    mac_address = var.herdr_container_mac_address
    vlan_id     = var.herdr_container_vlan_id
  }

  template_file_id = proxmox_download_file.debian_13_lxc_template[0].id

  startup = {
    order      = var.herdr_startup_order
    up_delay   = var.herdr_startup_up_delay
    down_delay = var.herdr_startup_down_delay
  }
}
