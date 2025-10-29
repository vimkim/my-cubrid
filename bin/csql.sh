#!/bin/env bash

DB="${DB:-testdb}"

echo "connecting to ... $DB"

# Check if DB name appears in cubrid server status
if cubrid server status | rg -q "$DB"; then
    echo "##### CS MODE to db: $DB"
    exec csql -u dba "$DB" "$@"
else
    echo "##### SA MODE to db: $DB"
    exec csql -u dba "$DB" -S "$@"
fi

