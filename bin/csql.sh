#!/usr/bin/env bash

# A leading database name is consumed; remaining arguments belong to csql.
DB=""
if [[ $# -gt 0 && $1 != -* ]]; then
  DB=$1
  shift
fi

if ! SERVER_STATUS=$(cubrid server status); then
  printf 'Unable to determine running CUBRID servers.\n' >&2
  exit 1
fi
mapfile -t RUNNING_DATABASES < <(
  printf '%s\n' "$SERVER_STATUS" | awk '$1 == "Server" || $1 == "HA-Server" { if (!seen[$2]++) print $2 }'
)

select_database()
{
  local prompt=$1
  shift
  if [[ $# -eq 0 ]]; then
    printf 'No databases available for selection.\n' >&2
    exit 1
  fi
  if ! command -v fzf >/dev/null 2>&1; then
    printf 'Database selection requires fzf; install it or pass a database name.\n' >&2
    exit 1
  fi
  DB=$(printf '%s\n' "$@" | fzf --height=40% --layout=reverse --border --no-multi --prompt="$prompt") || exit $?
  [[ -n $DB ]] || exit 1
}

if [[ -z $DB ]]; then
  case ${#RUNNING_DATABASES[@]} in
    0)
      REGISTRY="${CUBRID_DATABASES:-.}/databases.txt"
      if [[ ! -r $REGISTRY ]]; then
        printf 'Cannot read database registry: %s\n' "$REGISTRY" >&2
        exit 1
      fi
      mapfile -t REGISTERED_DATABASES < <(
        awk 'NF && $1 !~ /^#/ { if (!seen[$1]++) print $1 }' "$REGISTRY"
      )
      select_database 'Registered database (standalone)> ' "${REGISTERED_DATABASES[@]}"
      ;;
    1) DB=${RUNNING_DATABASES[0]} ;;
    *) select_database 'Running database> ' "${RUNNING_DATABASES[@]}" ;;
  esac
fi

SERVER_RUNNING=false
for RUNNING_DB in "${RUNNING_DATABASES[@]}"; do
  if [[ $RUNNING_DB == "$DB" ]]; then
    SERVER_RUNNING=true
    break
  fi
done

CSQL_BIN=$(command -v csql)
CUBRID_BIN=$(command -v cubrid)

verify_server_build()
{
  local actual_server server_pid source_root client_source server_source
  if ! command -v cubrid-binary-source-dir >/dev/null 2>&1; then
    printf 'Refusing connection: cubrid-binary-source-dir is required to verify the server.\n' >&2
    return 1
  fi
  if ! client_source=$(cubrid-binary-source-dir "$CSQL_BIN"); then
    printf 'Refusing connection: cannot determine the client source tree.\n' >&2
    return 1
  fi
  source_root=$(git rev-parse --show-toplevel 2>/dev/null) || source_root=""
  # Outside a CUBRID checkout, use the selected client's recorded source tree.
  if [[ -z $source_root || ! -f $source_root/src/storage/page_buffer.c ]]; then
    source_root=$client_source
  fi
  source_root=$(realpath -e -- "$source_root") || return 1
  if [[ $client_source != "$source_root" ]]; then
    printf 'Refusing connection: csql belongs to another source tree.\n' >&2
    printf '  Current tree: %s\n  Client tree:  %s\n' "$source_root" "$client_source" >&2
    return 1
  fi

  # The master identifies the target PID; unrelated servers may use the same DB name.
  server_pid=$(printf '%s\n' "$SERVER_STATUS" | awk -v db="$DB" '
    ($1 == "Server" || $1 == "HA-Server") && $2 == db {
      for (i = 3; i < NF; i++) if ($i == "pid") {
        pid = $(i + 1); sub(/\)$/, "", pid); print pid
      }
    }')
  if [[ ! $server_pid =~ ^[0-9]+$ ]]; then
    printf 'Refusing connection: cannot determine the server PID for %s.\n' "$DB" >&2
    return 1
  fi
  actual_server=$(readlink -- "/proc/$server_pid/exe") || actual_server=""
  if [[ ${actual_server##*/} != cub_server ]]; then
    printf 'Refusing connection: cannot inspect the running cub_server for %s (PID %s).\n' "$DB" "$server_pid" >&2
    return 1
  fi
  if ! server_source=$(cubrid-binary-source-dir "/proc/$server_pid/exe"); then
    printf 'Refusing connection: cannot determine the running server source tree.\n' >&2
    return 1
  fi
  if [[ $server_source != "$source_root" ]]; then
    printf 'Refusing connection: running server belongs to another source tree.\n' >&2
    printf '  Database: %s\n  Server PID: %s\n  Current tree: %s\n  Server tree:  %s\n  Running: %s\n' \
      "$DB" "$server_pid" "$source_root" "$server_source" "$actual_server" >&2
    printf "Switch to the server's environment, or start the matching server on a separate port.\n" >&2
    return 1
  fi
}

if "$SERVER_RUNNING"; then
  verify_server_build || exit 1
fi

Y="\033[33m" # yellow
G="\033[32m" # green
N="\033[0m"

BLACK="\033[30m"
RED="\033[31m"
GREEN="\033[32m"
YELLOW="\033[33m"
BLUE="\033[34m"
MAGENTA="\033[35m"
CYAN="\033[36m"
WHITE="\033[37m"
BRIGHT_RED="\033[91m"

cubrid_rel | rg "CUBRID"
printf "${Y}===== Environment Info =====${N}\n"
printf "  ${G}csql${N}           : %s\n" "$CSQL_BIN"
printf "  ${G}cubrid${N}         : %s\n" "$CUBRID_BIN"
printf "  ${G}DB location${N}    : %s\n" "${CUBRID_DATABASES}"
printf "  ${G}DB name${N}        : %s\n" "$DB"

if "$SERVER_RUNNING"; then
  printf "  ${G}Mode${N}           : ${CYAN}CS MODE\n${N}"
printf "${Y}=============================${N}\n"
  printf "Running: csql -u dba %s ${MAGENTA}%s${N}\n\n" "$DB" "$*"
  exec "$CSQL_BIN" --no-pager -u dba "$DB" "$@"
else
  printf "  ${G}Mode${N}           : ${CYAN}SA MODE\n${N}"
printf "${Y}=============================${N}\n"
  printf "Running: csql -u dba %s -S ${MAGENTA}%s${N}\n\n" "$DB" "$*"
  exec "$CSQL_BIN" --no-pager -u dba "$DB" -S "$@"
fi
