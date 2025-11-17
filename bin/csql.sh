#!/bin/env bash

DB="${DB:-testdb}"
echo "##### csql    : $(which csql)"
echo "##### cubrid  : $(which cubrid)"
echo "##### DB loc  : ${CUBRID_DATABASES}"
echo "##### DB name : $DB"

# Check if DB name appears in cubrid server status
if cubrid server status | rg -q "$DB"; then
  echo "##### MODE    : CS MODE"
  echo "##### running: \$ csql -u dba $DB $*"

  exec csql --no-pager -u dba "$DB" "$@"
else
  echo "##### MODE    : SA MODE"
  echo "##### running : \$ csql -u dba $DB -S $*"

  exec csql --no-pager -u dba "$DB" -S "$@"
fi
