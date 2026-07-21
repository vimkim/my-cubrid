#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -gt 1 ]; then
  echo "usage: cubrid-oos-isolation-test.sh [CTL_FILE_OR_DIRECTORY]" >&2
  exit 2
fi

ctl_dir="$HOME/cubrid-testtools/CTP/isolation/ctltool"
tc_base="$HOME/cubrid-testcases/isolation"
timeout="${TIMEOUT:-120}"
target="${1:-}"

if [ -n "$target" ] && [ ! -e "$target" ]; then
  echo "not a file or directory: $target" >&2
  exit 2
fi

if [ ! -f "$ctl_dir/qacsql" ] || [ ! -f "$ctl_dir/qactl" ]; then
  echo "Building CTP isolation tools..."
  (cd "$ctl_dir" && make && chmod +x ./*.sh)
fi

if ! cubrid server status 2>/dev/null | grep -q ctldb; then
  echo "Preparing ctldb..."
  (cd "$ctl_dir" && sh prepare.sh qacsql ctldb nolog)
fi

if [ -n "$target" ] && [ -f "$target" ]; then
  (cd "$ctl_dir" && sh runone.sh "$target" "$timeout" 2>&1) | grep -E 'flag:|elapse:'
  exit "${PIPESTATUS[0]}"
fi

if [ -n "$target" ] && [ -d "$target" ]; then
  search_dir="$target"
else
  search_dir="$tc_base/_01_ReadCommitted/issues/cbrd_26517_oos"
fi

pass=0
fail=0
total=0
for ctl in "$search_dir"/*.ctl "$tc_base"/_02_RepeatableRead/issues/cbrd_26517_oos/*.ctl; do
  [ -f "$ctl" ] || continue
  total=$((total + 1))
  name="$(basename "$ctl" .ctl)"
  result="$(cd "$ctl_dir" && sh runone.sh "$ctl" "$timeout" 2>&1 | grep 'flag:' | head -1 || true)"
  if grep -q 'OK' <<<"$result"; then
    echo "  OK  $name"
    pass=$((pass + 1))
  else
    echo "  NOK $name"
    fail=$((fail + 1))
  fi
done

echo "---"
echo "$pass/$total passed"
[ "$fail" -eq 0 ]
