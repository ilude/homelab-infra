check "herdr_hardening_policy" {
  assert {
    condition = (
      !var.herdr_password_authentication &&
      !var.herdr_permit_root_login &&
      length(var.herdr_allowed_ssh_cidrs) > 0 &&
      alltrue([
        for cidr in var.herdr_allowed_ssh_cidrs :
        can(cidrhost(cidr, 0)) && !strcontains(cidr, ":") && cidr != "0.0.0.0/0"
      ]) &&
      (
        var.herdr_container_ipv4_address == "dhcp" ||
        split("/", var.herdr_container_ipv4_address)[0] == var.herdr_lan_ip
      )
    )
    error_message = "herdr must keep password and root SSH disabled, use bounded IPv4 source CIDRs, and keep the static LXC address aligned with herdr_lan_ip."
  }
}
