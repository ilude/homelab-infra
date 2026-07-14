#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  scripts/service-state.sh list
  scripts/service-state.sh backup <service|all>
  scripts/service-state.sh restore <service> values/service-backups/<service>/<archive>.tar.gz
  scripts/service-state.sh restore-if-present <service> [values/service-backups/<service>/<archive>.tar.gz]

Managed service-state archives are private operational state. They are written
under values/service-backups/ in the ignored private values repo.
USAGE
}

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
backup_root="${SERVICE_STATE_BACKUP_ROOT:-/workspace/values/service-backups}"
host_backup_root="${repo_root}/values/service-backups"
service_state_host_acl_enforced=false

secure_local_backup_root() {
  mkdir -p "${host_backup_root}"
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
      command -v cygpath >/dev/null 2>&1 || {
        printf 'cygpath is required to secure private service backups on Windows.\n' >&2
        exit 1
      }
      command -v icacls.exe >/dev/null 2>&1 || {
        printf 'icacls.exe is required to secure private service backups on Windows.\n' >&2
        exit 1
      }
      local windows_path windows_identity
      windows_path="$(cygpath -w "${host_backup_root}")"
      windows_identity="$(whoami.exe | tr -d '\r')"
      MSYS2_ARG_CONV_EXCL='*' icacls.exe "${windows_path}" \
        /inheritance:r \
        /grant:r "${windows_identity}:(OI)(CI)F" \
        '*S-1-5-18:(OI)(CI)F' \
        '*S-1-5-32-544:(OI)(CI)F' \
        /T /C /Q >/dev/null
      service_state_host_acl_enforced=true
      ;;
    *)
      chmod 0700 "${host_backup_root}"
      ;;
  esac
}

if ! jq -e '.services | all(.[]; (.state_capable | type) == "boolean")' infra/services.json >/dev/null; then
  printf 'Every service must declare Boolean state_capable metadata.\n' >&2
  exit 2
fi
mapfile -t state_capable_services < <(
  jq -r '.services | to_entries | map(select(.value.state_capable)) | sort_by(.value.state_order // 999999)[] | .key' infra/services.json |
    tr -d '\r'
)

is_supported_service() {
  local service="$1"
  local item
  for item in "${state_capable_services[@]}"; do
    [[ "${item}" == "${service}" ]] && return 0
  done
  return 1
}

container_path() {
  local input="$1"
  case "${input}" in
    /workspace/*)
      printf '%s\n' "${input}"
      ;;
    /*)
      case "${input}" in
        "${repo_root}"/*)
          printf '/workspace/%s\n' "${input#"${repo_root}"/}"
          ;;
        *)
          printf '%s\n' "${input}"
          ;;
      esac
      ;;
    *)
      printf '/workspace/%s\n' "${input#./}"
      ;;
  esac
}

latest_local_archive() {
  local service="$1"
  local backup_dir="${repo_root}/values/service-backups/${service}"
  if [[ ! -d "${backup_dir}" ]]; then
    return 1
  fi
  find "${backup_dir}" -maxdepth 1 -type f -name "${service}-state-*.tar.gz" \
    ! -name "${service}-state-pre-restore-*.tar.gz" \
    -printf '%T@ %p\n' | sort -nr | awk 'NR == 1 { $1=""; sub(/^ /, ""); print }'
}

validate_restore_file() {
  local service="$1"
  local file="$2"
  case "${file}" in
    "/workspace/values/service-backups/${service}/"*.tar.gz) ;;
    *)
      printf 'Restore archive must be under values/service-backups/%s/ and end in .tar.gz\n' "${service}" >&2
      exit 2
      ;;
  esac
}

service_group() {
  local service="$1"
  scripts/python.sh - "${service}" <<'PY'
import json
import sys
from pathlib import Path

service = sys.argv[1]
registry = json.loads(Path("infra/services.json").read_text(encoding="utf-8"))
try:
    print(registry["services"][service]["inventory"]["group"])
except KeyError as error:
    raise SystemExit(f"No inventory group is registered for service {service!r}.") from error
PY
}

enabled_supported_services() {
  local service
  while IFS= read -r service; do
    if is_supported_service "${service}"; then
      printf '%s\n' "${service}"
    fi
  done < <(scripts/python.sh scripts/settings.py services | tr -d '\r' | tr ' ' '\n')
}

run_playbook() {
  local mode="$1"
  local service="$2"
  local group
  group="$(service_group "${service}")"

  local inventory_args="-i values/ansible/inventory/local.yml -i infra/ansible/inventory/tfvars.py"
  local refresh_direct_access=""
  if [[ "$(jq -r --arg service "${service}" '.services[$service].execution_resource // ""' infra/services.json | tr -d '\r')" == "direct_lxc_known_hosts" ]]; then
    refresh_direct_access="ansible-playbook ${inventory_args} -e direct_access_target_group=${group@Q} infra/ansible/playbooks/direct-access-ready.yml;"
  fi

  if [[ "${mode}" == "backup" ]]; then
    INFRA_COPY_SSH_KEYS="${INFRA_COPY_SSH_KEYS:-true}" \
      SERVICE_STATE_BACKUP_ROOT="${backup_root}" \
      SERVICE_STATE_HOST_ACL_ENFORCED="${service_state_host_acl_enforced}" \
      scripts/run-infra.sh bash -lc \
      "export PATH=/opt/ansible/bin:\$PATH; ${refresh_direct_access} ansible-playbook ${inventory_args} -e service_state_service=${service@Q} -e service_state_hosts=${group@Q} infra/ansible/playbooks/service-state-backup.yml"
  else
    INFRA_COPY_SSH_KEYS="${INFRA_COPY_SSH_KEYS:-true}" \
      SERVICE_STATE_BACKUP_ROOT="${backup_root}" \
      SERVICE_STATE_RESTORE_FILE="${restore_file}" \
      scripts/run-infra.sh bash -lc \
      "export PATH=/opt/ansible/bin:\$PATH; ${refresh_direct_access} ansible-playbook ${inventory_args} -e service_state_service=${service@Q} -e service_state_hosts=${group@Q} infra/ansible/playbooks/service-state-restore.yml"
  fi
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

command_name="$1"
shift

case "${command_name}" in
  list)
    if [[ $# -ne 0 ]]; then
      usage
      exit 2
    fi
    printf 'Supported service-state targets:\n'
    printf '  %s\n' "${state_capable_services[@]}"
    ;;
  backup)
    if [[ $# -ne 1 ]]; then
      usage
      exit 2
    fi
    secure_local_backup_root
    target="$1"
    if [[ "${target}" == "all" ]]; then
      mapfile -t selected_services < <(enabled_supported_services)
      if [[ "${#selected_services[@]}" -eq 0 ]]; then
        printf 'No enabled services have service-state backup definitions.\n' >&2
        exit 1
      fi
      for service in "${selected_services[@]}"; do
        printf 'Backing up %s service state...\n' "${service}" >&2
        run_playbook backup "${service}"
      done
    else
      if ! is_supported_service "${target}"; then
        printf 'Unsupported service-state target: %s\n' "${target}" >&2
        exit 2
      fi
      run_playbook backup "${target}"
    fi
    ;;
  restore)
    if [[ $# -ne 2 ]]; then
      usage
      exit 2
    fi
    service="$1"
    if ! is_supported_service "${service}"; then
      printf 'Unsupported service-state target: %s\n' "${service}" >&2
      exit 2
    fi
    restore_file="$(container_path "$2")"
    validate_restore_file "${service}" "${restore_file}"
    run_playbook restore "${service}"
    ;;
  restore-if-present)
    if [[ $# -lt 1 || $# -gt 2 ]]; then
      usage
      exit 2
    fi
    service="$1"
    if ! is_supported_service "${service}"; then
      printf 'Unsupported service-state target: %s\n' "${service}" >&2
      exit 2
    fi
    if [[ $# -eq 2 ]]; then
      local_restore_file="$2"
      if [[ ! -f "${local_restore_file}" ]]; then
        printf 'No %s service-state archive found at %s; skipping restore.\n' "${service}" "${local_restore_file}" >&2
        exit 0
      fi
    else
      local_restore_file="$(latest_local_archive "${service}" || true)"
      if [[ -z "${local_restore_file}" ]]; then
        printf 'No %s service-state archive found; skipping restore.\n' "${service}" >&2
        exit 0
      fi
    fi
    restore_file="$(container_path "${local_restore_file}")"
    validate_restore_file "${service}" "${restore_file}"
    run_playbook restore "${service}"
    ;;
  *)
    usage
    exit 2
    ;;
esac
