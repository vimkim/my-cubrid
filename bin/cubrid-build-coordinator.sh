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
  database-delete [lock-wait-seconds] [--database name]
  installation-delete [lock-wait-seconds]
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
    printf 'Runtime command could not acquire the lock within %s seconds.\n' "$timeout" >&2
    printf 'Environment: %s\nLock: %s\n' "$CUBRID" "$RUNTIME_LOCK" >&2
    printf 'Another runtime command or a daemon holding an inherited lock may own it.\n' >&2
    exit "$EX_TEMPFAIL"
  fi
}

runtime_guard_command()
{
  printf '%s/bin/my-cubrid-runtime' "${MY_CUBRID:-$HOME/my-cubrid}"
}

validate_runtime()
{
  local required_state="${1:-ready}"
  local report
  local status
  local guard
  local -a validation_arguments=()

  if [[ "$required_state" == idle ]]; then
    validation_arguments+=(--require-idle)
  elif [[ "$required_state" != ready ]]; then
    die_usage "unknown runtime validation requirement: $required_state"
  fi

  guard="$(runtime_guard_command)"
  if report="$("$guard" validate --worktree "$PWD" --preset "$PRESET_MODE" \
      "${validation_arguments[@]}" --json)"; then
    return 0
  else
    status=$?
  fi
  printf '%s\n' "$report" >&2
  return "$status"
}

validate_runtime_ready()
{
  validate_runtime ready
}

validate_runtime_idle()
{
  validate_runtime idle
}

require_selected_database()
{
  local expected="$1"
  local selected
  local selector="${MY_CUBRID:-$HOME/my-cubrid}/bin/my-cubrid-pwddb-getname"

  selected="$("$selector")"
  if [[ "$selected" != "$expected" ]]; then
    printf 'Refusing fixed database command for %s: manifest-selected database is %s.\n' \
      "$expected" "$selected" >&2
    return 1
  fi
}

initialize_guarded_runtime()
{
  local guard

  guard="$(runtime_guard_command)"
  "$guard" init --worktree "$PWD" --preset "$PRESET_MODE"
}

compile_unlocked()
{
  cmake --build --preset "$PRESET_MODE"
}

prepare_jdk_install_destination()
{
  local build_jdk="$CUBRID_BUILD_DIR/vm/jdk8"
  local install_jdk="$INSTALL_PREFIX/vm/jdk8"

  if [[ -L "$build_jdk" && -d "$install_jdk" && ! -L "$install_jdk" ]]; then
    printf 'Replacing bundled install JDK with JAVA_HOME symlink: %s\n' "$install_jdk"
    cmake -E remove_directory "$install_jdk"
  elif [[ -d "$build_jdk" && ! -L "$build_jdk" && -L "$install_jdk" ]]; then
    printf 'Replacing JAVA_HOME install symlink with bundled JDK: %s\n' "$install_jdk"
    cmake -E remove "$install_jdk"
  fi
}

install_unlocked()
{
  prepare_jdk_install_destination
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
    initialize_guarded_runtime
    ;;
  install)
    [[ $# -le 1 ]] || die_usage "install accepts at most one timeout"
    runtime_timeout="${1:-0}"
    acquire_build_lock
    acquire_idle_runtime_lock "$runtime_timeout"
    install_unlocked
    initialize_guarded_runtime
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
    expected_database=""
    if [[ "${1:-}" == "--database" ]]; then
      [[ $# -ge 2 ]] || die_usage "runtime --database requires a database name"
      expected_database="$2"
      shift 2
    fi
    [[ "${1:-}" == "--" ]] && shift
    [[ $# -gt 0 ]] || die_usage "runtime requires a command"
    acquire_runtime_lock "$runtime_timeout"
    validate_runtime_ready
    [[ -z "$expected_database" ]] || require_selected_database "$expected_database"
    # Keep the lock in this supervisor, not in the command or its daemon children.
    (
      exec {RUNTIME_LOCK_FD}>&-
      exec "$@"
    )
    ;;
  database-delete)
    if [[ $# -eq 0 || "${1:-}" == "--database" ]]; then
      runtime_timeout="$DEFAULT_RUNTIME_LOCK_TIMEOUT"
    else
      runtime_timeout="$1"
      shift
    fi
    expected_database=""
    if [[ "${1:-}" == "--database" ]]; then
      [[ $# -eq 2 ]] || die_usage "database-delete --database requires exactly one database name"
      expected_database="$2"
      shift 2
    fi
    [[ $# -eq 0 ]] || die_usage "database-delete accepts only a timeout and optional database name"
    acquire_runtime_lock "$runtime_timeout"
    database_helper="${MY_CUBRID:-$HOME/my-cubrid}/bin/my-cubrid-pwddb"
    database_arguments=(delete)
    if [[ -n "$expected_database" ]]; then
      database_arguments+=(--expected-name "$expected_database")
    fi
    (
      exec {RUNTIME_LOCK_FD}>&-
      exec "$database_helper" "${database_arguments[@]}"
    )
    ;;
  installation-delete)
    [[ $# -le 1 ]] || die_usage "installation-delete accepts at most one timeout"
    runtime_timeout="${1:-$DEFAULT_RUNTIME_LOCK_TIMEOUT}"
    acquire_runtime_lock "$runtime_timeout"
    validate_runtime_idle
    [[ "$INSTALL_PREFIX" != / && "$INSTALL_PREFIX" != "$HOME" ]] \
      || die_usage "refusing to remove a broad installation path: $INSTALL_PREFIX"
    /bin/rm -rf -- "$INSTALL_PREFIX"
    ;;
  stop-and-build)
    [[ $# -eq 0 ]] || die_usage "stop-and-build takes no arguments"
    acquire_build_lock
    compile_unlocked
    acquire_runtime_lock "$DEFAULT_RUNTIME_LOCK_TIMEOUT"
    validate_runtime_ready
    stop_current_runtime
    wait_for_runtime_to_stop
    install_unlocked
    initialize_guarded_runtime
    ;;
  *)
    die_usage "unknown action: $action"
    ;;
esac
