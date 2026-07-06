#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: cleanup-gone-worktrees.sh [options]

Lists Git worktrees whose checked-out branch tracks a missing upstream branch
on one of these remotes: upstream, origin, vk.

By default the script:
  - scans the Git worktree group selected from ~/gh/cb
    (when run from this CUBRID worktree container, ./cubrid is selected)
  - fetches --prune for upstream/origin/vk when those remotes exist
  - prints matching worktrees
  - prompts before deleting all listed worktree directories

Options:
  --base DIR    Scan Git repositories/worktrees below DIR instead
  --all-repos   Scan every Git repository/worktree group below the base directory
  --no-fetch    Do not fetch --prune before checking tracking refs
  --dry-run     List matches but do not prompt or delete
  --yes         Delete without prompting
  -h, --help    Show this help
USAGE
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

base_dir="$HOME/gh/cb"
fetch_prune=1
dry_run=0
assume_yes=0
all_repos=0
target_remotes=(upstream origin vk)

while (($#)); do
  case "$1" in
    --base)
      (($# >= 2)) || die "--base requires a directory"
      base_dir="$2"
      shift 2
      ;;
    --no-fetch)
      fetch_prune=0
      shift
      ;;
    --all-repos)
      all_repos=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --yes)
      assume_yes=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

[[ -d "$base_dir" ]] || die "base directory does not exist: $base_dir"
base_dir="$(cd -- "$base_dir" && pwd -P)"
cd "$base_dir"

is_target_remote() {
  local remote="$1"
  local target

  for target in "${target_remotes[@]}"; do
    [[ "$remote" == "$target" ]] && return 0
  done

  return 1
}

git_common_dir() {
  local repo="$1"
  local common

  common="$(git -C "$repo" rev-parse --git-common-dir 2>/dev/null)" || return 1
  if [[ "$common" != /* ]]; then
    common="$(cd -- "$repo/$common" && pwd -P)"
  else
    common="$(cd -- "$common" && pwd -P)"
  fi

  printf '%s\n' "$common"
}

discover_git_repos() {
  local git_marker repo

  if git -C "$base_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$base_dir" rev-parse --show-toplevel
  fi

  while IFS= read -r -d '' git_marker; do
    repo="${git_marker%/.git}"
    git -C "$repo" rev-parse --show-toplevel 2>/dev/null || true
  done < <(find "$base_dir" -mindepth 1 -maxdepth 2 -name .git -print0)
}

select_default_repo() {
  local repo

  if git -C "$base_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$base_dir" rev-parse --show-toplevel
    return 0
  fi

  repo="$base_dir/cubrid"
  if [[ -e "$repo/.git" ]] && git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$repo" rev-parse --show-toplevel
    return 0
  fi

  discover_git_repos | sort -u | sed -n '1p'
}

process_worktree_record() {
  local control_repo="$1"
  local path="$2"
  local branch="$3"
  local remote merge remote_branch tracking_ref reason

  [[ -n "$path" && -n "$branch" ]] || return 0
  [[ -d "$path" ]] || return 0

  remote="$(git -C "$path" config --get "branch.$branch.remote" 2>/dev/null || true)"
  merge="$(git -C "$path" config --get "branch.$branch.merge" 2>/dev/null || true)"

  [[ -n "$remote" && -n "$merge" ]] || return 0
  is_target_remote "$remote" || return 0
  [[ "$merge" == refs/heads/* ]] || return 0

  remote_branch="${merge#refs/heads/}"
  tracking_ref="refs/remotes/$remote/$remote_branch"

  if git -C "$control_repo" show-ref --verify --quiet "$tracking_ref"; then
    return 0
  fi

  if git -C "$control_repo" remote get-url "$remote" >/dev/null 2>&1; then
    reason="missing tracking ref"
  else
    reason="remote is not configured"
  fi

  stale_paths+=("$path")
  stale_branches+=("$branch")
  stale_upstreams+=("$remote/$remote_branch")
  stale_controls+=("$control_repo")
  stale_reasons+=("$reason")
}

scan_worktrees() {
  local control_repo="$1"
  local path branch line

  path=""
  branch=""

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ -z "$line" ]]; then
      process_worktree_record "$control_repo" "$path" "$branch"
      path=""
      branch=""
      continue
    fi

    case "$line" in
      worktree\ *)
        path="${line#worktree }"
        ;;
      branch\ refs/heads/*)
        branch="${line#branch refs/heads/}"
        ;;
      detached)
        branch=""
        ;;
    esac
  done < <(git -C "$control_repo" worktree list --porcelain)

  process_worktree_record "$control_repo" "$path" "$branch"
}

remove_worktree() {
  local control_repo="$1"
  local path="$2"

  if git -C "$control_repo" worktree remove --force --force "$path"; then
    return 0
  fi

  printf '  git worktree remove failed; deleting directory directly and pruning metadata\n' >&2

  if [[ -d "$path/.git" ]]; then
    printf '  refusing direct rm -rf because %s is a main worktree with a .git directory\n' "$path" >&2
    return 1
  fi

  rm -rf -- "$path"
  git -C "$control_repo" worktree prune
}

declare -A seen_common_dirs=()
declare -a control_repos=()
declare -a candidate_repos=()

if ((all_repos)); then
  while IFS= read -r repo; do
    candidate_repos+=("$repo")
  done < <(discover_git_repos | sort -u)
else
  selected_repo="$(select_default_repo)"
  [[ -n "$selected_repo" ]] || die "no Git repository found below $base_dir"
  candidate_repos+=("$selected_repo")
fi

for repo in "${candidate_repos[@]}"; do
  [[ -n "$repo" && -d "$repo" ]] || continue
  common_dir="$(git_common_dir "$repo")" || continue
  [[ -n "${seen_common_dirs[$common_dir]:-}" ]] && continue

  seen_common_dirs["$common_dir"]=1
  control_repos+=("$repo")
done

((${#control_repos[@]} > 0)) || die "no Git repositories found below $base_dir"

for control_repo in "${control_repos[@]}"; do
  if ((fetch_prune)); then
    for remote in "${target_remotes[@]}"; do
      if git -C "$control_repo" remote get-url "$remote" >/dev/null 2>&1; then
        printf 'Fetching %s in %s...\n' "$remote" "$control_repo" >&2
        git -C "$control_repo" fetch --prune "$remote"
      fi
    done
  fi
done

declare -a stale_paths=()
declare -a stale_branches=()
declare -a stale_upstreams=()
declare -a stale_controls=()
declare -a stale_reasons=()

for control_repo in "${control_repos[@]}"; do
  scan_worktrees "$control_repo"
done

if ((${#stale_paths[@]} == 0)); then
  printf 'No worktrees track missing upstream/origin/vk branches.\n'
  exit 0
fi

printf 'Worktrees tracking missing upstream/origin/vk branches:\n'
for i in "${!stale_paths[@]}"; do
  printf '%2d. %s\n' "$((i + 1))" "${stale_paths[$i]}"
  printf '    branch:   %s\n' "${stale_branches[$i]}"
  printf '    upstream: %s (%s)\n' "${stale_upstreams[$i]}" "${stale_reasons[$i]}"
done

if ((dry_run)); then
  printf '\nDry run: no worktrees were deleted.\n'
  exit 0
fi

if ((!assume_yes)); then
  printf '\nDelete all %d listed worktree directories? Type "delete" to continue: ' "${#stale_paths[@]}"
  read -r answer
  if [[ "$answer" != "delete" ]]; then
    printf 'Aborted; no worktrees were deleted.\n'
    exit 0
  fi
fi

failures=0
for i in "${!stale_paths[@]}"; do
  printf 'Removing %s...\n' "${stale_paths[$i]}"
  if ! remove_worktree "${stale_controls[$i]}" "${stale_paths[$i]}"; then
    printf 'Failed to remove %s\n' "${stale_paths[$i]}" >&2
    failures=$((failures + 1))
  fi
done

if ((failures > 0)); then
  die "$failures worktree(s) could not be removed"
fi

printf 'Removed %d worktree(s).\n' "${#stale_paths[@]}"
