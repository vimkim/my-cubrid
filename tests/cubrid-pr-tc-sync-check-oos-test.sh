#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_AUTHOR_NAME="OOS TC Sync Test" GIT_COMMITTER_NAME="OOS TC Sync Test"
export GIT_AUTHOR_EMAIL="test@example.invalid" GIT_COMMITTER_EMAIL="test@example.invalid"

feature_branch=feature/oos-merge
pr_branch=tc/pr-7990

create_repository ()
{
  local root="$1"
  local kind="$2"
  local scenario="$3"
  local directory="$root/$kind"

  git init --quiet --bare "$directory.git"
  git init --quiet --initial-branch=develop "$directory"
  git -C "$directory" remote add origin "$directory.git"
  git -C "$directory" commit --quiet --allow-empty -m base
  git -C "$directory" branch "$feature_branch"
  git -C "$directory" branch "$pr_branch"

  case "$scenario" in
    equal)
      ;;
    feature-ahead)
      git -C "$directory" switch --quiet "$feature_branch"
      git -C "$directory" commit --quiet --allow-empty -m feature-update
      ;;
    pr-ahead)
      git -C "$directory" switch --quiet "$pr_branch"
      git -C "$directory" commit --quiet --allow-empty -m forbidden-pr-update
      ;;
    diverged)
      git -C "$directory" switch --quiet "$feature_branch"
      git -C "$directory" commit --quiet --allow-empty -m feature-update
      git -C "$directory" switch --quiet "$pr_branch"
      git -C "$directory" commit --quiet --allow-empty -m pr-update
      ;;
    *)
      printf 'unknown scenario: %s\n' "$scenario" >&2
      exit 1
      ;;
  esac

  git -C "$directory" push --quiet origin "$feature_branch" "$pr_branch"
}

create_pair ()
{
  local root="$1"
  local public_scenario="$2"
  local private_scenario="$3"

  mkdir -p "$root"
  create_repository "$root" public "$public_scenario"
  create_repository "$root" private "$private_scenario"
}

run_sync ()
{
  local root="$1"
  local answer="${2:-}"

  if [[ -n "$answer" ]]
  then
    printf '%s\n' "$answer" | CUBRID_TESTCASES_DIR="$root/public" \
      CUBRID_TESTCASES_PRIVATE_EX_DIR="$root/private" \
      bash "$repo_root/bin/cubrid-pr-tc-sync-check-oos" 2>&1
  else
    CUBRID_TESTCASES_DIR="$root/public" \
      CUBRID_TESTCASES_PRIVATE_EX_DIR="$root/private" \
      bash "$repo_root/bin/cubrid-pr-tc-sync-check-oos" 2>&1
  fi
}

remote_sha ()
{
  local root="$1"
  local kind="$2"
  local branch="$3"

  git --git-dir="$root/$kind.git" rev-parse "$branch"
}

root="$test_root/equal"
create_pair "$root" equal equal
output="$(run_sync "$root")"
[[ "$output" == *"Both testcase repositories are already synchronized."* ]]
printf 'ok: equal branches require no confirmation or push\n'

root="$test_root/decline"
create_pair "$root" feature-ahead feature-ahead
public_before="$(remote_sha "$root" public "$pr_branch")"
private_before="$(remote_sha "$root" private "$pr_branch")"
output="$(run_sync "$root" n)"
[[ "$output" == *"Cancelled; no branches were changed."* ]]
[[ "$(remote_sha "$root" public "$pr_branch")" == "$public_before" ]]
[[ "$(remote_sha "$root" private "$pr_branch")" == "$private_before" ]]
printf 'ok: declined confirmation leaves both repositories unchanged\n'

root="$test_root/fast-forward"
create_pair "$root" feature-ahead feature-ahead
output="$(run_sync "$root" y)"
for kind in public private
do
  [[ "$(remote_sha "$root" "$kind" "$pr_branch")" == "$(remote_sha "$root" "$kind" "$feature_branch")" ]]
done
[[ "$output" == *"Synchronized tc/pr-7990 to feature/oos-merge in both testcase repositories."* ]]
printf 'ok: confirmation fast-forwards and verifies both repositories\n'

root="$test_root/reverse"
create_pair "$root" feature-ahead pr-ahead
public_before="$(remote_sha "$root" public "$pr_branch")"
if output="$(run_sync "$root" y)"
then
  printf 'reverse-direction history was accepted\n' >&2
  exit 1
fi
[[ "$output" == *"tc/pr-7990 is ahead of feature/oos-merge; move those edits to feature/oos-merge first"* ]]
[[ "$(remote_sha "$root" public "$pr_branch")" == "$public_before" ]]
printf 'ok: reverse-direction edit blocks both repositories before push\n'

root="$test_root/diverged"
create_pair "$root" equal diverged
if output="$(run_sync "$root" y)"
then
  printf 'diverged history was accepted\n' >&2
  exit 1
fi
[[ "$output" == *"feature/oos-merge and tc/pr-7990 have diverged; cannot fast-forward"* ]]
printf 'ok: diverged history is rejected\n'
