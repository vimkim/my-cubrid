#!/usr/bin/env bash

set -euo pipefail

usage()
{
  cat <<'EOF'
Usage: cubrid-worktree-add.sh NAME NEW_BRANCH BASE_BRANCH

Create ../NAME as a Git worktree with NEW_BRANCH based on BASE_BRANCH.

If NAME contains a CBRD ticket such as CBRD-12345, creation is rejected when
the same ticket appears (case-insensitively) in either a registered worktree
directory name or any sibling directory name.
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

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) \
  || die "current directory is not inside a Git worktree"
parent_dir=$(dirname -- "$repo_root")
target_path="$parent_dir/$name"

ticket=""
if [[ "$name" =~ ([Cc][Bb][Rr][Dd]-[0-9]+) ]]; then
  ticket="${BASH_REMATCH[1],,}"
fi

if [[ -n "$ticket" ]]; then
  declare -a matched_paths=()
  declare -a matched_sources=()
  line=""

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" != worktree\ * ]]; then
      continue
    fi

    worktree_path="${line#worktree }"
    worktree_name="${worktree_path%/}"
    worktree_name="${worktree_name##*/}"
    if [[ "${worktree_name,,}" == *"$ticket"* ]]; then
      matched_sources+=("registered worktree")
      matched_paths+=("$worktree_path")
    fi
  done < <(git -C "$repo_root" worktree list --porcelain)

  while IFS= read -r -d '' sibling_path; do
    sibling_name="${sibling_path##*/}"
    if [[ "${sibling_name,,}" == *"$ticket"* ]]; then
      matched_sources+=("sibling directory")
      matched_paths+=("$sibling_path")
    fi
  done < <(find "$parent_dir" -mindepth 1 -maxdepth 1 -type d -print0)

  if ((${#matched_paths[@]} > 0)); then
    echo "cubrid-worktree-add: refusing to create $target_path" >&2
    echo "The JIRA ticket ${ticket^^} is already present:" >&2
    for ((index = 0; index < ${#matched_paths[@]}; index++)); do
      printf '  [%s] %s\n' "${matched_sources[index]}" "${matched_paths[index]}" >&2
    done
    exit 1
  fi
fi

git -C "$repo_root" worktree add -b "$new_branch" "$target_path" "$base_branch"
