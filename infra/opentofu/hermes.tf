module "hermes" {
  source = "./modules/debian-lxc"
  count  = local.hermes_enabled ? 1 : 0

  description   = var.hermes_container_description
  node_name     = var.proxmox_node_name
  vm_id         = var.hermes_container_vmid
  started       = var.hermes_started
  start_on_boot = var.hermes_start_on_boot
  tags          = ["hermes", "management", "opentofu"]

  cores     = var.hermes_container_cores
  memory_mb = var.hermes_container_memory_mb
  swap_mb   = var.hermes_container_swap_mb

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.hermes_container_disk_gb
  }

  hostname      = var.hermes_container_hostname
  search_domain = var.hermes_container_search_domain
  dns_servers   = var.hermes_container_dns_servers
  ipv4_address  = var.hermes_container_ipv4_address
  ipv4_gateway  = var.hermes_container_ipv4_gateway

  root_password   = var.lxc_root_password
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge      = var.hermes_container_bridge
    mac_address = var.hermes_container_mac_address
    vlan_id     = var.hermes_container_vlan_id
  }

  template_file_id = proxmox_download_file.debian_12_lxc_template[0].id

  startup = {
    order      = var.hermes_startup_order
    up_delay   = var.hermes_startup_up_delay
    down_delay = var.hermes_startup_down_delay
  }
}
