#!/usr/bin/env bash

# Coordinate builds, installs, and runtime activity that share a CUBRID worktree.
# Normal builds never stop a running CUBRID process. Compilation may complete,
# but installation is deferred with EX_TEMPFAIL while the install prefix is busy.

set -euo pipefail

readonly EX_USAGE=64
readonly EX_TEMPFAIL=75
readonly DEFAULT_BUILD_LOCK_TIMEOUT="${CUBRID_BUILD_LOCK_TIMEOUT:-600}"
readonly DEFAULT_RUNTIME_LOCK_TIMEOUT="${CUBRID_RUNTIME_LOCK_TIMEOUT:-300}"

usage()
{
  cat <<'EOF'
Usage: cubrid-build-coordinator.sh ACTION [ARGUMENTS]

Actions:
  configure
  compile
  build [runtime-wait-seconds]
  install [runtime-wait-seconds]
  install-target <target> [runtime-wait-seconds]
  runtime [lock-wait-seconds] -- command [args...]
  stop-and-build

Exit status 75 means that the operation is safe to retry later.
EOF
}

die_usage()
{
  printf 'Error: %s\n' "$*" >&2
  usage >&2
  exit "$EX_USAGE"
}

require_environment()
{
  : "${PRESET_MODE:?PRESET_MODE is required}"
  : "${CUBRID_BUILD_DIR:?CUBRID_BUILD_DIR is required}"
  : "${CUBRID:?CUBRID is required}"

  command -v cmake >/dev/null || die_usage "cmake is not available"
  command -v flock >/dev/null || die_usage "flock is not available"
  command -v sha256sum >/dev/null || die_usage "sha256sum is not available"
}

validate_timeout()
{
  local timeout="$1"
  [[ "$timeout" =~ ^[0-9]+$ ]] || die_usage "timeout must be a non-negative integer: $timeout"
}

lock_id()
{
  printf '%s' "$1" | sha256sum | awk '{print $1}'
}

initialize_locks()
{
  local lock_root
  local canonical_build_dir
  local canonical_install_dir

  lock_root="${XDG_RUNTIME_DIR:-/tmp}/cubrid-dev-locks-${UID}"
  install -d -m 700 "$lock_root"

  canonical_build_dir="$(realpath -m -- "$CUBRID_BUILD_DIR")"
  canonical_install_dir="$(realpath -m -- "$CUBRID")"
  BUILD_LOCK="${lock_root}/build-$(lock_id "$canonical_build_dir").lock"
  RUNTIME_LOCK="${lock_root}/runtime-$(lock_id "$canonical_install_dir").lock"
  INSTALL_PREFIX="$canonical_install_dir"
}

acquire_build_lock()
{
  local timeout="${1:-$DEFAULT_BUILD_LOCK_TIMEOUT}"
  validate_timeout "$timeout"

  exec {BUILD_LOCK_FD}>"$BUILD_LOCK"
  if ! flock -w "$timeout" "$BUILD_LOCK_FD"; then
    printf 'Build directory is busy: %s\n' "$CUBRID_BUILD_DIR" >&2
    printf 'Retry this command later. No process was stopped.\n' >&2
    exit "$EX_TEMPFAIL"
  fi
}

find_active_install_processes()
{
  local proc_dir
  local executable
  local process_name

  for proc_dir in /proc/[0-9]*; do
    [[ -e "$proc_dir/exe" ]] || continue
    executable="$(readlink "$proc_dir/exe" 2>/dev/null || true)"
    executable="${executable% (deleted)}"
    case "$executable" in
      "$INSTALL_PREFIX"/*)
        process_name="$(cat "$proc_dir/comm" 2>/dev/null || printf 'unknown')"
        printf '%s\t%s\t%s\n' "${proc_dir##*/}" "$process_name" "$executable"
        ;;
    esac
  done
}

report_runtime_busy()
{
  local processes="$1"

  printf '\nInstallation deferred: the target CUBRID environment is busy.\n' >&2
  printf 'Environment: %s\n' "$CUBRID" >&2
  if [[ -n "$processes" ]]; then
    printf 'Active processes:\n' >&2
    while IFS=$'\t' read -r pid name executable; do
      printf '  PID %-8s %-20s %s\n' "$pid" "$name" "$executable" >&2
    done <<<"$processes"
  else
    printf 'Another coordinated test or runtime command owns the runtime lock.\n' >&2
  fi
  printf 'No process was stopped. Retry with: just install\n' >&2
}

acquire_idle_runtime_lock()
{
  local timeout="$1"
  local deadline
  local processes=""

  validate_timeout "$timeout"
  deadline=$((SECONDS + timeout))

  while true; do
    exec {RUNTIME_LOCK_FD}>"$RUNTIME_LOCK"
    if flock -n "$RUNTIME_LOCK_FD"; then
      processes="$(find_active_install_processes)"
      if [[ -z "$processes" ]]; then
        return 0
      fi
      flock -u "$RUNTIME_LOCK_FD"
    else
      processes=""
    fi
    exec {RUNTIME_LOCK_FD}>&-

    if (( SECONDS >= deadline )); then
      report_runtime_busy "$processes"
      exit "$EX_TEMPFAIL"
    fi
    sleep 2
  done
}

acquire_runtime_lock()
{
  local timeout="$1"
  validate_timeout "$timeout"

  exec {RUNTIME_LOCK_FD}>"$RUNTIME_LOCK"
  if ! flock -w "$timeout" "$RUNTIME_LOCK_FD"; then
    report_runtime_busy ""
    exit "$EX_TEMPFAIL"
  fi
}

compile_unlocked()
{
  cmake --build --preset "$PRESET_MODE"
}

install_unlocked()
{
  cmake --install "$CUBRID_BUILD_DIR" --prefix "$CUBRID"
  printf 'Build and install completed successfully!\n'
}

stop_current_runtime()
{
  local cubrid_command="$CUBRID/bin/cubrid"

  if [[ ! -x "$cubrid_command" ]]; then
    return 0
  fi

  "$cubrid_command" service stop || true
  "$cubrid_command" broker stop || true
}

wait_for_runtime_to_stop()
{
  local deadline=$((SECONDS + 30))
  local processes

  while true; do
    processes="$(find_active_install_processes)"
    [[ -z "$processes" ]] && return 0
    if (( SECONDS >= deadline )); then
      printf 'The explicitly requested stop did not finish within 30 seconds.\n' >&2
      report_runtime_busy "$processes"
      return 1
    fi
    sleep 1
  done
}

action="${1:-}"
[[ -n "$action" ]] || die_usage "action is required"
shift

require_environment
initialize_locks

case "$action" in
  configure)
    [[ $# -eq 0 ]] || die_usage "configure takes no arguments"
    acquire_build_lock
    cmake --preset "$PRESET_MODE"
    ;;
  compile)
    [[ $# -eq 0 ]] || die_usage "compile takes no arguments"
    acquire_build_lock
    compile_unlocked
    ;;
  build)
    [[ $# -le 1 ]] || die_usage "build accepts at most one timeout"
    runtime_timeout="${1:-0}"
    acquire_build_lock
    compile_unlocked
    acquire_idle_runtime_lock "$runtime_timeout"
    install_unlocked
    ;;
  install)
    [[ $# -le 1 ]] || die_usage "install accepts at most one timeout"
    runtime_timeout="${1:-0}"
    acquire_build_lock
    acquire_idle_runtime_lock "$runtime_timeout"
    install_unlocked
    ;;
  install-target)
    [[ $# -ge 1 && $# -le 2 ]] || die_usage "install-target requires a target and optional timeout"
    target="$1"
    runtime_timeout="${2:-0}"
    acquire_build_lock
    acquire_idle_runtime_lock "$runtime_timeout"
    cmake --build --preset "$PRESET_MODE" --target "$target"
    ;;
  runtime)
    if [[ "${1:-}" == "--" ]]; then
      runtime_timeout="$DEFAULT_RUNTIME_LOCK_TIMEOUT"
    else
      runtime_timeout="${1:-$DEFAULT_RUNTIME_LOCK_TIMEOUT}"
      [[ $# -ge 1 ]] && shift
    fi
    [[ "${1:-}" == "--" ]] && shift
    [[ $# -gt 0 ]] || die_usage "runtime requires a command"
    if [[ "${CUBRID_RUNTIME_LOCK_HELD:-0}" == "1" ]]; then
      exec "$@"
    fi
    acquire_runtime_lock "$runtime_timeout"
    export CUBRID_RUNTIME_LOCK_HELD=1
    exec "$@"
    ;;
  stop-and-build)
    [[ $# -eq 0 ]] || die_usage "stop-and-build takes no arguments"
    acquire_build_lock
    compile_unlocked
    acquire_runtime_lock "$DEFAULT_RUNTIME_LOCK_TIMEOUT"
    stop_current_runtime
    wait_for_runtime_to_stop
    install_unlocked
    ;;
  *)
    die_usage "unknown action: $action"
    ;;
esac
