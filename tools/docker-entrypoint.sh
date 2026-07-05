#!/usr/bin/env bash
set -euo pipefail

container_user="${INFRA_CONTAINER_USER:-anvil}"
container_home="/home/${container_user}"
ssh_dir="${container_home}/.ssh"

if [[ -n "${INFRA_HOST_GID:-}" ]] && [[ "$(id -g "${container_user}")" != "${INFRA_HOST_GID}" ]]; then
  groupmod -o -g "${INFRA_HOST_GID}" "${container_user}"
fi

if [[ -n "${INFRA_HOST_UID:-}" ]] && [[ "$(id -u "${container_user}")" != "${INFRA_HOST_UID}" ]]; then
  usermod -o -u "${INFRA_HOST_UID}" -g "$(id -g "${container_user}")" "${container_user}"
fi

install -d -m 0755 "${container_home}"
install -d -m 0755 "${container_home}/.terraform.d" "${container_home}/.ansible"
install -d -m 0755 "${container_home}/.terraform.d/plugin-cache"
chown -R "${container_user}:${container_user}" "${container_home}/.terraform.d" "${container_home}/.ansible"

# Keep generated bind-mounted artifacts writable by the host user that invoked
# Docker. This is intentionally narrow: do not recursively chown the private
# values repo, but do repair local state/lock/plan files that OpenTofu must
# rewrite or replace.
for path in /workspace /workspace/infra/opentofu /workspace/values; do
  if [[ -e "${path}" ]]; then
    chown "${container_user}:${container_user}" "${path}" 2>/dev/null || true
  fi
done

find /workspace -type d \( -name __pycache__ -o -name .pytest_cache -o -name .terraform \) \
  -prune -exec chown -R "${container_user}:${container_user}" {} + 2>/dev/null || true

find /workspace -maxdepth 1 -type f \( -name 'tfplan*' -o -name '*.tfplan*' \) \
  -exec chown "${container_user}:${container_user}" {} + 2>/dev/null || true

if [[ -d /workspace/values ]]; then
  find /workspace/values -maxdepth 1 -type f \( \
    -name 'terraform.tfstate*' -o \
    -name '*.tfstate*' -o \
    -name '.terraform.tfstate.lock.info' \
  \) -exec chown "${container_user}:${container_user}" {} + 2>/dev/null || true
fi

if [[ -d /ssh-ro ]]; then
  install -d -m 0700 -o "${container_user}" -g "${container_user}" "${ssh_dir}"

  for path in /ssh-ro/known_hosts /ssh-ro/config /ssh-ro/*.pub; do
    if [[ -f "${path}" ]]; then
      cp "${path}" "${ssh_dir}/"
    fi
  done

  if [[ "${INFRA_COPY_SSH_KEYS:-false}" == "true" ]]; then
    find /ssh-ro -maxdepth 1 -type f \
      ! -name '*.pub' \
      ! -name known_hosts \
      ! -name config \
      -exec cp {} "${ssh_dir}/" \;
  fi

  chown -R "${container_user}:${container_user}" "${ssh_dir}"
  chmod 0700 "${ssh_dir}"
  find "${ssh_dir}" -type f -name '*.pub' -exec chmod 0644 {} +
  find "${ssh_dir}" -type f ! -name '*.pub' -exec chmod 0600 {} +
fi

export HOME="${container_home}"

exec gosu "${container_user}" "$@"
