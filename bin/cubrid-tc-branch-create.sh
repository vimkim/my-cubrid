#!/usr/bin/env bash

set -euo pipefail

readonly OWNER="${CUBRID_TC_OWNER:-CUBRID}"
readonly TC_REPOS=(
  cubrid-testcases
  cubrid-testcases-private-ex
)

usage ()
{
  cat <<'EOF'
Usage: cubrid-tc-branch-create.sh [--dry-run] BASE_BRANCH NEW_BRANCH

Create NEW_BRANCH from BASE_BRANCH in both CUBRID testcase repositories:
  - cubrid-testcases
  - cubrid-testcases-private-ex

Both repositories are validated before either branch is created. The command
refuses to overwrite NEW_BRANCH if it already exists in either repository.

Examples:
  cubrid-tc-branch-create.sh feat/oos tc/pr-7588
  cubrid-tc-branch-create.sh --dry-run develop tc/pr-7588

Requirements:
  - gh must be installed and authenticated
  - the authenticated account must be able to create branches in both repos

Environment overrides (primarily useful for testing):
  CUBRID_TC_OWNER
EOF
}

die ()
{
  printf 'error: %s\n' "$*" >&2
  exit 1
}

validate_branch_name ()
{
  local label="$1"
  local branch="$2"

  git check-ref-format --branch "$branch" >/dev/null 2>&1 \
    || die "$label is not a valid Git branch name: $branch"
}

resolve_branch_sha ()
{
  local repo="$1"
  local branch="$2"

  gh api "repos/${OWNER}/${repo}/git/ref/heads/${branch}" --jq '.object.sha'
}

branch_exists ()
{
  local repo="$1"
  local branch="$2"

  gh api "repos/${OWNER}/${repo}/git/ref/heads/${branch}" >/dev/null 2>&1
}

create_branch ()
{
  local repo="$1"
  local branch="$2"
  local source_sha="$3"

  gh api "repos/${OWNER}/${repo}/git/refs" \
    --method POST \
    --field ref="refs/heads/${branch}" \
    --field sha="$source_sha" \
    >/dev/null
}

main ()
{
  local dry_run=false

  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]
  then
    usage
    exit 0
  fi

  if [[ "${1:-}" == "--dry-run" ]]
  then
    dry_run=true
    shift
  fi

  [[ $# -eq 2 ]] || {
    usage >&2
    exit 2
  }

  local base_branch="$1"
  local new_branch="$2"
  local repo
  local created_repo
  local source_sha
  local -a source_shas=()
  local -a created_repos=()

  command -v git >/dev/null 2>&1 || die "git is required"
  command -v gh >/dev/null 2>&1 || die "gh is required"

  validate_branch_name "BASE_BRANCH" "$base_branch"
  validate_branch_name "NEW_BRANCH" "$new_branch"

  [[ "$base_branch" != "$new_branch" ]] \
    || die "BASE_BRANCH and NEW_BRANCH must be different"

  printf 'Preflighting branches under %s...\n' "$OWNER"
  for repo in "${TC_REPOS[@]}"
  do
    if ! source_sha="$(resolve_branch_sha "$repo" "$base_branch" 2>/dev/null)"
    then
      die "cannot resolve ${OWNER}/${repo}:${base_branch}; check the branch name and repository access"
    fi

    if branch_exists "$repo" "$new_branch"
    then
      die "refusing to overwrite existing branch ${OWNER}/${repo}:${new_branch}"
    fi

    source_shas+=("$source_sha")
    printf '  %-36s %s -> %s (%s)\n' "${OWNER}/${repo}" "$base_branch" "$new_branch" "${source_sha:0:12}"
  done

  if [[ "$dry_run" == true ]]
  then
    printf 'Dry run complete; no branches were created.\n'
    exit 0
  fi

  for repo_index in "${!TC_REPOS[@]}"
  do
    repo="${TC_REPOS[repo_index]}"
    source_sha="${source_shas[repo_index]}"

    if ! create_branch "$repo" "$new_branch" "$source_sha"
    then
      printf 'error: failed to create %s/%s:%s\n' "$OWNER" "$repo" "$new_branch" >&2
      if ((${#created_repos[@]} > 0))
      then
        printf 'Branches already created before the failure:\n' >&2
        for created_repo in "${created_repos[@]}"
        do
          printf '  %s:%s\n' "$created_repo" "$new_branch" >&2
        done
      fi
      exit 1
    fi

    created_repos+=("${OWNER}/${repo}")
    printf 'Created %s/%s:%s\n' "$OWNER" "$repo" "$new_branch"
  done

  printf 'Created %s from %s in both testcase repositories.\n' "$new_branch" "$base_branch"
}

main "$@"
