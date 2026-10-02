#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 2 && $# -le 3 ]] || { printf 'Usage: cubrid-start.sh WORKTREE PRESET [DATABASE]\n' >&2; exit 64; }
here="$(dirname -- "$0")"
"$here/cub.sh" -b "$1" -p "$2" server start "${3:-testdb}"
exec "$here/cub.sh" -b "$1" -p "$2" broker start
