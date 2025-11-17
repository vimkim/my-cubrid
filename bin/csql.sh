#!/usr/bin/env bash

DB="${DB:-testdb}"

CSQL_BIN=$(which csql 2>/dev/null)
CUBRID_BIN=$(which cubrid 2>/dev/null)

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

printf "${Y}===== Environment Info =====${N}\n"
printf "  ${G}csql${N}           : %s\n" "$CSQL_BIN"
printf "  ${G}cubrid${N}         : %s\n" "$CUBRID_BIN"
printf "  ${G}DB location${N}    : %s\n" "${CUBRID_DATABASES}"
printf "  ${G}DB name${N}        : %s\n" "$DB"

if cubrid server status | rg -q "$DB"; then
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
