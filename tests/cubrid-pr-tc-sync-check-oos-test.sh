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
  local source_branch="${4:-$feature_branch}"
  local target_branch="${5:-$pr_branch}"
  local directory="$root/$kind"

  git init --quiet --bare "$directory.git"
  git init --quiet --initial-branch=develop "$directory"
  git -C "$directory" remote add origin "$directory.git"
  git -C "$directory" commit --quiet --allow-empty -m base
  git -C "$directory" branch "$source_branch"
  git -C "$directory" branch "$target_branch"

  case "$scenario" in
    equal)
      ;;
    feature-ahead)
      git -C "$directory" switch --quiet "$source_branch"
      git -C "$directory" commit --quiet --allow-empty -m feature-update
      ;;
    feature-ahead-long)
      git -C "$directory" switch --quiet "$source_branch"
      for commit_number in $(seq 1 30)
      do
        git -C "$directory" commit --quiet --allow-empty \
          -m "feature-update-$commit_number"
      done
      ;;
    pr-ahead)
      git -C "$directory" switch --quiet "$target_branch"
      git -C "$directory" commit --quiet --allow-empty -m forbidden-pr-update
      ;;
    diverged)
      git -C "$directory" switch --quiet "$source_branch"
      git -C "$directory" commit --quiet --allow-empty -m feature-update
      git -C "$directory" switch --quiet "$target_branch"
      git -C "$directory" commit --quiet --allow-empty -m pr-update
      ;;
    *)
      printf 'unknown scenario: %s\n' "$scenario" >&2
      exit 1
      ;;
  esac

  git -C "$directory" push --quiet origin "$source_branch" "$target_branch"
}

create_pair ()
{
  local root="$1"
  local public_scenario="$2"
  local private_scenario="$3"
  local source_branch="${4:-$feature_branch}"
  local target_branch="${5:-$pr_branch}"

  mkdir -p "$root"
  create_repository "$root" public "$public_scenario" "$source_branch" "$target_branch"
  create_repository "$root" private "$private_scenario" "$source_branch" "$target_branch"
}

run_sync ()
{
  local root="$1"
  local answer="${2:-}"
  local source_branch="${3:-$feature_branch}"
  local target_branch="${4:-$pr_branch}"

  if [[ -n "$answer" ]]
  then
    printf '%s\n' "$answer" | CUBRID_TESTCASES_DIR="$root/public" \
      CUBRID_TESTCASES_PRIVATE_EX_DIR="$root/private" \
      "$repo_root/bin/cubrid-pr-tc-sync-check" \
      "$source_branch" "$target_branch" 2>&1
  else
    CUBRID_TESTCASES_DIR="$root/public" \
      CUBRID_TESTCASES_PRIVATE_EX_DIR="$root/private" \
      "$repo_root/bin/cubrid-pr-tc-sync-check" \
      "$source_branch" "$target_branch" 2>&1
  fi
}

run_oos_wrapper ()
{
  local root="$1"

  CUBRID_TESTCASES_DIR="$root/public" \
    CUBRID_TESTCASES_PRIVATE_EX_DIR="$root/private" \
    "$repo_root/bin/cubrid-pr-tc-sync-check-oos" 2>&1
}

remote_sha ()
{
  local root="$1"
  local kind="$2"
  local branch="$3"

  git --git-dir="$root/$kind.git" rev-parse "$branch"
}

if output="$("$repo_root/bin/cubrid-pr-tc-sync-check" same same 2>&1)"
then
  printf 'identical source and target branches were accepted\n' >&2
  exit 1
fi
[[ "$output" == *"SOURCE_BRANCH and TARGET_BRANCH must be different"* ]]
printf 'ok: generic checker rejects an ambiguous branch pair\n'

root="$test_root/equal"
create_pair "$root" equal equal
output="$(run_oos_wrapper "$root")"
[[ "$output" == *"Both testcase repositories are already synchronized."* ]]
[[ "$(grep -c 'branch relationship' <<<"$output")" -eq 2 ]]
[[ "$(grep -c '\[common ancestor\]' <<<"$output")" -eq 2 ]]
[[ "$output" == *"origin/tc/pr-7990"* ]]
[[ "$output" == *"origin/feature/oos-merge"* ]]
printf 'ok: equal branches require no confirmation or push\n'

root="$test_root/custom-branches"
custom_source=release/mock-feature
custom_target=tc/pr-1234
create_pair "$root" feature-ahead feature-ahead "$custom_source" "$custom_target"
output="$(run_sync "$root" n "$custom_source" "$custom_target")"
[[ "$output" == *"needs sync — $custom_target is 1 commit behind $custom_source"* ]]
[[ "$output" == *"source: $custom_source; target: $custom_target"* ]]
[[ "$output" == *"origin/$custom_source"* ]]
[[ "$output" == *"origin/$custom_target"* ]]
printf 'ok: generic checker accepts arbitrary source and target branches\n'

root="$test_root/decline"
create_pair "$root" feature-ahead feature-ahead
public_before="$(remote_sha "$root" public "$pr_branch")"
private_before="$(remote_sha "$root" private "$pr_branch")"
output="$(run_sync "$root" n)"
[[ "$output" == *"Cancelled; no branches were changed."* ]]
[[ "$output" == *"needs sync — tc/pr-7990 is 1 commit behind feature/oos-merge"* ]]
[[ "$(grep -c 'branch relationship' <<<"$output")" -eq 2 ]]
[[ "$output" == *"origin/feature/oos-merge"*"feature-update"* ]]
[[ "$(grep -c '\[common ancestor\]' <<<"$output")" -eq 2 ]]
[[ "$(remote_sha "$root" public "$pr_branch")" == "$public_before" ]]
[[ "$(remote_sha "$root" private "$pr_branch")" == "$private_before" ]]
printf 'ok: declined confirmation leaves both repositories unchanged\n'

root="$test_root/complete-graph"
create_pair "$root" feature-ahead-long equal
output="$(run_sync "$root" n)"
[[ "$output" == *"feature-update-30"* ]]
[[ "$output" == *"feature-update-1"* ]]
[[ "$output" == *"[common ancestor]"*"base"* ]]
printf 'ok: relationship graph includes both tips and the common ancestor\n'

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
[[ "$output" == *"CUBRID/cubrid-testcases"* ]]
[[ "$output" == *"CUBRID/cubrid-testcases-private-ex"* ]]
[[ "$output" == *"origin/feature/oos-merge"*"feature-update"* ]]
[[ "$output" == *"origin/tc/pr-7990"*"forbidden-pr-update"* ]]
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
[[ "$output" == *"branches diverged: tc/pr-7990 is 1 commit ahead and 1 commit behind"* ]]
[[ "$output" == *"origin/feature/oos-merge"*"feature-update"* ]]
[[ "$output" == *"origin/tc/pr-7990"*"pr-update"* ]]
[[ "$output" == *"[common ancestor]"*"base"* ]]
printf 'ok: diverged history is rejected\n'
