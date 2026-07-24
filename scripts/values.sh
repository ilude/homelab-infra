#!/usr/bin/env bash
set -euo pipefail

command_name="${1:-}"
values_root="${VALUES_DIR:-values}"
template_dir="${VALUES_TEMPLATE_DIR:-scaffold}"
site="${VALUES_SITE:-}"
values_dir="${values_root}"
if [[ -n "${site}" ]]; then
  if [[ ! "${site}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ || "${site}" == *..* ]]; then
    printf 'VALUES_SITE must be a simple site identifier.\n' >&2
    exit 2
  fi
  values_dir="${values_root}/sites/${site}"
fi

usage() {
  cat <<'USAGE'
Usage: scripts/values.sh <command> [args]

Commands:
  init [remote]      Create values/ from scaffold/ and git init it. If remote is supplied, add it as origin.
  clone <remote>     Clone an existing private values repo into values/.
  status             Show values/ git status.
  check              Verify required values/ files exist.

Environment:
  VALUES_DIR              Override private values directory (default: values).
  VALUES_SITE             Select values/sites/<site> for this operation.
  VALUES_TEMPLATE_DIR     Override scaffold template directory (default: scaffold).
USAGE
}

require_template() {
  if [[ ! -d "${template_dir}" ]]; then
    printf 'Missing template directory: %s\n' "${template_dir}" >&2
    exit 1
  fi
}

require_values() {
  if [[ ! -d "${values_dir}" ]]; then
    printf 'Missing %s. Run just setup or just setup <remote>.\n' "${values_dir}" >&2
    exit 1
  fi
}

copy_if_missing() {
  local src="$1"
  local dest="$2"
  if [[ ! -e "${dest}" ]]; then
    install -d -m 0755 "$(dirname "${dest}")"
    cp "${src}" "${dest}"
  fi
}

case "${command_name}" in
  init)
    remote="${2:-}"
    require_template
    if [[ -e "${values_root}" && ! -d "${values_root}/.git" ]]; then
      printf '%s already exists and is not a git repo. Aborting.\n' "${values_root}" >&2
      exit 1
    fi
    if [[ ! -d "${values_root}" ]]; then
      install -d -m 0755 "${values_root}"
    fi
    install -d -m 0755 "${values_dir}"
    copy_if_missing "${template_dir}/README.md" "${values_root}/README.md"
    copy_if_missing "${template_dir}/.env.example" "${values_dir}/.env"
    copy_if_missing "${template_dir}/terraform.tfvars" "${values_dir}/terraform.tfvars"
    copy_if_missing "${template_dir}/dns-records.local.json" "${values_dir}/dns-records.local.json"
    copy_if_missing "${template_dir}/ansible/inventory/local.yml" "${values_dir}/ansible/inventory/local.yml"
    if [[ -n "${site}" ]]; then
      site_template="${template_dir}/sites/${site}/site.json"
      if [[ ! -f "${site_template}" ]]; then
        printf 'Missing site scaffold: %s\n' "${site_template}" >&2
        exit 1
      fi
      copy_if_missing "${site_template}" "${values_dir}/site.json"
    fi
    if [[ ! -d "${values_root}/.git" ]]; then
      git -C "${values_root}" init
    fi
    if [[ -n "${remote}" ]] && ! git -C "${values_root}" remote get-url origin >/dev/null 2>&1; then
      git -C "${values_root}" remote add origin "${remote}"
    fi
    printf 'Initialized %s. Edit values before planning/applying.\n' "${values_dir}"
    ;;
  clone)
    remote="${2:-}"
    if [[ -z "${remote}" ]]; then
      printf 'Remote URL is required.\n' >&2
      usage >&2
      exit 1
    fi
    if [[ -e "${values_root}" ]]; then
      printf '%s already exists. Aborting.\n' "${values_root}" >&2
      exit 1
    fi
    git clone "${remote}" "${values_root}"
    ;;
  status)
    require_values
    git -C "${values_root}" status --short --branch
    ;;
  check)
    require_values
    missing=0
    for path in .env terraform.tfvars dns-records.local.json ansible/inventory/local.yml; do
      if [[ ! -f "${values_dir}/${path}" ]]; then
        printf 'Missing %s/%s\n' "${values_dir}" "${path}" >&2
        missing=1
      fi
    done
    if [[ "${missing}" -ne 0 ]]; then
      exit 1
    fi
    printf '%s contains required files.\n' "${values_dir}"
    ;;
  -h|--help|help|'')
    usage
    ;;
  *)
    printf 'Unknown command: %s\n' "${command_name}" >&2
    usage >&2
    exit 1
    ;;
esac
