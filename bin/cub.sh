#!/usr/bin/env bash
# Compatibility shortcut: choose a worktree, load cub-workenv, run native cubrid.
set -euo pipefail
branch="" preset=""
while getopts ':b:p:' option; do
  case "$option" in
    b) branch="$OPTARG" ;;
    p) preset="$OPTARG" ;;
    *) printf 'Usage: cub.sh -b WORKTREE_NAME -p PRESET COMMAND [ARGS...]\n' >&2; exit 64 ;;
  esac
done
shift $((OPTIND - 1))
[[ -n "$branch" && -n "$preset" && $# -gt 0 ]] || exit 64
source "$(dirname -- "$0")/cub-env.sh" -b "$branch" -p "$preset"
cd -- "${CUB_WORKENV_WORKTREE_ROOT:-$HOME/gh/cb}/$branch"
exec "$CUBRID/bin/cubrid" "$@"
