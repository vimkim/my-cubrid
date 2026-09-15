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
  exec csql --no-pager -u dba "$DB" "$@"
else
  printf "  ${G}Mode${N}           : ${CYAN}SA MODE\n${N}"
printf "${Y}=============================${N}\n"
  printf "Running: csql -u dba %s -S ${MAGENTA}%s${N}\n\n" "$DB" "$*"
  exec csql --no-pager -u dba "$DB" -S "$@"
fi
