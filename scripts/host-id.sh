#!/usr/bin/env bash
set -euo pipefail

kind="${1:-}"
case "${kind}" in
  uid|gid) ;;
  *)
    printf 'usage: %s uid|gid\n' "${0##*/}" >&2
    exit 2
    ;;
esac

# Docker Desktop bind mounts on Windows do not preserve useful POSIX uid/gid
# ownership. Keep the image default there instead of creating very large MSYS ids.
uname_s="$(uname -s 2>/dev/null || printf unknown)"
case "${uname_s}" in
  MINGW*|MSYS*|CYGWIN*)
    printf '1000\n'
    exit 0
    ;;
esac

if [[ "${kind}" == "uid" ]]; then
  id -u
else
  id -g
fi
