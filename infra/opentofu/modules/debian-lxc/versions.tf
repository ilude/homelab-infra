terraform {
  required_version = ">= 1.8.0"

  required_providers {
    proxmox = {
      source = "registry.terraform.io/bpg/proxmox"
    }
  }
}
