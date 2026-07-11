#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || -z "$1" ]]; then
  printf 'Usage: scripts/apply-service.sh <enabled-service>\n' >&2
  exit 2
fi

service="$1"

INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh python scripts/apply-ansible-services.py \
  --mode sequential \
  --service "${service}" \
  --inventory values/ansible/inventory/local.yml \
  --inventory infra/ansible/inventory/tfvars.py \
  --env-file values/.env
