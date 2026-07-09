module "forgejo_runner" {
  source = "./modules/debian-lxc"
  count  = local.forgejo_runner_enabled ? 1 : 0

  description   = var.forgejo_runner_description
  node_name     = var.proxmox_node_name
  vm_id         = var.forgejo_runner_vmid
  started       = var.forgejo_runner_started
  start_on_boot = var.forgejo_runner_start_on_boot
  tags          = ["forgejo", "runner", "actions", "opentofu"]

  cores     = var.forgejo_runner_cores
  memory_mb = var.forgejo_runner_memory_mb
  swap_mb   = var.forgejo_runner_swap_mb

  disk = {
    datastore_id = var.rootfs_datastore_id
    size_gb      = var.forgejo_runner_disk_gb
  }

  hostname      = var.forgejo_runner_hostname
  search_domain = var.forgejo_runner_search_domain
  dns_servers   = var.forgejo_runner_dns_servers
  ipv4_address  = var.forgejo_runner_ipv4_address
  ipv4_gateway  = var.forgejo_runner_ipv4_gateway

  root_password   = var.lxc_root_password
  ssh_public_keys = var.lxc_ssh_public_keys

  network = {
    bridge      = var.forgejo_runner_bridge
    mac_address = var.forgejo_runner_mac_address
    vlan_id     = var.forgejo_runner_vlan_id
  }

  template_file_id = proxmox_download_file.debian_12_lxc_template[0].id

  startup = {
    order      = var.forgejo_runner_startup_order
    up_delay   = var.forgejo_runner_startup_up_delay
    down_delay = var.forgejo_runner_startup_down_delay
  }
}
