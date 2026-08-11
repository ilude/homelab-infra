terraform {
  required_version = ">= 1.8.0"

  backend "s3" {}

  required_providers {
    proxmox = {
      source  = "registry.terraform.io/bpg/proxmox"
      version = "~> 0.88"
    }
  }
}
