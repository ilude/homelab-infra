#!/usr/bin/env bash
set -euo pipefail

settings_file="${INFRA_BWS_LOCATOR_FILE:-settings.local.json}"
if [[ ! -f "${settings_file}" ]]; then
  printf 'Missing %s. Configure the ignored BWS locator before running infrastructure commands.\n' "${settings_file}" >&2
  exit 1
fi
if [[ -z "${BITWARDEN_ACCESS_KEY:-}" ]]; then
  printf 'BITWARDEN_ACCESS_KEY is missing.\n' >&2
  exit 1
fi

export INFRA_HOST_UID="${INFRA_HOST_UID:-$(scripts/host-id.sh uid)}"
export INFRA_HOST_GID="${INFRA_HOST_GID:-$(scripts/host-id.sh gid)}"
export INFRA_GIT_COMMIT="${INFRA_GIT_COMMIT:-$(git rev-parse HEAD 2>/dev/null || true)}"

compose_args=(compose run --rm)
if [[ ! -t 0 || ! -t 1 ]]; then
  compose_args+=(-T)
fi

runner_args=(
  --settings "${settings_file}"
  --runtime-profile "${BWS_RUNTIME_PROFILE:-config}"
)
if [[ "${BWS_WRITEBACK:-}" == "1" ]]; then
  if [[ "$#" -lt 2 || "$1" != "python" || "$2" != "scripts/update.py" ]]; then
    printf 'BWS_WRITEBACK=1 is only allowed for: python scripts/update.py [selectors...]\n' >&2
    exit 2
  fi
  for selector in "${@:3}"; do
    if [[ "${selector}" == -* ]]; then
      printf 'BWS_WRITEBACK=1 is only allowed for: python scripts/update.py [selectors...]\n' >&2
      exit 2
    fi
  done
  runner_args+=(--writeback-update)
fi

docker "${compose_args[@]}" infra python scripts/run-infra-container.py \
  "${runner_args[@]}" \
  -- "$@"
