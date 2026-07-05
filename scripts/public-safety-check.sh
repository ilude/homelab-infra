#!/usr/bin/env bash
set -euo pipefail

tracked_file=".public-safety-tracked.$$"
ignored_file=".public-safety-ignored.$$"
cleanup() {
  rm -f -- "${tracked_file}" "${ignored_file}"
}
trap cleanup EXIT HUP INT TERM

git ls-files >"${tracked_file}"
: >"${ignored_file}"
for path in \
  scaffold/.env.example \
  scaffold/terraform.tfvars \
  scaffold/dns-records.local.json \
  scaffold/ansible/inventory/local.yml \
  settings.example.json; do
  if git check-ignore -q -- "${path}"; then
    printf '%s\n' "${path}" >>"${ignored_file}"
  fi
done

scripts/python.sh scripts/public-safety-check.py \
  --tracked-files "${tracked_file}" \
  --ignored-files "${ignored_file}"
