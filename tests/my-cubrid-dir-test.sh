#!/usr/bin/env bash
set -euo pipefail

readonly repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly cli="$repo_root/bin/my-cubrid-dir"
readonly test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT

fail()
{
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_equal()
{
  local expected="$1"
  local actual="$2"

  [[ "$actual" == "$expected" ]] || fail "expected '$expected', got '$actual'"
}

test_list()
{
  local actual
  local expected

  expected=$(printf '%s\n' \
    "$test_root/home/my-cubrid" \
    "$test_root/home/gh/my-cubrid-docs" \
    "$test_root/home/gh/my-cubrid-jira" \
    "$test_root/home/gh/my-cubrid-skills" \
    "$test_root/home/gh/cubrid-oos-context" \
    "$test_root/home/gh/cb/develop")
  actual=$(HOME="$test_root/home" "$cli" list)

  assert_equal "$expected" "$actual"
}

test_pull_all()
{
  local path
  local actual
  local expected
  local -a paths=(
    "$test_root/home/my-cubrid"
    "$test_root/home/gh/my-cubrid-docs"
    "$test_root/home/gh/my-cubrid-jira"
    "$test_root/home/gh/my-cubrid-skills"
    "$test_root/home/gh/cubrid-oos-context"
    "$test_root/home/gh/cb/develop"
  )

  mkdir -p "$test_root/bin"
  for path in "${paths[@]}"; do
    mkdir -p "$path"
  done

  cat >"$test_root/bin/git" <<'EOF'
#!/usr/bin/env bash
if [[ "$3" == "rev-parse" ]]; then
  exit 0
fi
printf '%s\n' "$*" >>"$GIT_CALLS"
if [[ "$1" == "clone" ]]; then
  mkdir -p -- "$3"
fi
EOF
  chmod +x "$test_root/bin/git"

  GIT_CALLS="$test_root/git-calls" HOME="$test_root/home" \
    PATH="$test_root/bin:$PATH" "$cli" pull >/dev/null
  actual=$(<"$test_root/git-calls")

  expected=""
  for path in "${paths[@]}"; do
    if [[ -n "$expected" ]]; then
      expected+=$'\n'
    fi
    expected+="-C $path pull --ff-only"
  done

  assert_equal "$expected" "$actual"
}

test_pull_continues_after_failure()
{
  local output

  rm -rf -- "$test_root/home/gh/my-cubrid-jira"
  if output=$(GIT_CALLS="$test_root/git-calls-failure" HOME="$test_root/home" \
    PATH="$test_root/bin:$PATH" "$cli" pull 2>&1); then
    fail 'pull succeeded with a missing configured directory'
  fi

  [[ "$output" == *"missing directory: $test_root/home/gh/my-cubrid-jira"* ]] || \
    fail 'missing directory was not reported'
  [[ "$output" == *'1 of 6 repositories failed'* ]] || \
    fail 'failure summary was not reported'
  [[ "$(wc -l <"$test_root/git-calls-failure")" -eq 5 ]] || \
    fail 'pull did not continue after the missing directory'
}

test_pull_clones_missing_repositories_after_confirmation()
{
  local actual
  local expected
  local output
  local prompt

  rm -rf -- \
    "$test_root/home/gh/my-cubrid-docs" \
    "$test_root/home/gh/my-cubrid-jira"

  if ! output=$(printf 'y\n' | GIT_CALLS="$test_root/git-calls-clone" \
    HOME="$test_root/home" PATH="$test_root/bin:$PATH" "$cli" pull 2>&1); then
    fail 'pull failed after confirming clones'
  fi

  prompt=$(printf 'Missing repositories:\n  %s\n  %s\n\nClone 2 missing repositories? [y/N] ' \
    "$test_root/home/gh/my-cubrid-docs" \
    "$test_root/home/gh/my-cubrid-jira")
  [[ "$output" == *"$prompt"* ]] || \
    fail 'missing repositories were not listed immediately before the clone prompt'

  [[ -d "$test_root/home/gh/my-cubrid-docs" ]] || \
    fail 'my-cubrid-docs was not cloned'
  [[ -d "$test_root/home/gh/my-cubrid-jira" ]] || \
    fail 'my-cubrid-jira was not cloned'

  actual=$(<"$test_root/git-calls-clone")
  expected=$(printf '%s\n' \
    "-C $test_root/home/my-cubrid pull --ff-only" \
    "-C $test_root/home/gh/my-cubrid-skills pull --ff-only" \
    "-C $test_root/home/gh/cubrid-oos-context pull --ff-only" \
    "-C $test_root/home/gh/cb/develop pull --ff-only" \
    "clone https://github.com/vimkim/my-cubrid-docs $test_root/home/gh/my-cubrid-docs" \
    "clone https://github.com/vimkim/my-cubrid-jira $test_root/home/gh/my-cubrid-jira")
  assert_equal "$expected" "$actual"
}

test_list
test_pull_all
test_pull_continues_after_failure
test_pull_clones_missing_repositories_after_confirmation
printf 'PASS: my-cubrid-dir\n'
