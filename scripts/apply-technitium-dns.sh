#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC2016
scripts/run-infra.sh bash -lc '
set -euo pipefail
: "${TECHNITIUM_API_URL:?TECHNITIUM_API_URL is required in values/.env}"
dns_records_file="${DNS_RECORDS_FILE:-values/dns-records.local.json}"
: "${TECHNITIUM_API_TOKEN:?TECHNITIUM_API_TOKEN is required in values/.env}" # public-safety: allow-secret
if [[ -z "${TECHNITIUM_API_TOKEN}" ]]; then
  printf "Missing TECHNITIUM_API_TOKEN.\n" >&2
  exit 1
fi
python3 infra/opentofu/scripts/apply-technitium-dns.py "${dns_records_file}"
'
