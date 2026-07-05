#!/usr/bin/env bash
set -euo pipefail

container_user="${INFRA_CONTAINER_USER:-anvil}"
container_home="/home/${container_user}"
ssh_dir="${container_home}/.ssh"

install -d -m 0755 "${container_home}"
install -d -m 0755 "${container_home}/.terraform.d" "${container_home}/.ansible"
install -d -m 0755 "${container_home}/.terraform.d/plugin-cache"
chown -R "${container_user}:${container_user}" "${container_home}/.terraform.d" "${container_home}/.ansible"

find /workspace -type d \( -name __pycache__ -o -name .pytest_cache -o -name .terraform \) \
  -prune -exec chown -R "${container_user}:${container_user}" {} + 2>/dev/null || true

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

gosu "${container_user}" git config --global --add safe.directory /workspace >/dev/null 2>&1 || true

export HOME="${container_home}"
exec gosu "${container_user}" "$@"
