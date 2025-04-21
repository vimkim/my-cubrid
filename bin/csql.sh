#!/bin/bash

# Find the running CUBRID database name from the process list
db=$(pgrep cub_server | xargs -I{} ps -p {} -o args= | awk '{print $2}')

# Connect to the database with csql
if [ -n "$db" ]; then
    # If a database was found, connect to it
    echo "##### CS MODE to db: $db"
    csql -u dba "${db}"
else
    # If no database was found, connect to the default "testdb"
    echo "##### SA MODE to db: testdb"
    csql -u dba testdb -S
fi
