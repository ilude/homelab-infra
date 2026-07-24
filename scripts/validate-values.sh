#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC2016
scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --require-values
python scripts/settings.py validate >/dev/null
python infra/ansible/scripts/apply-technitium-dns.py --check "${INFRA_VALUES_DIR}/dns-records.local.json"

ansible-inventory -i "${INFRA_VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py --list >/dev/null

mapfile -t playbooks < <(python scripts/settings.py ansible-playbooks)
ansible-playbook -i "${INFRA_VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py --syntax-check \
  infra/ansible/playbooks/storage-prep.yml \
  infra/ansible/playbooks/guest-mount-feature-preflight.yml \
  "${playbooks[@]}"
'
