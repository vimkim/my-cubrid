#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ] || [ ! -d "$1" ]; then
  echo "usage: cubrid-shell-debug.sh TEST_DIR" >&2
  echo "TEST_DIR must contain the shell test's cases/ directory." >&2
  exit 2
fi

test_dir="$1"
fm_conf="$HOME/.CUBRID_SHELL_FM/conf"

if [ ! -f "$fm_conf/cubrid.conf" ]; then
  mkdir -p "$fm_conf"
  if [ -f "${CUBRID:-}/conf/cubrid.conf" ]; then
    src_conf="$CUBRID/conf"
  else
    src_conf="$(pwd)/conf"
  fi
  cp -rf "$src_conf"/* "$fm_conf"/
  echo "[shell-debug] healed empty FM snapshot from $src_conf"
fi

source_conf="$HOME/CTP/conf/shell_ci.conf"
test_conf="$(mktemp /tmp/shell_single.XXXXXX.conf)"
transcript="$(mktemp /tmp/shell_single.XXXXXX.log)"
clean_log="$(mktemp /tmp/shell_single.XXXXXX.clean.log)"
trap 'rm -f "$test_conf" "$clean_log"' EXIT

cp "$source_conf" "$test_conf"
sed -i "s|^scenario=.*|scenario=$test_dir|" "$test_conf"
sed -i 's|^testcase_update_yn=.*|testcase_update_yn=false|' "$test_conf"
sed -i 's|^testcase_exclude_from_file=.*|#&|' "$test_conf"

echo "[shell-debug] scenario=$test_dir"
echo "[shell-debug] conf=$test_conf"
echo "[shell-debug] transcript=$transcript"

set +e
script -qefc "$HOME/CTP/bin/ctp.sh shell -c $test_conf" "$transcript"
ctp_rc=$?
set -e

tr -d '\r' <"$transcript" >"$clean_log"
if grep -Eq '\[TESTCASE\].*\[NOK\]|Total Fail Case:[[:space:]]*[1-9][0-9]*' "$clean_log"; then
  echo "[shell-debug] CTP reported failed shell tests; transcript=$transcript" >&2
  exit 1
fi
if grep -Eq 'Total Execution Case:[[:space:]]*0' "$clean_log"; then
  echo "[shell-debug] CTP executed zero shell tests; check TEST_DIR=$test_dir; transcript=$transcript" >&2
  exit 1
fi
if ! grep -Eq 'Total Execution Case:' "$clean_log"; then
  echo "[shell-debug] CTP summary was not found; transcript=$transcript" >&2
  if [ "$ctp_rc" -eq 0 ]; then
    exit 1
  fi
fi

exit "$ctp_rc"
