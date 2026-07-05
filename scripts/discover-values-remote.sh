#!/usr/bin/env bash
set -euo pipefail

explicit_remote="${1:-}"
settings_file="${INFRA_SETTINGS_FILE:-settings.local.json}"
repo_name="${VALUES_REPO_NAME:-homelab-infra-values}"
default_owner="${VALUES_REPO_OWNER:-mike}"

if [[ -n "${explicit_remote}" ]]; then
  printf '%s\n' "${explicit_remote}"
  exit 0
fi

settings_remote="$(scripts/python.sh scripts/settings.py values-remote)"
if [[ -n "${settings_remote}" ]]; then
  printf '%s\n' "${settings_remote}"
  exit 0
fi

if [[ ! -t 0 || ! -t 1 ]]; then
  exit 0
fi

printf 'Base domain for existing Forgejo values repo discovery (blank to skip): '
IFS= read -r domain
if [[ -z "${domain}" ]]; then
  exit 0
fi

domain="${domain#git.}"
forgejo_host="git.${domain}"
printf 'Values repo owner [%s]: ' "${default_owner}"
IFS= read -r owner
owner="${owner:-${default_owner}}"
remote="git@${forgejo_host}:${owner}/${repo_name}.git"

printf 'Checking %s...\n' "${remote}"
if ! git ls-remote --exit-code "${remote}" HEAD >/dev/null 2>&1; then
  printf 'No accessible values repo found at %s. Continuing with scaffold setup.\n' "${remote}" >&2
  exit 0
fi

export SETTINGS_FILE="${settings_file}"
export VALUES_REMOTE="${remote}"
scripts/python.sh - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

path = Path(os.environ["SETTINGS_FILE"])
remote = os.environ["VALUES_REMOTE"]
if path.exists():
    data = json.loads(path.read_text(encoding="utf-8"))
else:
    data = {}
if not isinstance(data, dict):
    raise SystemExit(f"{path} must contain a JSON object")
values_repo = data.setdefault("values_repo", {})
if not isinstance(values_repo, dict):
    raise SystemExit(f"{path}: values_repo must be an object")
values_repo["remote"] = remote
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY

printf '%s\n' "${remote}"
