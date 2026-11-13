#!/usr/bin/env bash
# Usage: selftest.sh [cubrid-worktree]
# Commits synthetic changes on e64a04a79a in a temporary detached worktree and checks the verdicts.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
src=$(git -C "${1:-.}" rev-parse --show-toplevel)
check=$here/cubrid-static-check
db=$(realpath "$src/compile_commands.json")
tmp=$(mktemp -d)
wt=$tmp/wt
cleanup() {
  git -C "$src" worktree remove --force "$wt" 2>/dev/null || true
  rm -rf "${tmp:?}"
}
trap cleanup EXIT

git -C "$src" worktree add --detach --quiet "$wt" e64a04a79a
cd "$wt"
f=src/base/fault_injection.c
commit() { git -c user.name=selftest -c user.email=selftest@localhost commit -qam "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; exit 1; }

printf '\n/* cubrid-static-check selftest: a comment-only change */\n' >>"$f"
commit "comment only"
rc=0
"$check" --compile-db "$db" HEAD~1 HEAD >"$tmp/clean.md" || rc=$?
cat "$tmp/clean.md"
[ "$rc" -eq 0 ] || fail "comment-only change exited $rc, expected 0"

mkdir "$tmp/bin"
ln -s "$(command -v lizard)" "$tmp/bin/lizard"
rc=0
PATH="$tmp/bin:/usr/bin:/bin" "$check" --compile-db "$db" --no-cpd --no-clang-tidy HEAD~1 HEAD \
  >"$tmp/notool.md" || rc=$?
[ "$rc" -eq 3 ] || fail "run without cppcheck exited $rc, expected 3"

git mv "$f" src/base/fault_injection_renamed.c
printf '/* renamed */\n' >>src/base/fault_injection_renamed.c
commit "rename with a comment-only edit"
rc=0
"$check" --compile-db "$db" HEAD~1 HEAD >"$tmp/rename.md" || rc=$?
cat "$tmp/rename.md"
[ "$rc" -eq 0 ] || fail "rename with a comment-only edit exited $rc, expected 0"
git mv src/base/fault_injection_renamed.c "$f"
commit "rename back"

{
  printf '\n'
  sed -n '111,154p' "$f" | sed 's/fi_thread_init/fi_thread_init_copy/'
  printf '\nint\nfi_selftest_null (void)\n{\n  int *p = NULL;\n  return *p;\n}\n'
} >>"$f"
commit "copied block and null dereference"
rc=0
"$check" --compile-db "$db" HEAD~1 HEAD >"$tmp/bug.md" || rc=$?
cat "$tmp/bug.md"
[ "$rc" -eq 1 ] || fail "defective change exited $rc, expected 1"
grep -q "fault_injection.c:[0-9]*\` \*\*nullPointer\*\*" "$tmp/bug.md" || fail "nullPointer not reported"
grep -q "fault_injection.c:[0-9-]*\` (new)" "$tmp/bug.md" || fail "copied block not reported as a new clone"
echo "PASS: quiet on comment-only and rename changes, exit 3 without cppcheck, caught nullPointer and the copied block"
