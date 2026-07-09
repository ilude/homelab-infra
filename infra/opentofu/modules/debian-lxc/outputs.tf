output "id" {
  description = "Terraform resource ID of the LXC."
  value       = proxmox_virtual_environment_container.this.id
}

output "vm_id" {
  description = "Proxmox VMID of the LXC."
  value       = proxmox_virtual_environment_container.this.vm_id
}
