#!/usr/bin/env bash
set -euo pipefail

compose_args=(compose run --rm)
if [[ ! -t 0 || ! -t 1 ]]; then
  compose_args+=(-T)
fi

exec docker "${compose_args[@]}" infra python "$@"
