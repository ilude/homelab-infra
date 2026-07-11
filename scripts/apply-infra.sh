#!/usr/bin/env bash
set -euo pipefail

destroy_verify_flag=""
if [[ "${INFRA_ALLOW_DESTROY:-}" == "1" ]]; then
  destroy_verify_flag="--allow-destroy"
fi
stateful_batch_verify_flag=""
if [[ "${INFRA_ALLOW_STATEFUL_BATCH:-}" == "1" ]]; then
  stateful_batch_verify_flag="--allow-stateful-batch"
fi
target_service="${INFRA_TARGET_SERVICE:-}"

# shellcheck disable=SC2016
INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --require-values

if [[ ! -f tfplan && ! -f tfplan.meta.json ]]; then
  printf "No saved infrastructure plan found. Run just plan, review the output, then run just apply.\n" >&2
  exit 1
fi
if [[ ! -f tfplan ]]; then
  printf "Saved plan file tfplan is missing. Run just plan again.\n" >&2
  exit 1
fi
if [[ ! -f tfplan.meta.json ]]; then
  printf "Saved plan metadata tfplan.meta.json is missing. Run just plan again.\n" >&2
  exit 1
fi

target_service="${1:-}"
shift || true

verify_args=()
for verify_arg in "$@"; do
  if [[ -n "${verify_arg}" ]]; then
    verify_args+=("${verify_arg}")
  fi
done
python scripts/tfplan-metadata.py verify --plan tfplan --metadata tfplan.meta.json "${verify_args[@]}"
python scripts/tfplan-metadata.py summary --metadata tfplan.meta.json
python scripts/settings.py summary
storage_vars_args=()
if [[ -n "${target_service}" ]]; then
  storage_vars_args+=(--service "${target_service}")
fi
python scripts/storage-vars.py --summary "${storage_vars_args[@]}"

printf "Applying verified tfplan created by just plan.\n"
trap "rm -f tfplan tfplan.meta.json ./*.tfplan ./*.tfplan.meta.json" EXIT

storage_vars="$(python scripts/storage-vars.py "${storage_vars_args[@]}")"
if python -c "import json, sys; raise SystemExit(0 if json.loads(sys.argv[1]).get(\"storage_datasets\") else 1)" "${storage_vars}"; then
  ansible-playbook \
    -i values/ansible/inventory/local.yml \
    -i infra/ansible/inventory/tfvars.py \
    -e "${storage_vars}" \
    infra/ansible/playbooks/storage-prep.yml
fi

tofu -chdir=infra/opentofu apply -state=../../values/terraform.tfstate ../../tfplan

ansible_service_args=()
if [[ -n "${target_service}" ]]; then
  ansible_service_args+=(--service "${target_service}")
fi

python scripts/apply-ansible-services.py \
  --inventory values/ansible/inventory/local.yml \
  --inventory infra/ansible/inventory/tfvars.py \
  --env-file values/.env \
  "${ansible_service_args[@]}"
' bash "${target_service}" "${destroy_verify_flag}" "${stateful_batch_verify_flag}"
