# Technitium high availability

This deployment can run a second Technitium DNS LXC on a standalone Proxmox host and use Keepalived to move the existing LAN DNS address between nodes.

## Topology

- Each Technitium node has a permanent static address.
- `technitium_virtual_ipv4_address` is the client-facing DNS address advertised by Keepalived.
- Technitium clustering uses the permanent node addresses and native HTTPS endpoint. It does not use the floating address or either Caddy HTTPS proxy.
- Both nodes run the same Caddy HTTPS proxy so the human web route follows the floating address. Native cluster traffic remains on Technitium HTTPS.
- The primary Keepalived node has priority 150. The secondary has priority 100.
- Keepalived uses unicast VRRP between the permanent node addresses.
- The floating address is eligible only when local UDP and TCP queries for the Technitium cluster zone succeed.

Technitium clustering synchronizes common configuration and catalog member zones. Cache and logs remain node-local. See the [Technitium clustering guide](https://blog.technitium.com/2025/11/understanding-clustering-and-how-to.html).

## Private values

Enable `technitium_secondary` in `settings.local.json`. Keep the second Proxmox credential in `values/.env`:

```dotenv
export SECONDARY_PVE_HOST="proxmox-secondary.example.internal"
export TF_VAR_secondary_proxmox_endpoint="https://proxmox-secondary.example.internal:8006/"
export TF_VAR_secondary_proxmox_api_token="terraform@pve!provider=REPLACE_WITH_SECONDARY_PROXMOX_TOKEN"
```

The secondary LXC, cluster domain, and floating address are declared in `values/terraform.tfvars`. The cluster domain is immutable after initialization.

## Deployment sequence

Treat the secondary as a canary before changing the existing primary address:

1. Keep `technitium_cluster_enabled = false`.
2. Run `just validate` and `just plan`.
3. Review a plan that creates only the secondary template and LXC on the secondary Proxmox host.
4. Run the approved `just apply` and verify DNS, SSH, and the Technitium API on the secondary permanent address.
5. Create a fresh `scripts/service-state.sh backup technitium` backup and verify its checksum.
6. Move the primary LXC to its new permanent address, retain the old address in `technitium_virtual_ipv4_address`, and set `technitium_cluster_enabled = true`.
7. Run `just validate`, review the new `just plan`, and run the approved `just apply`.
8. Verify cluster connectivity, catalog zone synchronization, and the floating DNS address.
9. Stop Keepalived on each node separately and confirm the other node takes ownership of the floating address.

The initial primary address cutover can briefly interrupt DNS between the OpenTofu network change and Ansible starting Keepalived. Do not proceed if the secondary direct DNS endpoint is unhealthy.

## Recovery

If secondary creation fails, leave the existing primary and floating address unchanged and recover only the secondary service.

If cluster initialization or floating-address activation fails after the primary address changes:

1. Verify the primary directly on its permanent address.
2. Restore client DNS quickly by assigning the floating address to the healthy primary through the managed Keepalived configuration.
3. Keep the secondary out of VRRP until direct DNS and cluster state are healthy.
4. Restore `/etc/dns` with `scripts/service-state.sh restore technitium <archive>` only when configuration state is damaged. Address or VRRP failures do not require a Technitium state restore.
