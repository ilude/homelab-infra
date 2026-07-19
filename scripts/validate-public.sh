#!/usr/bin/env bash
set -euo pipefail

export INFRA_HOST_UID="${INFRA_HOST_UID:-$(scripts/host-id.sh uid)}"
export INFRA_HOST_GID="${INFRA_HOST_GID:-$(scripts/host-id.sh gid)}"

docker compose config >/dev/null

# shellcheck disable=SC2016
docker compose run --rm infra bash -euo pipefail -c '
python scripts/workspace-preflight.py

tofu -chdir=infra/opentofu init -backend=false
tofu fmt -check -recursive infra/opentofu scaffold/terraform.tfvars
tofu -chdir=infra/opentofu validate
tflint --chdir=infra/opentofu --minimum-failure-severity=error

shellcheck scripts/*.sh tools/docker-entrypoint.sh

mapfile -t python_files < <(find infra/ansible scripts tests -type f -name "*.py" | sort)
python -m py_compile "${python_files[@]}"
python infra/ansible/scripts/validate-service-state-archive.py --help >/dev/null

python infra/ansible/scripts/apply-technitium-dns.py --check scaffold/dns-records.local.json
python scripts/parse-env.py --env-file scaffold/.env.example >/dev/null
python scripts/settings.py --settings settings.example.json validate >/dev/null
python -m unittest discover -s tests -p "test_*.py"

export ANSIBLE_TFVARS_FILE=scaffold/terraform.tfvars
export INFRA_SETTINGS_FILE=settings.example.json
export PVE_HOST=proxmox.example.internal
export SECONDARY_PVE_HOST=proxmox-secondary.example.internal
ansible-inventory -i scaffold/ansible/inventory/local.yml -i infra/ansible/inventory/tfvars.py --list >/dev/null
mapfile -t playbooks < <(python scripts/settings.py --settings settings.example.json ansible-playbooks --all)
ansible-playbook -i scaffold/ansible/inventory/local.yml -i infra/ansible/inventory/tfvars.py --syntax-check \
  infra/ansible/playbooks/site.yml \
  infra/ansible/playbooks/storage-prep.yml \
  infra/ansible/playbooks/service-state-backup.yml \
  infra/ansible/playbooks/service-state-restore.yml \
  infra/ansible/playbooks/hermes-state-backup.yml \
  infra/ansible/playbooks/hermes-state-restore.yml \
  "${playbooks[@]}"
# Ansible-lint starts a syntax-check subprocess for each playbook. Copy its inputs
# off the Windows bind mount so those repeated filesystem reads stay fast.
ansible_lint_dir="$(mktemp -d)"
cleanup_ansible_lint() {
  rm -rf -- "${ansible_lint_dir}"
}
trap cleanup_ansible_lint EXIT HUP INT TERM
cp -a .ansible-lint ansible.cfg settings.example.json infra scaffold scripts "${ansible_lint_dir}/"
(
  cd "${ansible_lint_dir}"
  export ANSIBLE_CONFIG="${ansible_lint_dir}/ansible.cfg"
  ansible-lint infra/ansible
)
'
