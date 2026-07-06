#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC2016
INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --require-values

test -f tfplan
test -f tfplan.meta.json
python scripts/tfplan-metadata.py verify --plan tfplan --metadata tfplan.meta.json

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
'
