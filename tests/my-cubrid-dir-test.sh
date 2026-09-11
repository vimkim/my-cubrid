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
    "$test_root/home/gh/cb")
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
    "$test_root/home/gh/cb"
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

test_list
test_pull_all
test_pull_continues_after_failure
printf 'PASS: my-cubrid-dir\n'
