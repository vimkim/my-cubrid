#!/usr/bin/env bash
set -euo pipefail

script="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/bin/cubrid-test-socket-preflight.sh"
export LC_ALL=C

work="$(mktemp -d)"
trap '/bin/rm -rf "${work:?}"' EXIT

build_dir="$work/build"
mkdir -p "$build_dir/unit_tests/oos"
cat > "$build_dir/unit_tests/oos/CTestTestfile.cmake" <<'EOF'
add_test([=[oos_setup_server_crash_db]=] "/usr/bin/cmake" "-E" "env" "bash" "/src/unit_tests/oos/scripts/setup_isolated_db.sh" "oosservercrashdb")
add_test([=[oos_setup_db]=] "/usr/bin/cmake" "-E" "env" "bash" "/src/unit_tests/oos/scripts/setup_unittestdb.sh")
EOF

# check STATUS STDOUT [BUILD_DIR] -- ENV...
check()
{
  local expected_status="$1" expected_stdout="$2" dir="$3" status=0 stdout stderr
  shift 4
  stdout=$(env -u CUBRID_TMP CUBRID=/opt/cubrid "$@" bash "$script" ${dir:+"$dir"} 2>"$work/stderr") || status=$?
  stderr="$(cat "$work/stderr")"
  if [[ "$status" != "$expected_status" ]]; then
    printf 'Expected exit %s, got %s (env: %s): %s\n' "$expected_status" "$status" "$*" "$stderr" >&2
    exit 1
  fi
  if [[ ! "$stdout" =~ ^${expected_stdout}$ ]]; then
    printf 'Expected stdout /%s/, got "%s" (env: %s)\n' "$expected_stdout" "$stdout" "$*" >&2
    exit 1
  fi
  if (( expected_status != 0 )); then
    [[ "$stderr" == *'Effective PL socket:'* && "$stderr" == *'CUBRID_TMP'* ]]
  fi
}

short='/tmp/cubrid-sock-[0-9a-f]{10}'
printf -v padding '%088d' 0

# An explicit CUBRID_TMP is used as given. / + 88 bytes + /sp_unittestdb.sock (19) = 108: reject.
check 1 '' '' -- "CUBRID_TMP=/$padding"
# A 107-byte pathname leaves room for the terminating NUL.
check 0 '' '' -- "CUBRID_TMP=/${padding:1}"
check 0 '' '' -- CUBRID_TMP=/tmp/cubrid-test
check 1 '' '' -- CUBRID_TMP=relative/path
# Count encoded bytes, not Unicode characters (89 bytes + 19 suffix).
check 1 '' '' -- "CUBRID_TMP=/$(printf '\303\251%.0s' {1..44})"
# The longest fixture database decides: the same CUBRID_TMP fits unittestdb but not oosservercrashdb.
printf -v pad82 '%082d' 0
check 0 '' '' -- "CUBRID_TMP=/$pad82"
check 1 '' "$build_dir" -- "CUBRID_TMP=/$pad82"

# Without CUBRID_TMP, a default directory that fits needs nothing.
check 0 '' '' --
check 0 '' '' -- CUBRID_TMP=
check 0 '' "$build_dir" --
# The 2026-11-16 failure: the default socket of oosservercrashdb is 108 bytes, unittestdb's is 101.
release=/home/vimkim/.cub/install/CBRD-27781-release-check/release_gcc_unit
check 0 '' '' -- "CUBRID=$release"
check 0 "$short" "$build_dir" -- "CUBRID=$release"
check 0 "$short" '' -- "CUBRID=/opt/$padding"
check 0 "$short" '' -- "CUBRID=/opt/$padding" CUBRID_TMP=
# The short directory is stable for one installation and differs between installations.
a="$(env -u CUBRID_TMP CUBRID="/opt/$padding" bash "$script" 2>/dev/null)"
b="$(env -u CUBRID_TMP CUBRID="/opt/$padding" bash "$script" 2>/dev/null)"
c="$(env -u CUBRID_TMP CUBRID="/opt/x$padding" bash "$script" 2>/dev/null)"
[[ "$a" == "$b" && "$a" != "$c" ]] || { printf 'Short directory is not stable per installation: %s %s %s\n' "$a" "$b" "$c" >&2; exit 1; }
printf 'Socket preflight checks passed.\n'
