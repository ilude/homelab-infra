#!/usr/bin/env bash
set -euo pipefail

VMID="${1:-106}"
: "${PVE_HOST:?PVE_HOST is required}"
: "${SERVER_NAME:?SERVER_NAME is required}"
UPSTREAM="${UPSTREAM:-127.0.0.1:5380}"
: "${CF_API_EMAIL:?CF_API_EMAIL is required}"
: "${CF_DNS_API_TOKEN:?CF_DNS_API_TOKEN is required}"

pct_exec() {
  local command="$1"
  # VMID and command are intentionally expanded locally before invoking pct on the Proxmox host.
  # shellcheck disable=SC2029
  ssh "${PVE_HOST}" "pct exec '${VMID}' -- bash -lc $(printf '%q' "${command}")"
}

pct_push() {
  local destination="$1"
  local destination_dir
  local local_tmp
  local remote_tmp
  destination_dir="$(dirname "${destination}")"
  local_tmp="$(mktemp)"
  remote_tmp="/tmp/pct-push-${VMID}-$(basename "${destination}").$$"
  cat >"${local_tmp}"
  scp "${local_tmp}" "${PVE_HOST}:${remote_tmp}" >/dev/null
  rm -f "${local_tmp}"
  # VMID and destination paths are intentionally expanded locally before invoking pct on the Proxmox host.
  # shellcheck disable=SC2029
  ssh "${PVE_HOST}" "pct exec '${VMID}' -- install -d -m 0755 '${destination_dir}' && pct push '${VMID}' '${remote_tmp}' '${destination}' && rm -f '${remote_tmp}'"
}

append_proxy_block() {
  local server_name="$1"
  local upstream="$2"

  cat <<CADDYBLOCK

${server_name} {
    encode zstd gzip
    reverse_proxy ${upstream}

    tls {
        dns cloudflare {env.CF_DNS_API_TOKEN}
        resolvers 1.1.1.1
    }
}
CADDYBLOCK
}

pct_exec 'DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y caddy ca-certificates curl'
pct_exec 'curl -fsSL https://go.dev/dl/go1.24.4.linux-amd64.tar.gz -o /tmp/go.tar.gz && rm -rf /usr/local/go && tar -C /usr/local -xzf /tmp/go.tar.gz'
# PATH is intentionally expanded inside the remote pct_exec shell.
# shellcheck disable=SC2016
pct_exec 'PATH=/usr/local/go/bin:${PATH} GOBIN=/usr/local/bin /usr/local/go/bin/go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest'
# shellcheck disable=SC2016
pct_exec 'PATH=/usr/local/go/bin:${PATH} /usr/local/bin/xcaddy build --with github.com/caddy-dns/cloudflare --output /tmp/caddy-cloudflare'
pct_exec 'install -m 0755 /tmp/caddy-cloudflare /usr/bin/caddy && /usr/bin/caddy version'

{
  printf 'CF_API_EMAIL=%s\n' "${CF_API_EMAIL}"
  printf 'CF_DNS_API_TOKEN=%s\n' "${CF_DNS_API_TOKEN}"
} | pct_push /etc/caddy/env
pct_exec 'chmod 0600 /etc/caddy/env && chown root:caddy /etc/caddy/env'

{
  cat <<CADDYFILE
{
    email ${CF_API_EMAIL}
}
CADDYFILE
  append_proxy_block "${SERVER_NAME}" "${UPSTREAM}"
} | pct_push /etc/caddy/Caddyfile
pct_exec 'chown root:caddy /etc/caddy/Caddyfile && chmod 0644 /etc/caddy/Caddyfile'

cat <<'OVERRIDE' | pct_push /etc/systemd/system/caddy.service.d/override.conf
[Service]
EnvironmentFile=/etc/caddy/env
ExecStart=
ExecStart=/usr/bin/caddy run --config /etc/caddy/Caddyfile
OVERRIDE

pct_exec 'systemctl daemon-reload && set -a && . /etc/caddy/env && set +a && caddy fmt --overwrite /etc/caddy/Caddyfile && caddy validate --config /etc/caddy/Caddyfile'
pct_exec 'systemctl enable --now caddy && systemctl restart caddy && systemctl status caddy --no-pager'

