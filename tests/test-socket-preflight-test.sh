#!/usr/bin/env bash
set -euo pipefail

script="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/bin/cubrid-test-socket-preflight.sh"
export LC_ALL=C

check()
{
  local expected="$1" status=0 output
  shift
  output=$(env -u CUBRID_TMP CUBRID=/opt/cubrid "$@" bash "$script" 2>&1) || status=$?
  if [[ "$status" != "$expected" ]]; then
    printf 'Expected exit %s, got %s: %s\n' "$expected" "$status" "$output" >&2
    exit 1
  fi
  if (( expected != 0 )); then
    [[ "$output" == *'Effective PL socket:'* && "$output" == *'CUBRID_TMP'* ]]
  fi
}

printf -v padding '%088d' 0
# / + 88 bytes + /sp_unittestdb.sock (19) = 108: reject.
check 1 "CUBRID_TMP=/$padding"
# A 107-byte pathname leaves room for the terminating NUL.
check 0 "CUBRID_TMP=/${padding:1}"
check 0 CUBRID_TMP=/tmp/cubrid-test
check 0 CUBRID_TMP=
check 0
check 1 CUBRID_TMP=relative/path
check 1 "CUBRID=/opt/$padding"
check 1 "CUBRID=/opt/$padding" CUBRID_TMP=
check 0 "CUBRID=/opt/$padding" CUBRID_TMP=/tmp/short
# Count encoded bytes, not Unicode characters (89 bytes + 19 suffix).
check 1 "CUBRID_TMP=/$(printf '\303\251%.0s' {1..44})"
printf 'Socket preflight checks passed.\n'
