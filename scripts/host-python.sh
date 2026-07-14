#!/usr/bin/env bash
set -euo pipefail

setup_guidance() {
  printf '%s\n' \
    'Install CPython 3.11 or newer from Python.org, winget install --exact --id Python.Python.3.13, or your platform package manager.' >&2
}

if ! command -v bash >/dev/null 2>&1; then
  printf '%s\n' 'Git Bash or another Bash installation is required for this workflow.' >&2
  exit 1
fi

probe=('-c' 'import platform, sys; raise SystemExit(sys.version_info < (3, 11) or platform.python_implementation() != "CPython")')
platform_name="$(uname -s 2>/dev/null || true)"
if [[ "${platform_name}" =~ ^(MINGW|MSYS|CYGWIN) ]]; then
  for version in 3.13 3.12 3.11; do
    if command -v py >/dev/null 2>&1 && py "-${version}" "${probe[@]}" >/dev/null 2>&1; then
      exec py "-${version}" "$@"
    fi
  done
else
  for executable in python3.13 python3.12 python3.11 python3 python; do
    if command -v "${executable}" >/dev/null 2>&1 && "${executable}" "${probe[@]}" >/dev/null 2>&1; then
      exec "${executable}" "$@"
    fi
  done
fi

setup_guidance
exit 1
