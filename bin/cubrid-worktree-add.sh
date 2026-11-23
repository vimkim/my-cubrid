#!/usr/bin/env bash

set -euo pipefail

usage()
{
  cat <<'EOF'
Usage: cubrid-worktree-add.sh NAME NEW_BRANCH BASE_BRANCH

Create ../NAME as a Git worktree with NEW_BRANCH based on BASE_BRANCH.
Delegates to `cubrid-worktree create` without implicit fetch, prepare, or Herdr placement.
EOF
}

die()
{
  echo "cubrid-worktree-add: $*" >&2
  exit 1
}

if (($# != 3)); then
  usage >&2
  exit 2
fi

name="$1"
new_branch="$2"
base_branch="$3"

if ! command -v cubrid-worktree >/dev/null 2>&1; then
  die "cubrid-worktree is not installed on PATH; run 'just install' in ~/gh/cubrid-worktree"
fi

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) \
  || die "current directory is not inside a Git worktree"
parent_dir=$(dirname -- "$repo_root")

exec cubrid-worktree create "$name" \
  --branch "$new_branch" \
  --base "$base_branch" \
  --control-dir "$repo_root" \
  --parent-dir "$parent_dir" \
  --no-fetch \
  --no-prepare \
  --no-herdr
