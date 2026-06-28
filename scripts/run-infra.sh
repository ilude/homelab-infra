#!/usr/bin/env bash
set -euo pipefail

values_dir="${VALUES_DIR:-values}"
if [[ ! -f "${values_dir}/.env" ]]; then
  printf 'Missing %s/.env. Run just setup or just setup <remote>.\n' "${values_dir}" >&2
  exit 1
fi

exec docker compose run --rm infra bash -c \
  'set -a; . <(tr -d "\r" < "${VALUES_DIR:-values}/.env"); set +a; exec "$@"' \
  bash "$@"
