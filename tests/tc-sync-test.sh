#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_AUTHOR_NAME="TC Sync Test" GIT_COMMITTER_NAME="TC Sync Test"
export GIT_AUTHOR_EMAIL="test@example.invalid" GIT_COMMITTER_EMAIL="test@example.invalid"
branch=tc/pr-6864

for scenario in worktree dirty-worktree ordinary remote-only
do
  root="$test_root/$scenario"
  mkdir -p "$root"
  for kind in public private
  do
    directory="$root/$kind"
    git init --quiet --bare "$directory.git"
    git init --quiet --initial-branch=develop "$directory"
    git -C "$directory" remote add origin "$directory.git"
    git -C "$directory" commit --quiet --allow-empty -m base
    git -C "$directory" branch "$branch"
    git -C "$directory" push --quiet origin develop "$branch"
    git -C "$directory" commit --quiet --allow-empty -m update
    git -C "$directory" push --quiet origin develop
    case "$scenario" in
      worktree|dirty-worktree)
        git -C "$directory" worktree add --quiet "$directory linked worktree" "$branch"
        ;;
      remote-only) git -C "$directory" branch -D "$branch" >/dev/null ;;
    esac
  done

  if [[ "$scenario" == dirty-worktree ]]; then
    touch "$root/private linked worktree/untracked"
  elif [[ "$scenario" == worktree ]]; then
    # An unrelated checkout's edits must not prevent syncing the target.
    touch "$root/public/untracked"
  fi

  if output="$(CUBRID_TESTCASES_DIR="$root/public" \
    CUBRID_TESTCASES_PRIVATE_EX_DIR="$root/private" \
    bash "$repo_root/bin/cubrid-tc-sync.sh" https://github.com/CUBRID/cubrid/pull/6864 2>&1)"
  then
    [[ "$scenario" != dirty-worktree ]] || { echo 'dirty worktree was accepted' >&2; exit 1; }
  else
    if [[ "$scenario" != dirty-worktree ]]; then
      printf '%s\n' "$output" >&2
      exit 1
    fi
    [[ "$output" == *"worktree has uncommitted or untracked changes: $root/private linked worktree"* ]]
    for kind in public private
    do
      [[ "$(git -C "$root/$kind" rev-parse "$branch")" == "$(git -C "$root/$kind" rev-parse develop^)" ]]
      [[ "$(git --git-dir="$root/$kind.git" rev-parse "$branch")" == "$(git -C "$root/$kind" rev-parse develop^)" ]]
    done
    printf 'ok: dirty target worktree blocks both repositories before sync\n'
    continue
  fi

  for kind in public private
  do
    directory="$root/$kind"
    expected="$(git -C "$directory" rev-parse develop)"
    [[ "$(git --git-dir="$directory.git" rev-parse "$branch")" == "$expected" ]]
    if [[ "$scenario" == worktree ]]; then
      [[ "$(git -C "$directory" branch --show-current)" == develop ]]
      [[ "$(git -C "$directory linked worktree" rev-parse HEAD)" == "$expected" ]]
    else
      [[ "$(git -C "$directory" branch --show-current)" == "$branch" ]]
      [[ "$(git -C "$directory" rev-parse HEAD)" == "$expected" ]]
    fi
  done
  printf 'ok: %s sync updates and pushes both target branches\n' "$scenario"
done
