#!/bin/env bash

set -e
set -v

# Create the demo database directory if it doesn't already exist

DEMO_DB="$CUBRID_DATABASES/demodb"
mkdir -p "$DEMO_DB"
echo "$DEMO_DB"
pushd "$DEMO_DB"

# Check if the demo database creation script exists and is executable
DEMO_SCRIPT="$CUBRID/demo/make_cubrid_demo.sh"
"$DEMO_SCRIPT"

popd

# Print success message
echo "Demo database successfully created and setup completed."
