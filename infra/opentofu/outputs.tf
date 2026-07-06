output "technitium_container_vmid" {
  description = "Proxmox VMID for the Technitium DNS LXC, or null when disabled."
  value       = local.technitium_enabled ? proxmox_virtual_environment_container.technitium_dns[0].vm_id : null
}

output "technitium_dns_ip" {
  description = "Technitium DNS LXC IPv4 address without CIDR suffix, or null when disabled."
  value       = local.technitium_enabled ? split("/", var.technitium_container_ipv4_address)[0] : null
}

output "technitium_web_url" {
  description = "Technitium web console URL after bootstrap install, or null when disabled."
  value       = local.technitium_enabled ? "http://${split("/", var.technitium_container_ipv4_address)[0]}:5380/" : null
}

output "technitium_dns_endpoint" {
  description = "DNS endpoint to use in UniFi DHCP after Technitium is configured, or null when disabled."
  value       = local.technitium_enabled ? "${split("/", var.technitium_container_ipv4_address)[0]}:53" : null
}

output "forgejo_container_vmid" {
  description = "Proxmox VMID for the Forgejo LXC, or null when disabled."
  value       = local.forgejo_enabled ? proxmox_virtual_environment_container.forgejo[0].vm_id : null
}

output "forgejo_lan_ip" {
  description = "Expected Forgejo LAN IP, usually supplied by static DHCP, or null when disabled."
  value       = local.forgejo_enabled ? var.forgejo_lan_ip : null
}

output "forgejo_https_url" {
  description = "Forgejo HTTPS URL when the Forgejo hostname points at the Forgejo LXC Caddy instance, or null when disabled."
  value       = local.forgejo_enabled ? "https://${var.forgejo_server_name}/" : null
}

output "forgejo_ssh_clone_prefix" {
  description = "Forgejo SSH clone prefix when system OpenSSH on the Forgejo LXC is integrated with Forgejo, or null when disabled."
  value       = local.forgejo_enabled ? "git@${var.forgejo_server_name}:" : null
}

output "forgejo_data_mount" {
  description = "Forgejo data bind mount from Proxmox host to LXC, or null when disabled."
  value       = local.forgejo_enabled ? "${var.forgejo_data_host_path}:${var.forgejo_data_mount_path}" : null
}

output "infisical_container_vmid" {
  description = "Proxmox VMID for the Infisical LXC, or null when disabled."
  value       = local.infisical_enabled ? proxmox_virtual_environment_container.infisical[0].vm_id : null
}

output "infisical_lan_ip" {
  description = "Expected Infisical LAN IP, usually supplied by static DHCP, or null when disabled."
  value       = local.infisical_enabled ? var.infisical_lan_ip : null
}

output "infisical_https_url" {
  description = "Infisical HTTPS URL when the Infisical hostname points at the Infisical LXC Caddy instance, or null when disabled."
  value       = local.infisical_enabled ? "https://${var.infisical_server_name}/" : null
}

output "hermes_container_vmid" {
  description = "Proxmox VMID for the Hermes management LXC, or null when disabled."
  value       = local.hermes_enabled ? proxmox_virtual_environment_container.hermes[0].vm_id : null
}

output "hermes_lan_ip" {
  description = "Expected Hermes LAN IP, usually supplied by static DHCP, or null when disabled."
  value       = local.hermes_enabled ? var.hermes_lan_ip : null
}

output "hermes_https_url" {
  description = "Hermes HTTPS URL when the Hermes hostname points at the Hermes LXC Caddy instance, or null when disabled."
  value       = local.hermes_enabled ? "https://${var.hermes_server_name}/" : null
}

output "hermes_ssh_target" {
  description = "Hermes SSH target, or null when disabled."
  value       = local.hermes_enabled ? "root@${var.hermes_server_name}" : null
}

output "tailscale_client_container_vmid" {
  description = "Proxmox VMID for the Tailscale client LXC, or null when disabled."
  value       = local.tailscale_client_enabled ? proxmox_virtual_environment_container.tailscale_client[0].vm_id : null
}

output "tailscale_client_ipv4_address" {
  description = "Configured IPv4 address for the Tailscale client LXC, or null when disabled."
  value       = local.tailscale_client_enabled ? var.tailscale_client_ipv4_address : null
}
