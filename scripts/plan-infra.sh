#!/usr/bin/env bash
set -euo pipefail

source scripts/site-context.sh
values_dir="$(site_values_dir)"
rm -f "${values_dir}/tfplan" "${values_dir}/tfplan.meta.json"

target_service="${INFRA_TARGET_SERVICE:-}"
replace_service="${INFRA_REPLACE_SERVICE:-}"
if [[ -n "${replace_service}" ]]; then
  if [[ -n "${target_service}" && "${target_service}" != "${replace_service}" ]]; then
    printf 'INFRA_TARGET_SERVICE and INFRA_REPLACE_SERVICE must match when both are set.\n' >&2
    exit 2
  fi
  target_service="${replace_service}"
fi

# shellcheck disable=SC2016
INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh bash -euo pipefail -c '
python scripts/workspace-preflight.py --require-values
python scripts/settings.py summary
storage_vars_args=()
if [[ -n "${1:-}" ]]; then
  storage_vars_args+=(--service "${1}")
fi
python scripts/storage-vars.py --summary "${storage_vars_args[@]}"
python scripts/guest-mount-feature-vars.py --summary

guest_mount_feature_vars="$(python scripts/guest-mount-feature-vars.py)"
ansible-playbook \
  -i "${INFRA_VALUES_DIR}/ansible/inventory/local.yml" \
  -i infra/ansible/inventory/tfvars.py \
  -e "${guest_mount_feature_vars}" \
  infra/ansible/playbooks/guest-mount-feature-preflight.yml

tofu -chdir=infra/opentofu init

enabled_services="$(python scripts/settings.py tofu-var)"
target_args=()
replace_args=()
if [[ -n "${1:-}" ]]; then
  while IFS= read -r target; do
    [[ -n "${target}" ]] && target_args+=("-target=${target}")
  done < <(python scripts/settings.py tofu-targets "${1}")
  printf "Creating one-service canary plan for %s. A full plan is required after this rollout.\n" "${1}"
fi
if [[ -n "${2:-}" ]]; then
  replace_runtime="$(python scripts/service-runtime.py "${2}")"
  while IFS= read -r target; do
    [[ -n "${target}" ]] && replace_args+=("-replace=${target}")
  done < <(python scripts/settings.py tofu-replace-targets "${2}" --runtime "${replace_runtime}")
  printf "Forcing replacement of %s service resources for runtime %s. Review destroy/create output carefully.\n" "${2}" "${replace_runtime}"
fi

tofu -chdir=infra/opentofu plan \
  -var "enabled_services=${enabled_services}" \
  -var-file=../../${INFRA_VALUES_DIR}/terraform.tfvars \
  -state=../../${INFRA_VALUES_DIR}/terraform.tfstate \
  "${target_args[@]}" \
  "${replace_args[@]}" \
  -out=../../${INFRA_VALUES_DIR}/tfplan

tofu -chdir=infra/opentofu show ../../${INFRA_VALUES_DIR}/tfplan
python scripts/tfplan-metadata.py create \
  --plan "${INFRA_VALUES_DIR}/tfplan" \
  --metadata "${INFRA_VALUES_DIR}/tfplan.meta.json" \
  --target-service "${1:-}" \
  --replace-service "${2:-}" \
  --print-summary
' bash "${target_service}" "${replace_service}"
