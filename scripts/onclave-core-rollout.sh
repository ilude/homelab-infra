#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 4 ]]; then
  printf 'Usage: scripts/onclave-core-rollout.sh --source-sha <40-hex-sha> [--core-digest sha256:<64-hex>]\n' >&2
  exit 2
fi

# The controller must receive BWS_RUNTIME_PROFILE=onclave so the command only
# gets the configuration and runtime families needed by this rollout.
BWS_RUNTIME_PROFILE=onclave INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh \
  python scripts/onclave-core-rollout.py "$@"
