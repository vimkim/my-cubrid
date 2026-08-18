#!/usr/bin/env bash

set -euo pipefail

readonly -a DEFAULT_PUBLIC_TC_DIRS=(
  "/home/vimkim/gh/cub-tc/cubrid-testcases"
  "/home/vimkim/gh/tc/cubrid-testcases"
)
readonly -a DEFAULT_PRIVATE_TC_DIRS=(
  "/home/vimkim/gh/cub-tc-private-ex/cubrid-testcases-private-ex"
  "/home/vimkim/cubrid-testcases-private-ex"
)

usage ()
{
  cat <<'EOF'
Usage: cubrid-tc-sync.sh <CUBRID PR URL>

Fetch both CUBRID testcase repositories, switch each one to the testcase
branch associated with the PR, merge origin/develop into that branch, and push
the updated branch to origin.

Example:
  cubrid-tc-sync.sh https://github.com/CUBRID/cubrid/pull/6864

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

resolve_repository_directory ()
{
  local override="$1"
  shift
  local directory

  if [[ -n "$override" ]]
  then
    printf '%s\n' "$override"
    return
  fi

  for directory in "$@"
  do
    if git -C "$directory" rev-parse --is-inside-work-tree >/dev/null 2>&1
    then
      printf '%s\n' "$directory"
      return
    fi
  done

  # Return the preferred path so ensure_repository reports a useful error.
  printf '%s\n' "$1"
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

ensure_clean_worktree ()
{
  local directory="$1"

  [[ -z "$(git -C "$directory" status --porcelain)" ]] \
    || die "worktree has uncommitted or untracked changes: $directory"
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

  # Incorporate any commits pushed from another checkout without creating an
  # accidental merge commit. A diverged local branch stops here for inspection.
  git -C "$directory" merge --ff-only "origin/$branch"
  git -C "$directory" merge origin/develop
  printf '    %s is now at %s\n' "$branch" \
    "$(git -C "$directory" rev-parse --short HEAD)"
}

push_repository ()
{
  local directory="$1"
  local branch="$2"

  printf '\n==> Pushing %s from %s\n' "$branch" "$directory"
  git -C "$directory" push origin "$branch"
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
  local public_tc_dir
  local private_tc_dir
  pr_number="$(parse_pr_number "$1")"
  branch="tc/pr-$pr_number"
  public_tc_dir="$(resolve_repository_directory \
    "${CUBRID_TESTCASES_DIR:-}" "${DEFAULT_PUBLIC_TC_DIRS[@]}")"
  private_tc_dir="$(resolve_repository_directory \
    "${CUBRID_TESTCASES_PRIVATE_EX_DIR:-}" "${DEFAULT_PRIVATE_TC_DIRS[@]}")"

  ensure_repository "$public_tc_dir"
  ensure_repository "$private_tc_dir"
  ensure_clean_worktree "$public_tc_dir"
  ensure_clean_worktree "$private_tc_dir"

  # Fetch and validate both repositories before changing either worktree.
  fetch_repository "$public_tc_dir"
  fetch_repository "$private_tc_dir"
  ensure_required_refs "$public_tc_dir" "$branch"
  ensure_required_refs "$private_tc_dir" "$branch"

  sync_repository "$public_tc_dir" "$branch"
  sync_repository "$private_tc_dir" "$branch"

  push_repository "$public_tc_dir" "$branch"
  push_repository "$private_tc_dir" "$branch"

  printf '\nSynced and pushed %s in both testcase repositories.\n' "$branch"
}

main "$@"
