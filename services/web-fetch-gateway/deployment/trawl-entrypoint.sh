#!/bin/sh
set -eu

# Only the browser container's network namespace is changed. Never use host
# networking or share this namespace with the gateway or an existing service.
if [ ! -f /run/.containerenv ] && [ ! -f /.dockerenv ]; then
    echo 'Browser network guard requires a container' >&2
    exit 1
fi
iptables -w -P OUTPUT DROP
iptables -w -F OUTPUT
iptables -w -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
for network in \
    0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 \
    172.16.0.0/12 192.0.0.0/24 192.0.2.0/24 192.168.0.0/16 \
    198.18.0.0/15 198.51.100.0/24 203.0.113.0/24 224.0.0.0/4 240.0.0.0/4; do
    iptables -w -A OUTPUT -d "$network" -j REJECT
done
# A public DNS resolver is supplied through the container's --dns setting. No
# private DNS exception allows an HTTP request to bypass destination restrictions.
iptables -w -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -w -A OUTPUT -p tcp -j ACCEPT
# IPv4-only browser egress also closes mapped IPv6, link-local and transition paths.
ip6tables -w -P OUTPUT DROP
ip6tables -w -F OUTPUT
ip6tables -w -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Firefox is controlled through inherited pipes, not a loopback HTTP listener.
# Remove network administration before any page can execute. Dropping every
# capability made this pinned Firefox runtime hang during navigation; retain the
# ordinary rootless Podman defaults. No Docker/Podman socket is mounted, and the
# removed bounding-set capability cannot be restored to change this firewall.
exec setpriv --bounding-set=-net_admin --no-new-privs \
    /usr/bin/tini -- "$@"
