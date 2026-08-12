#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC2016
scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --config-dir "${VALUES_DIR}"
python scripts/settings.py validate >/dev/null
python infra/ansible/scripts/apply-technitium-dns.py --check "${DNS_RECORDS_FILE}"

ansible-inventory -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py --list >/dev/null

mapfile -t playbooks < <(python scripts/settings.py ansible-playbooks)
ansible-playbook -i "${VALUES_DIR}/ansible/inventory/local.yml" -i infra/ansible/inventory/tfvars.py --syntax-check \
  infra/ansible/playbooks/storage-prep.yml \
  "${playbooks[@]}"
'
