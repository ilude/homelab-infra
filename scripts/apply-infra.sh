#!/usr/bin/env bash
set -euo pipefail

destroy_verify_flag=""
if [[ "${INFRA_ALLOW_DESTROY:-}" == "1" ]]; then
  destroy_verify_flag="--allow-destroy"
fi

# shellcheck disable=SC2016
INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --require-values

if [[ ! -f tfplan && ! -f tfplan.meta.json ]]; then
  printf "No saved infrastructure plan found. Run `just plan`, review the output, then run `just apply`.\n" >&2
  exit 1
fi
if [[ ! -f tfplan ]]; then
  printf "Saved plan file `tfplan` is missing. Run `just plan` again.\n" >&2
  exit 1
fi
if [[ ! -f tfplan.meta.json ]]; then
  printf "Saved plan metadata `tfplan.meta.json` is missing. Run `just plan` again.\n" >&2
  exit 1
fi

verify_args=()
if [[ -n "${1:-}" ]]; then
  verify_args+=("$1")
fi
python scripts/tfplan-metadata.py verify --plan tfplan --metadata tfplan.meta.json "${verify_args[@]}"
python scripts/tfplan-metadata.py summary --metadata tfplan.meta.json
python scripts/settings.py summary
python scripts/storage-vars.py --summary

printf "Applying verified tfplan created by `just plan`.\n"
trap "rm -f tfplan tfplan.meta.json ./*.tfplan ./*.tfplan.meta.json" EXIT

storage_vars="$(python scripts/storage-vars.py)"
ansible-playbook \
  -i values/ansible/inventory/local.yml \
  -i infra/ansible/inventory/tfvars.py \
  -e "${storage_vars}" \
  infra/ansible/playbooks/storage-prep.yml

tofu -chdir=infra/opentofu apply -state=../../values/terraform.tfstate ../../tfplan

mapfile -t playbooks < <(python scripts/settings.py ansible-playbooks)
if [[ "${#playbooks[@]}" -gt 0 ]]; then
  ansible-playbook \
    -i values/ansible/inventory/local.yml \
    -i infra/ansible/inventory/tfvars.py \
    "${playbooks[@]}"
fi
' bash "${destroy_verify_flag}"
