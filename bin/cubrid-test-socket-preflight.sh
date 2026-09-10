#!/usr/bin/env bash

# The configured OOS test fixtures use the database name unittestdb.
set -euo pipefail
export LC_ALL=C

socket_dir="${CUBRID_TMP:-${CUBRID:?CUBRID is required}/var/CUBRID_SOCK}"
socket_path="$socket_dir/sp_unittestdb.sock"
reason=""

if [[ "$socket_dir" != /* ]]; then
  reason="The socket directory must be an absolute path."
elif [[ -n "${CUBRID_TMP:-}" ]] && (( ${#CUBRID_TMP} > 96 )); then
  reason="CUBRID_TMP exceeds CUBRID's 96-byte directory limit."
elif (( ${#socket_path} > 107 )); then
  reason="The PL socket path exceeds the 107-byte Unix socket pathname limit (108 bytes including the terminating NUL)."
fi

if [[ -n "$reason" ]]; then
  printf 'CUBRID test preflight failed: %s\n' "$reason" >&2
  if [[ -n "${CUBRID_TMP:-}" ]]; then
    printf 'CUBRID_TMP: %s (%s bytes)\n' "$CUBRID_TMP" "${#CUBRID_TMP}" >&2
  else
    printf 'CUBRID_TMP is unset or empty; using $CUBRID/var/CUBRID_SOCK.\n' >&2
  fi
  printf 'Effective PL socket: %s (%s bytes)\n' "$socket_path" "${#socket_path}" >&2
  printf 'An overlong path can leave a truncated socket and hang PL server startup.\n' >&2
  printf 'Set CUBRID_TMP to a short, absolute directory unique to this worktree, then retry.\n' >&2
  printf '%s\n' 'Example: export CUBRID_TMP="$(mktemp -d /tmp/cubrid-test.XXXXXX)"' '         just test' >&2
  exit 1
fi
