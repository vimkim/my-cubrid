#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT

remote_repo="$test_root/origin.git"
work_repo="$test_root/work"
fake_bin="$test_root/bin"

git init --quiet --bare "$remote_repo"
git init --quiet "$work_repo"
git -C "$work_repo" config user.name "Hook Test"
git -C "$work_repo" config user.email "hook-test@example.invalid"
git -C "$work_repo" commit --quiet --allow-empty --message "base"
git -C "$work_repo" branch --move develop
git -C "$work_repo" remote add origin "$remote_repo"
git -C "$work_repo" push --quiet --set-upstream origin develop
git -C "$work_repo" branch feat/oos
git -C "$work_repo" push --quiet origin feat/oos
git -C "$work_repo" switch --quiet --create topic
git -C "$work_repo" commit --quiet --allow-empty --message "topic"

mkdir -p "$fake_bin"
ln -s "$repo_root/stow/cubrid/lefthook.yml" "$work_repo/lefthook.yml"
ln -s "$repo_root/tests/fixtures/gh" "$fake_bin/gh"

run_hook()
{
  cd "$work_repo"
  PATH="$fake_bin:$PATH" lefthook run pre-push --force --no-auto-install --colors off 2>&1
}

assert_contains()
{
  local output="$1"
  local expected="$2"

  if [[ "$output" != *"$expected"* ]]; then
    printf 'expected output to contain %s, got:\n%s\n' "$expected" "$output" >&2
    exit 1
  fi
}

if output="$(FAKE_PR_BASE="" run_hook)"; then
  printf 'expected an unknown PR base to block the push\n' >&2
  printf '%s\n' "$output" >&2
  exit 1
fi

assert_contains "$output" "Unable to determine PR base for branch 'topic'."

if [[ "$output" == *"Checking that HEAD contains latest origin/develop"* ]]; then
  printf 'hook silently fell back to origin/develop:\n%s\n' "$output" >&2
  exit 1
fi

printf 'ok: unknown PR base is rejected without assuming origin/develop\n'

if output="$(FAKE_GH_ERROR="simulated GitHub CLI failure" run_hook)"; then
  printf 'expected a GitHub CLI failure to block the push\n' >&2
  printf '%s\n' "$output" >&2
  exit 1
fi
assert_contains "$output" "simulated GitHub CLI failure"
assert_contains "$output" "Failed to query GitHub PR base for branch 'topic'."
assert_contains "$output" "git config branch.topic.cubrid-pr-base-branch <base-branch>"
printf 'ok: GitHub CLI failures retain their diagnostic\n'

output="$(FAKE_PR_BASE=feat/oos run_hook)"
assert_contains "$output" "Checking that HEAD contains latest origin/feat/oos"
printf 'ok: GitHub PR base feat/oos is checked\n'

output="$(FAKE_PR_BASE=develop run_hook)"
assert_contains "$output" "Checking that HEAD contains latest origin/develop"
printf 'ok: GitHub PR base develop is checked\n'

git -C "$work_repo" config branch.topic.cubrid-pr-base-branch feat/oos
output="$(FAKE_PR_BASE=develop run_hook)"
assert_contains "$output" "Checking that HEAD contains latest origin/feat/oos"
printf 'ok: branch-local config takes precedence over GitHub PR metadata\n'

git -C "$work_repo" config branch.topic.cubrid-pr-base-branch develop
output="$(
  CUBRID_PR_BASE_REMOTE=origin \
    CUBRID_PR_BASE=feat/oos \
    run_hook
)"
assert_contains "$output" "Checking that HEAD contains latest origin/feat/oos"
printf 'ok: environment override takes precedence over branch-local config\n'
