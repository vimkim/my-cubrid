#!/bin/bash

DB="${DB:-testdb}"

echo "connecting to ... $DB"

if [ "$SA" = "1" ]; then
    echo "##### SA MODE to db: $DB"
    csql -u dba "$DB" -S "$@"
else
    echo "##### CS MODE to db: $DB"
    csql -u dba "$DB" "$@"
fi
