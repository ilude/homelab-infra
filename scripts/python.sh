#!/usr/bin/env bash
set -euo pipefail

export INFRA_HOST_UID="${INFRA_HOST_UID:-$(scripts/host-id.sh uid)}"
export INFRA_HOST_GID="${INFRA_HOST_GID:-$(scripts/host-id.sh gid)}"
export INFRA_GIT_COMMIT="${INFRA_GIT_COMMIT:-$(git rev-parse HEAD 2>/dev/null || true)}"

compose_args=(compose run --rm)
if [[ ! -t 0 || ! -t 1 ]]; then
  compose_args+=(-T)
fi

exec docker "${compose_args[@]}" infra python "$@"
