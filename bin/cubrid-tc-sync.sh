#!/usr/bin/env bash

set -euo pipefail

readonly DEFAULT_PUBLIC_TC_DIR="/home/vimkim/gh/tc/cubrid-testcases"
readonly DEFAULT_PRIVATE_TC_DIR="/home/vimkim/cubrid-testcases-private-ex"

readonly PUBLIC_TC_DIR="${CUBRID_TESTCASES_DIR:-$DEFAULT_PUBLIC_TC_DIR}"
readonly PRIVATE_TC_DIR="${CUBRID_TESTCASES_PRIVATE_EX_DIR:-$DEFAULT_PRIVATE_TC_DIR}"

usage ()
{
  cat <<'EOF'
Usage: sync-cubrid-tc.sh <CUBRID PR URL>

Fetch both CUBRID testcase repositories, switch each one to the testcase
branch associated with the PR, and merge origin/develop into that branch.

Example:
  sync-cubrid-tc.sh https://github.com/CUBRID/cubrid/pull/1234

Environment overrides (primarily useful for testing):
  CUBRID_TESTCASES_DIR
  CUBRID_TESTCASES_PRIVATE_EX_DIR
EOF
}

die ()
{
  printf 'error: %s\n' "$*" >&2
  exit 1
}

parse_pr_number ()
{
  local url="$1"

  url="${url%%\?*}"
  url="${url%%#*}"
  url="${url%/}"

  if [[ "$url" =~ ^https://github\.com/CUBRID/cubrid/pull/([0-9]+)$ ]]
  then
    printf '%s\n' "${BASH_REMATCH[1]}"
    return
  fi

  die "expected a CUBRID PR URL such as https://github.com/CUBRID/cubrid/pull/1234"
}

ensure_repository ()
{
  local directory="$1"

  [[ -d "$directory" ]] || die "repository directory does not exist: $directory"
  git -C "$directory" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || die "not a Git worktree: $directory"
  git -C "$directory" remote get-url origin >/dev/null 2>&1 \
    || die "Git remote 'origin' is missing: $directory"
}

fetch_repository ()
{
  local directory="$1"

  printf '\n==> Fetching %s\n' "$directory"
  git -C "$directory" fetch --all --prune
}

ensure_required_refs ()
{
  local directory="$1"
  local branch="$2"

  git -C "$directory" show-ref --verify --quiet refs/remotes/origin/develop \
    || die "origin/develop does not exist after fetch: $directory"

  if ! git -C "$directory" show-ref --verify --quiet "refs/heads/$branch" \
     && ! git -C "$directory" show-ref --verify --quiet "refs/remotes/origin/$branch"
  then
    die "neither $branch nor origin/$branch exists after fetch: $directory"
  fi
}

sync_repository ()
{
  local directory="$1"
  local branch="$2"

  printf '\n==> Syncing %s\n' "$directory"

  if git -C "$directory" show-ref --verify --quiet "refs/heads/$branch"
  then
    git -C "$directory" switch "$branch"
  else
    git -C "$directory" switch --track -c "$branch" "origin/$branch"
  fi

  git -C "$directory" merge origin/develop
  printf '    %s is now at %s\n' "$branch" \
    "$(git -C "$directory" rev-parse --short HEAD)"
}

main ()
{
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]
  then
    usage
    exit 0
  fi

  [[ $# -eq 1 ]] || {
    usage >&2
    exit 2
  }

  local pr_number
  local branch
  pr_number="$(parse_pr_number "$1")"
  branch="tc/pr-$pr_number"

  ensure_repository "$PUBLIC_TC_DIR"
  ensure_repository "$PRIVATE_TC_DIR"

  # Fetch and validate both repositories before changing either worktree.
  fetch_repository "$PUBLIC_TC_DIR"
  fetch_repository "$PRIVATE_TC_DIR"
  ensure_required_refs "$PUBLIC_TC_DIR" "$branch"
  ensure_required_refs "$PRIVATE_TC_DIR" "$branch"

  sync_repository "$PUBLIC_TC_DIR" "$branch"
  sync_repository "$PRIVATE_TC_DIR" "$branch"

  printf '\nSynced %s in both testcase repositories.\n' "$branch"
}

main "$@"
