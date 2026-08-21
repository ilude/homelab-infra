#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || -z "$1" ]]; then
  printf 'Usage: scripts/apply-service.sh <enabled-service>\n' >&2
  exit 2
fi

service="$1"
runtime_profile="config"
case "${service}" in
  seaweedfs_onramp) runtime_profile="seaweedfs" ;;
  onclave_onramp|searxng_onramp) runtime_profile="onclave" ;;
  freellmapi_onramp) runtime_profile="freellmapi" ;;
esac

# shellcheck disable=SC2016
BWS_RUNTIME_PROFILE="${runtime_profile}" INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c '
python scripts/apply-ansible-services.py \
  --mode sequential \
  --service "$1" \
  --inventory "${VALUES_DIR}/ansible/inventory/local.yml" \
  --inventory infra/ansible/inventory/tfvars.py
' bash "${service}"
