#!/usr/bin/env bash

# Usage: cubrid-test-socket-preflight.sh [BUILD_DIR]
# Prints the CUBRID_TMP value the tests must use, or nothing when the current setting fits.
# CUBRID places each database's PL socket at $CUBRID_TMP/sp_<db>.sock, or at
# $CUBRID/var/CUBRID_SOCK/sp_<db>.sock when CUBRID_TMP is unset or empty (src/sp/pl_comm.c).
set -euo pipefail
export LC_ALL=C

build_dir="${1:-}"
readonly socket_limit=107
readonly cubrid_tmp_limit=96

db_names=(unittestdb)
if [[ -n "$build_dir" && -d "$build_dir" ]]; then
  # Fixtures create their databases through setup_*.sh scripts that take the name as the next argument.
  while IFS= read -r name; do
    db_names+=("$name")
  done < <(grep -rhoE 'setup_[A-Za-z0-9_]*\.sh" "[^"]+"' --include=CTestTestfile.cmake "$build_dir" 2>/dev/null \
             | sed -E 's/.*" "([^"]+)"$/\1/' | sort -u)
fi

longest_db=""
for name in "${db_names[@]}"; do
  if (( ${#name} > ${#longest_db} )); then
    longest_db="$name"
  fi
done

socket_path_for()
{
  printf '%s/sp_%s.sock' "${1%/}" "$longest_db"
}

fail()
{
  local socket_dir="$2" socket_path
  socket_path="$(socket_path_for "$socket_dir")"
  printf 'CUBRID test preflight failed: %s\n' "$1" >&2
  if [[ -n "${CUBRID_TMP:-}" ]]; then
    printf 'CUBRID_TMP: %s (%s bytes)\n' "$CUBRID_TMP" "${#CUBRID_TMP}" >&2
  else
    printf 'CUBRID_TMP is unset or empty; using $CUBRID/var/CUBRID_SOCK.\n' >&2
  fi
  printf 'Effective PL socket: %s (%s bytes, longest test database %s)\n' "$socket_path" "${#socket_path}" "$longest_db" >&2
  printf 'An overlong path makes the PL server fail with "sockname too long" and the server boot fail.\n' >&2
  printf 'Set CUBRID_TMP to a short, absolute directory unique to this installation, then retry.\n' >&2
  exit 1
}

if [[ -n "${CUBRID_TMP:-}" ]]; then
  if [[ "$CUBRID_TMP" != /* ]]; then
    fail "CUBRID_TMP must be an absolute path." "$CUBRID_TMP"
  elif (( ${#CUBRID_TMP} > cubrid_tmp_limit )); then
    fail "CUBRID_TMP exceeds CUBRID's ${cubrid_tmp_limit}-byte directory limit." "$CUBRID_TMP"
  fi
  socket_path="$(socket_path_for "$CUBRID_TMP")"
  if (( ${#socket_path} > socket_limit )); then
    fail "The PL socket path exceeds the ${socket_limit}-byte Unix socket pathname limit (108 bytes including the terminating NUL)." "$CUBRID_TMP"
  fi
  exit 0
fi

default_dir="${CUBRID:?CUBRID is required}/var/CUBRID_SOCK"
if [[ "$default_dir" != /* ]]; then
  fail "The socket directory must be an absolute path." "$default_dir"
fi
default_socket="$(socket_path_for "$default_dir")"
if (( ${#default_socket} <= socket_limit )); then
  exit 0
fi

# The installation path is too long for its default socket directory. Use a short directory that stays
# the same for this installation, so every process of the run and of later runs meets at the same sockets.
short_dir="/tmp/cubrid-sock-$(printf '%s' "$CUBRID" | sha1sum | cut -c1-10)"
socket_path="$(socket_path_for "$short_dir")"
if (( ${#socket_path} > socket_limit )); then
  fail "A test database name is too long for any socket directory." "$short_dir"
fi
printf 'CUBRID test preflight: %s is %s bytes, over the %s-byte limit; using CUBRID_TMP=%s\n' \
  "$default_socket" "${#default_socket}" "$socket_limit" "$short_dir" >&2
printf '%s\n' "$short_dir"
