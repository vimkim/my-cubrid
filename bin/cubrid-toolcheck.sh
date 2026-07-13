#!/usr/bin/env bash

# Report the local and remote health of valued CUBRID work repositories.

set -uo pipefail

# Prevent read-only Git commands such as status from refreshing the index.
export GIT_OPTIONAL_LOCKS=0

readonly repos=(
  "$HOME/my-cubrid"
  "$HOME/gh/my-cubrid-docs"
  "$HOME/gh/my-cubrid-jira"
  "$HOME/gh/my-cubrid-skills"
  "$HOME/gh/cubrid-oos-context"
)

color_reset=''
color_bold=''
color_green=''
color_yellow=''
color_red=''
if [[ -t 1 && ${TERM:-dumb} != dumb && -z ${NO_COLOR+x} ]]; then
  color_reset=$'\033[0m'
  color_bold=$'\033[1m'
  color_green=$'\033[32m'
  color_yellow=$'\033[33m'
  color_red=$'\033[31m'
fi

remote_check_root="$(mktemp -d "${TMPDIR:-/tmp}/check-valued-repos.XXXXXX")" || {
  printf 'error: could not create temporary directory for remote checks\n' >&2
  exit 2
}
trap 'rm -rf -- "$remote_check_root"' EXIT HUP INT TERM

print_row() {
  local color="$1"
  local name="$2"
  local changes="$3"
  local unpushed="$4"
  local pull="$5"
  local tracking="$6"

  printf '%b%-20s%b  %-9s  %-12s  %-12s  %s\n' \
    "$color" "$name" "$color_reset" "$changes" "$unpushed" "$pull" "$tracking"
}

has_attention=0
has_error=0
repo_index=0

printf '%b%-20s  %-9s  %-12s  %-12s  %s%b\n' "$color_bold" \
  'REPOSITORY' 'CHANGES' 'UNPUSHED' 'PULL' 'BRANCH / UPSTREAM' "$color_reset"
printf '%-20s  %-9s  %-12s  %-12s  %s\n' \
  '--------------------' '---------' '------------' '------------' '-----------------'

for repo in "${repos[@]}"; do
  ((repo_index += 1))
  name="${repo##*/}"
  changed_entries=()
  repo_color="$color_green"

  if [[ ! -d "$repo" ]]; then
    print_row "$color_red" "$name" 'UNKNOWN' 'UNKNOWN' 'UNKNOWN' "missing: $repo"
    has_error=1
    continue
  fi

  if ! git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    print_row "$color_red" "$name" 'UNKNOWN' 'UNKNOWN' 'UNKNOWN' 'not a Git worktree'
    has_error=1
    continue
  fi

  if ! status="$(git -C "$repo" status --porcelain=v1 --untracked-files=all 2>/dev/null)"; then
    print_row "$color_red" "$name" 'UNKNOWN' 'UNKNOWN' 'UNKNOWN' 'could not read Git status'
    has_error=1
    continue
  fi
  if [[ -n "$status" ]]; then
    mapfile -t changed_entries <<<"$status"
    change_count=${#changed_entries[@]}
    changes="YES ($change_count)"
    has_attention=1
    repo_color="$color_yellow"
  else
    changes='no'
  fi

  branch="$(git -C "$repo" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  if [[ -z "$branch" ]]; then
    short_head="$(git -C "$repo" rev-parse --short HEAD 2>/dev/null || printf '?')"
    branch="detached@$short_head"
  fi

  upstream="$(git -C "$repo" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
  if [[ -z "$upstream" ]]; then
    unpushed='UNKNOWN'
    pull='UNKNOWN'
    tracking="$branch / no upstream"
    has_error=1
    repo_color="$color_red"
  else
    remote="$(git -C "$repo" config --get "branch.$branch.remote" 2>/dev/null || true)"
    merge_ref="$(git -C "$repo" config --get "branch.$branch.merge" 2>/dev/null || true)"
    remote_url="$(git -C "$repo" remote get-url "$remote" 2>/dev/null || true)"
    head_oid="$(git -C "$repo" rev-parse HEAD 2>/dev/null || true)"
    common_dir="$(git -C "$repo" rev-parse --git-common-dir 2>/dev/null || true)"
    if [[ -n "$common_dir" && "$common_dir" != /* ]]; then
      common_dir="$repo/$common_dir"
    fi
    if [[ -n "$common_dir" ]]; then
      common_dir="$(cd -- "$common_dir" 2>/dev/null && pwd -P || true)"
    fi

    check_repo="$remote_check_root/$repo_index.git"
    remote_check_ok=1
    if [[ -z "$remote" || -z "$merge_ref" || -z "$remote_url" || -z "$head_oid" || -z "$common_dir" ]]; then
      remote_check_ok=0
    elif ! git init --quiet --bare "$check_repo" >/dev/null 2>&1; then
      remote_check_ok=0
    elif ! GIT_ALTERNATE_OBJECT_DIRECTORIES="$common_dir/objects" \
      git -C "$check_repo" update-ref refs/check/local "$head_oid" 2>/dev/null; then
      remote_check_ok=0
    elif ! GIT_ALTERNATE_OBJECT_DIRECTORIES="$common_dir/objects" GIT_TERMINAL_PROMPT=0 \
      git -C "$check_repo" fetch --quiet --no-tags --no-write-fetch-head \
        "$remote_url" "$merge_ref:refs/check/remote" >/dev/null 2>&1; then
      remote_check_ok=0
    fi

    if ((remote_check_ok)); then
      counts="$(GIT_ALTERNATE_OBJECT_DIRECTORIES="$common_dir/objects" \
        git -C "$check_repo" rev-list --left-right --count \
          refs/check/local...refs/check/remote 2>/dev/null || true)"
      read -r ahead behind <<<"$counts"
    else
      ahead="$(git -C "$repo" rev-list --count "$upstream"..HEAD 2>/dev/null || true)"
      behind=''
    fi

    if [[ -z "$ahead" || -z "$behind" ]]; then
      unpushed='UNKNOWN'
      pull='UNKNOWN'
      tracking="$branch / $upstream (remote check failed)"
      has_error=1
      repo_color="$color_red"
    else
      if ((ahead > 0)); then
        unpushed="YES ($ahead)"
        has_attention=1
        repo_color="$color_yellow"
      else
        unpushed='no'
      fi
      if ((behind > 0)); then
        pull="YES ($behind)"
        has_attention=1
        repo_color="$color_yellow"
      else
        pull='no'
      fi
      if ((ahead > 0 && behind > 0)); then
        tracking="$branch / $upstream (diverged)"
        repo_color="$color_red"
      else
        tracking="$branch / $upstream"
      fi
    fi
  fi

  print_row "$repo_color" "$name" "$changes" "$unpushed" "$pull" "$tracking"

  changed_count=${#changed_entries[@]}
  if ((changed_count > 0)); then
    shown_count=$((changed_count < 5 ? changed_count : 5))
    printf '  └─ changed paths (%d; showing %d)\n' "$changed_count" "$shown_count"
    for ((i = 0; i < shown_count; i++)); do
      if ((i + 1 == shown_count && shown_count == changed_count)); then
        connector='└─'
      else
        connector='├─'
      fi
      printf '     %s %s\n' "$connector" "${changed_entries[i]}"
    done
    if ((changed_count > shown_count)); then
      printf '     └─ … %d more\n' "$((changed_count - shown_count))"
    fi
  fi
done

printf '\nRemote checks use isolated temporary Git storage; the monitored repositories are not modified.\n'
if [[ -n "$color_green" ]]; then
  printf 'Colors: %bgreen%b clean · %byellow%b action needed · %bred%b error or divergence\n' \
    "$color_green" "$color_reset" "$color_yellow" "$color_reset" "$color_red" "$color_reset"
fi

if ((has_error)); then
  exit 2
fi
if ((has_attention)); then
  exit 1
fi
exit 0
