#!/usr/bin/env bash

set -euo pipefail

RUNNER_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DEFAULT_IMAGE=${CUBRID_PODMAN_TEST_IMAGE:-registry.access.redhat.com/ubi9/ubi-init:latest}
DEFAULT_TIMEOUT=${CUBRID_PODMAN_TEST_TIMEOUT:-120}
CONTAINER_RUNNER_DIR=/opt/cubrid-podman-test
CONTAINER_TEST_DIR=/opt/cubrid-test

usage()
{
  cat <<'EOF'
Usage:
  cubrid-podman-test.sh run [OPTIONS] TEST_SCRIPT [-- TEST_ARGS...]
  cubrid-podman-test.sh status CONTAINER
  cubrid-podman-test.sh sql CONTAINER [SQL]
  cubrid-podman-test.sh exec CONTAINER COMMAND [ARG...]
  cubrid-podman-test.sh script CONTAINER HOST_SCRIPT [-- SCRIPT_ARGS...]
  cubrid-podman-test.sh shell CONTAINER
  cubrid-podman-test.sh logs CONTAINER
  cubrid-podman-test.sh stop CONTAINER

Run a CUBRID shell test in an isolated Podman container and keep the container
alive after PASS or FAIL for inspection. Database files are ephemeral and are
permanently removed only by the explicit stop command.

Run options:
  -n, --name NAME          Container name; generated when omitted.
  -C, --cubrid-root DIR    Installed CUBRID tree; defaults to $CUBRID.
  -d, --db-name NAME       Inspection database name (must be under 17 chars).
      --server             Ask compatible tests to use and preserve cub_server;
                           requires --db-name.
  -e, --env KEY=VALUE      Extra test environment; repeatable.
  -v, --mount SPEC         Extra bind mount SRC:DST[:ro|rw]; repeatable.
      --image IMAGE        Existing local image (default: UBI 9 init).
      --network MODE       Podman network mode (default: none).
      --timeout SECONDS    Wait for test completion (default: 120).

Environment contract available to tests:
  CUBRID_PODMAN=1
  CUBRID_PODMAN_KEEP_ALIVE=1
  CUBRID_PODMAN_STATE_DIR=/sandbox
  CUBRID_PODMAN_DB_DIR=/sandbox/database
  CUBRID_PODMAN_DB_NAME=<--db-name, when supplied>
  CUBRID_PODMAN_USE_SERVER=1          (only with --server)

The CUBRID install tree and test directory are mounted read-only. Tests should
write under $CUBRID_PODMAN_STATE_DIR, $CUBRID_PODMAN_DB_DIR, /work, or /tmp.
The script command streams a host shell script to bash in an existing container;
it does not copy the script into the container or create another container.
EOF
}

die()
{
  echo "ERROR: $*" >&2
  exit 1
}

require_podman()
{
  command -v podman >/dev/null 2>&1 || die "podman is not available in PATH"
}

container_exists()
{
  local container_name=$1
  podman container exists "${container_name}"
}

container_running()
{
  local container_name=$1
  [[ $(podman inspect --format '{{.State.Running}}' "${container_name}" 2>/dev/null) == true ]]
}

container_label()
{
  local container_name=$1
  local label_name=$2
  podman inspect --format "{{ index .Config.Labels \"${label_name}\" }}" "${container_name}"
}

require_managed_container()
{
  local container_name=$1
  container_exists "${container_name}" || die "container does not exist: ${container_name}"
  [[ $(container_label "${container_name}" io.cubrid.podman-test) == true ]] \
    || die "refusing unmanaged container: ${container_name}"
}

sanitize_name()
{
  local value=$1
  value=${value//[^a-zA-Z0-9_.-]/-}
  value=${value:0:48}
  printf '%s\n' "${value}"
}

container_main()
{
  local test_path=$1
  shift

  mkdir -p "${CUBRID_DATABASES}" "${CUBRID_PODMAN_DB_DIR}" "${HOME}"
  printf '#db-name\tvol-path\t\tdb-host\t\tlog-path\t\tlob-base-path\n' \
    > "${CUBRID_DATABASES}/databases.txt"

  echo "TEST: ${test_path}"
  set +e
  if [[ -x "${test_path}" ]]; then
    "${test_path}" "$@"
  else
    /bin/bash "${test_path}" "$@"
  fi
  local test_status=$?
  set -e

  printf '%s\n' "${test_status}" > "${CUBRID_PODMAN_STATE_DIR}/test.status"
  if [[ "${test_status}" -eq 0 ]]; then
    touch "${CUBRID_PODMAN_STATE_DIR}/test.ready"
    echo "READY: test passed; container is available for inspection"
  else
    touch "${CUBRID_PODMAN_STATE_DIR}/test.failed"
    echo "FAILED: test exited ${test_status}; container is preserved for inspection" >&2
  fi

  exec sleep infinity
}

print_inspection_help()
{
  local container_name=$1
  local db_name=$2

  cat <<EOF

Live inspection:
  $0 status ${container_name}
  $0 logs ${container_name}
  $0 exec ${container_name} COMMAND [ARG...]
  $0 shell ${container_name}
EOF
  if [[ -n "${db_name}" ]]; then
    cat <<EOF
  $0 sql ${container_name} "SELECT * FROM db_root;"
EOF
  fi
  cat <<EOF

Cleanup (permanently deletes the ephemeral database):
  $0 stop ${container_name}
EOF
}

run_container()
{
  require_podman

  local container_name=
  local cubrid_root=${CUBRID:-}
  local db_name=
  local use_server=0
  local image=${DEFAULT_IMAGE}
  local network_mode=none
  local wait_seconds=${DEFAULT_TIMEOUT}
  local test_script=
  local test_dir test_name container_test_path generated_name deadline test_status mount_spec
  local -a extra_envs=()
  local -a extra_mounts=()
  local -a podman_mount_args=()
  local -a test_args=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -n|--name)
        [[ $# -ge 2 ]] || die "$1 requires a value"
        container_name=$2
        shift 2
        ;;
      -C|--cubrid-root)
        [[ $# -ge 2 ]] || die "$1 requires a value"
        cubrid_root=$2
        shift 2
        ;;
      -d|--db-name)
        [[ $# -ge 2 ]] || die "$1 requires a value"
        db_name=$2
        shift 2
        ;;
      --server)
        use_server=1
        shift
        ;;
      -e|--env)
        [[ $# -ge 2 ]] || die "$1 requires a value"
        extra_envs+=("$2")
        shift 2
        ;;
      -v|--mount)
        [[ $# -ge 2 ]] || die "$1 requires a value"
        extra_mounts+=("$2")
        shift 2
        ;;
      --image)
        [[ $# -ge 2 ]] || die "$1 requires a value"
        image=$2
        shift 2
        ;;
      --network)
        [[ $# -ge 2 ]] || die "$1 requires a value"
        network_mode=$2
        shift 2
        ;;
      --timeout)
        [[ $# -ge 2 ]] || die "$1 requires a value"
        wait_seconds=$2
        shift 2
        ;;
      --)
        shift
        [[ $# -gt 0 ]] || die "missing TEST_SCRIPT after --"
        test_script=$1
        shift
        test_args=("$@")
        break
        ;;
      -*)
        die "unknown run option: $1"
        ;;
      *)
        test_script=$1
        shift
        if [[ ${1:-} == -- ]]; then
          shift
        fi
        test_args=("$@")
        break
        ;;
    esac
  done

  [[ -n "${test_script}" ]] || die "run requires TEST_SCRIPT"
  [[ -r "${test_script}" && -f "${test_script}" ]] || die "test script is not readable: ${test_script}"
  [[ -n "${cubrid_root}" ]] || die "use --cubrid-root DIR or set CUBRID"
  [[ -d "${cubrid_root}" ]] || die "CUBRID root is not a directory: ${cubrid_root}"
  [[ -x "${cubrid_root}/bin/cubrid" ]] || die "missing executable: ${cubrid_root}/bin/cubrid"
  [[ -x "${cubrid_root}/bin/csql" ]] || die "missing executable: ${cubrid_root}/bin/csql"
  [[ "${wait_seconds}" =~ ^[1-9][0-9]*$ ]] || die "timeout must be a positive integer"

  cubrid_root=$(realpath "${cubrid_root}")
  test_script=$(realpath "${test_script}")
  test_dir=$(dirname "${test_script}")
  test_name=$(basename "${test_script}")
  container_test_path=${CONTAINER_TEST_DIR}/${test_name}

  if [[ -z "${container_name}" ]]; then
    generated_name=$(sanitize_name "${test_name%.*}")
    container_name="cubrid-tc-${generated_name}-${BASHPID}"
  fi
  [[ "${container_name}" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] \
    || die "invalid container name: ${container_name}"

  if [[ -n "${db_name}" ]]; then
    [[ ${#db_name} -lt 17 ]] || die "database name must be shorter than 17 characters: ${db_name}"
    [[ "${db_name}" =~ ^[a-zA-Z][a-zA-Z0-9_]*$ ]] || die "invalid database name: ${db_name}"
  fi
  if [[ "${use_server}" -eq 1 && -z "${db_name}" ]]; then
    die "--server requires --db-name"
  fi

  for mount_spec in "${extra_mounts[@]}"; do
    IFS=: read -r mount_source mount_target mount_mode <<< "${mount_spec}"
    [[ -n "${mount_source}" && -n "${mount_target}" ]] \
      || die "mount must be SRC:DST[:ro|rw]: ${mount_spec}"
    [[ "${mount_target}" == /* ]] || die "mount destination must be absolute: ${mount_target}"
    [[ -e "${mount_source}" ]] || die "mount source does not exist: ${mount_source}"
    mount_source=$(realpath "${mount_source}")
    mount_mode=${mount_mode:-ro}
    case "${mount_mode}" in
      ro)
        podman_mount_args+=(--mount "type=bind,src=${mount_source},dst=${mount_target},ro=true")
        ;;
      rw)
        podman_mount_args+=(--mount "type=bind,src=${mount_source},dst=${mount_target}")
        ;;
      *)
        die "mount mode must be ro or rw: ${mount_spec}"
        ;;
    esac
  done

  for environment_entry in "${extra_envs[@]}"; do
    [[ "${environment_entry}" =~ ^[a-zA-Z_][a-zA-Z0-9_]*= ]] \
      || die "environment must be KEY=VALUE: ${environment_entry}"
  done

  if container_exists "${container_name}"; then
    die "container already exists: ${container_name}"
  fi
  podman image exists "${image}" || die "Podman image is not available locally: ${image}"

  local -a podman_env_args=(
    --env "CUBRID=${cubrid_root}"
    --env CUBRID_DATABASES=/sandbox/databases
    --env "LD_LIBRARY_PATH=${cubrid_root}/lib:${cubrid_root}/cci/lib"
    --env "PATH=${cubrid_root}/bin:/usr/bin:/bin"
    --env HOME=/sandbox/home
    --env CUBRID_PODMAN=1
    --env CUBRID_PODMAN_KEEP_ALIVE=1
    --env CUBRID_PODMAN_STATE_DIR=/sandbox
    --env CUBRID_PODMAN_DB_DIR=/sandbox/database
  )

  if [[ -n "${db_name}" ]]; then
    podman_env_args+=(--env "CUBRID_PODMAN_DB_NAME=${db_name}")
  fi
  if [[ "${use_server}" -eq 1 ]]; then
    podman_env_args+=(--env CUBRID_PODMAN_USE_SERVER=1)
  fi
  for environment_entry in "${extra_envs[@]}"; do
    podman_env_args+=(--env "${environment_entry}")
  done

  podman run --detach --pull=never \
    --name "${container_name}" \
    --hostname cubrid-tc \
    --network "${network_mode}" \
    --ipc=private \
    --pid=private \
    --userns=nomap \
    --cgroups=disabled \
    --read-only \
    --init \
    --security-opt label=disable \
    --label io.cubrid.podman-test=true \
    --label "io.cubrid.test.source=${test_script}" \
    --label "io.cubrid.root=${cubrid_root}" \
    --label "io.cubrid.db=${db_name}" \
    --mount "type=bind,src=${cubrid_root},dst=${cubrid_root},ro=true" \
    --mount "type=bind,src=${RUNNER_DIR},dst=${CONTAINER_RUNNER_DIR},ro=true" \
    --mount "type=bind,src=${test_dir},dst=${CONTAINER_TEST_DIR},ro=true" \
    "${podman_mount_args[@]}" \
    --tmpfs "${cubrid_root}/log:rw,mode=0755,notmpcopyup" \
    --tmpfs "${cubrid_root}/tmp:rw,mode=0755,notmpcopyup" \
    --tmpfs "${cubrid_root}/var:rw,mode=0755,notmpcopyup" \
    --tmpfs /sandbox:rw,mode=0755,notmpcopyup \
    --tmpfs /work:rw,mode=0755,notmpcopyup \
    --tmpfs /tmp:rw,mode=1777,notmpcopyup \
    "${podman_env_args[@]}" \
    --workdir /work \
    "${image}" \
    /bin/bash "${CONTAINER_RUNNER_DIR}/cubrid-podman-test.sh" \
      _container "${container_test_path}" "${test_args[@]}" \
    >/dev/null

  deadline=$((SECONDS + wait_seconds))
  while (( SECONDS < deadline )); do
    if ! container_running "${container_name}"; then
      podman logs "${container_name}" >&2 || true
      die "container exited before the test completed: ${container_name}"
    fi

    if podman exec "${container_name}" test -f /sandbox/test.status; then
      test_status=$(podman exec "${container_name}" cat /sandbox/test.status)
      podman logs "${container_name}"
      print_inspection_help "${container_name}" "${db_name}"
      return "${test_status}"
    fi
    sleep 1
  done

  podman logs "${container_name}" >&2 || true
  die "timed out after ${wait_seconds}s; container ${container_name} was left running"
}

show_status()
{
  local container_name=${1:-}
  [[ -n "${container_name}" ]] || die "status requires CONTAINER"
  require_podman
  require_managed_container "${container_name}"

  local test_source db_name cubrid_root
  test_source=$(container_label "${container_name}" io.cubrid.test.source)
  db_name=$(container_label "${container_name}" io.cubrid.db)
  cubrid_root=$(container_label "${container_name}" io.cubrid.root)

  podman inspect --format \
    'Container={{.Name}} Running={{.State.Running}} Status={{.State.Status}} Pid={{.State.Pid}}' \
    "${container_name}"
  printf 'Test=%s\nCUBRID=%s\nDatabase=%s\n' "${test_source}" "${cubrid_root}" "${db_name:-<unspecified>}"

  if container_running "${container_name}"; then
    podman exec "${container_name}" /bin/bash -lc '
      if [[ -f "${CUBRID_PODMAN_STATE_DIR}/test.status" ]]; then
        printf "Test_status=%s\n" "$(cat "${CUBRID_PODMAN_STATE_DIR}/test.status")"
      else
        printf "Test_status=running\n"
      fi
      cubrid server status
    '
  fi
}

run_sql()
{
  local container_name=${1:-}
  [[ -n "${container_name}" ]] || die "sql requires CONTAINER"
  shift
  require_podman
  require_managed_container "${container_name}"
  container_running "${container_name}" || die "container is not running: ${container_name}"

  local db_name
  db_name=$(container_label "${container_name}" io.cubrid.db)
  [[ -n "${db_name}" ]] || die "container has no --db-name metadata; use exec with csql explicitly"

  if [[ $# -eq 0 ]]; then
    [[ -t 0 && -t 1 ]] || die "interactive csql requires a terminal; pass SQL as an argument"
    podman exec -it "${container_name}" csql -u dba "${db_name}"
  else
    podman exec "${container_name}" csql -u dba -c "$*" "${db_name}"
  fi
}

run_exec()
{
  local container_name=${1:-}
  [[ -n "${container_name}" ]] || die "exec requires CONTAINER"
  shift
  [[ $# -gt 0 ]] || die "exec requires COMMAND"
  require_podman
  require_managed_container "${container_name}"
  container_running "${container_name}" || die "container is not running: ${container_name}"
  podman exec "${container_name}" "$@"
}

run_script()
{
  local container_name=${1:-}
  [[ -n "${container_name}" ]] || die "script requires CONTAINER"
  shift

  local host_script=${1:-}
  [[ -n "${host_script}" ]] || die "script requires HOST_SCRIPT"
  shift
  if [[ ${1:-} == -- ]]; then
    shift
  fi

  [[ -r "${host_script}" && -f "${host_script}" ]] \
    || die "host script is not readable: ${host_script}"
  require_podman
  require_managed_container "${container_name}"
  container_running "${container_name}" || die "container is not running: ${container_name}"

  podman exec --interactive "${container_name}" /bin/bash -s -- "$@" < "${host_script}"
}

open_shell()
{
  local container_name=${1:-}
  [[ -n "${container_name}" ]] || die "shell requires CONTAINER"
  require_podman
  require_managed_container "${container_name}"
  container_running "${container_name}" || die "container is not running: ${container_name}"
  [[ -t 0 && -t 1 ]] || die "shell requires a terminal"
  podman exec -it "${container_name}" /bin/bash
}

show_logs()
{
  local container_name=${1:-}
  [[ -n "${container_name}" ]] || die "logs requires CONTAINER"
  require_podman
  require_managed_container "${container_name}"
  podman logs "${container_name}"
}

stop_container()
{
  local container_name=${1:-}
  [[ -n "${container_name}" ]] || die "stop requires CONTAINER"
  require_podman
  require_managed_container "${container_name}"

  if container_running "${container_name}"; then
    podman exec "${container_name}" cubrid server stop >/dev/null 2>&1 || true
  fi
  podman rm --force --time 10 "${container_name}" >/dev/null
  echo "Removed ${container_name}; its ephemeral database is no longer recoverable."
}

command_name=${1:-help}
if [[ $# -gt 0 ]]; then
  shift
fi

case "${command_name}" in
  run)
    run_container "$@"
    ;;
  status)
    show_status "$@"
    ;;
  sql)
    run_sql "$@"
    ;;
  exec)
    run_exec "$@"
    ;;
  script)
    run_script "$@"
    ;;
  shell)
    open_shell "$@"
    ;;
  logs)
    show_logs "$@"
    ;;
  stop)
    stop_container "$@"
    ;;
  _container)
    container_main "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage >&2
    die "unknown command: ${command_name}"
    ;;
esac
